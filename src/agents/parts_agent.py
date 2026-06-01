"""
Parts Agent — searches the 立创商城 (LCSC) database and builds a BOM.

Given requirements from the orchestrator, it:
1. Searches the parts DB using FTS and direct queries
2. Uses Claude or DeepSeek to rank/select the best parts for the project
3. Returns a Bill of Materials with prices (CNY) and LCSC URLs
"""
import json
import sqlite3
from pathlib import Path

from src.db.schema import init_db, DB_PATH
from src.agents.orchestrator import AgentMessage, parse_json_response, MODEL
from src.llm_client import get_llm_client


class PartsAgent:
    def __init__(self, db_path: str | Path = DB_PATH):
        self.conn = init_db(db_path)
        self.conn.row_factory = sqlite3.Row
        self.client = get_llm_client()

    @staticmethod
    def _sanitize_fts(query: str) -> list[str]:
        """Extract clean search tokens from a component description.
        
        FTS5 chokes on parentheses, hyphens, and 'or'/'and' operators.
        Split into individual keywords and quote each one.
        """
        import re
        # Strip parenthetical notes like "(Pixhawk or similar)"
        clean = re.sub(r'\([^)]*\)', '', query)
        # Remove special chars
        clean = re.sub(r'[^\w\s]', ' ', clean)
        # Split into words, drop noise
        stop = {'or', 'and', 'the', 'a', 'an', 'for', 'with', 'not', 'of', 'to', 'in', 'is', 'on', 'by'}
        tokens = [w for w in clean.lower().split() if w not in stop and len(w) > 1]
        return tokens

    def _search_parts(self, query: str, limit: int = 15) -> list[dict]:
        """Search parts via FTS (per-keyword), falling back to LIKE."""
        results = []
        seen = set()
        tokens = self._sanitize_fts(query)

        # FTS: search each keyword independently, merge results
        for token in tokens[:4]:  # cap at 4 keywords
            try:
                fts_q = f'"{token}"'  # quote to prevent operator interpretation
                rows = self.conn.execute(
                    """SELECT p.id, p.name, p.url, p.sku, p.price, p.currency,
                              p.in_stock, p.description, p.image_url, c.name as category
                       FROM parts_fts f
                       JOIN parts p ON f.rowid = p.id
                       LEFT JOIN categories c ON p.category_id = c.id
                       WHERE parts_fts MATCH ?
                       ORDER BY p.price > 0 DESC, p.price ASC
                       LIMIT ?""",
                    (fts_q, limit),
                ).fetchall()
                for r in rows:
                    d = dict(r)
                    key = d["url"] or d["name"]
                    if key not in seen:
                        seen.add(key)
                        results.append(d)
            except Exception:
                pass

        # Also try the full phrase via LIKE for exact substring matches
        if len(results) < limit:
            for token in tokens[:3]:
                try:
                    rows = self.conn.execute(
                        """SELECT p.id, p.name, p.url, p.sku, p.price, p.currency,
                                  p.in_stock, p.description, p.image_url, c.name as category
                           FROM parts p
                           LEFT JOIN categories c ON p.category_id = c.id
                           WHERE p.name LIKE ?
                           ORDER BY p.price > 0 DESC, p.price ASC
                           LIMIT ?""",
                        (f"%{token}%", limit),
                    ).fetchall()
                    for r in rows:
                        d = dict(r)
                        key = d["url"] or d["name"]
                        if key not in seen:
                            seen.add(key)
                            results.append(d)
                except Exception:
                    pass

        return results[:limit * 3]  # return up to 3× limit for Claude to pick from

    def _get_db_stats(self) -> dict:
        """Get DB stats for context."""
        total = self.conn.execute("SELECT COUNT(*) FROM parts").fetchone()[0]
        priced = self.conn.execute("SELECT COUNT(*) FROM parts WHERE price > 0").fetchone()[0]
        cats = self.conn.execute("SELECT COUNT(*) FROM categories").fetchone()[0]
        return {"total_parts": total, "priced_parts": priced, "categories": cats}

    async def handle(self, msg: AgentMessage) -> list[dict]:
        # Handle both direct requirements dict and wrapped {"requirements": {...}}
        requirements = msg.payload
        if "requirements" in requirements and isinstance(requirements["requirements"], dict):
            requirements = requirements["requirements"]
        components_needed = requirements.get("components_needed", requirements.get("key_components", []))
        db_stats = self._get_db_stats()

        # Search for each component type
        all_candidates = {}
        for component in components_needed:
            # Try multiple search strategies
            search_terms = [component]
            # Also try individual words for multi-word queries
            words = component.split()
            if len(words) > 1:
                search_terms.extend(words)

            for term in search_terms:
                results = self._search_parts(term, limit=10)
                for r in results:
                    key = r["url"] or r["name"]
                    if key not in all_candidates:
                        r["search_term"] = component
                        all_candidates[key] = r

        candidates_list = list(all_candidates.values())
        print(f"   Found {len(candidates_list)} candidate parts from DB")

        # Build the prompt for Claude
        if candidates_list:
            return await self._select_from_candidates(requirements, candidates_list, db_stats)
        else:
            print(f"   No DB matches — using LLM knowledge of LCSC inventory")
            return await self._suggest_parts_without_db(requirements)

    async def _select_from_candidates(
        self, requirements: dict, candidates: list[dict], db_stats: dict
    ) -> list[dict]:
        """Use Claude to select optimal BOM from DB candidates."""
        # Compact candidate format to stay within token budget
        slim = []
        for c in candidates[:80]:
            entry = c["name"]
            if c.get("price"):
                entry += f" [¥{c['price']}]"
            if c.get("category"):
                entry += f" ({c['category']})"
            slim.append(entry)

        candidate_text = "\n".join(f"  {i+1}. {s}" for i, s in enumerate(slim))

        response = self.client.messages.create(
            model=MODEL,
            max_tokens=8192,
            system=f"""You select hardware parts from a database of {db_stats['total_parts']} products ({db_stats['priced_parts']} priced) sourced from 立创商城 (LCSC). Prices are in CNY (¥).

Given requirements and candidate parts, return a JSON array. NO markdown fences. NO explanation. ONLY the JSON array.

Each item: {{"name":"exact name","price":12.50,"quantity":1,"reason":"brief"}}

If a needed part isn't in candidates, add it with "estimated_price" instead of "price". Use realistic CNY prices.
Include everything: MCU, sensors, passives, connectors, power, wiring, mounting hardware.""",
            messages=[{
                "role": "user",
                "content": f"PROJECT: {requirements.get('project_name','')}\nCOMPONENTS NEEDED: {', '.join(requirements.get('components_needed',[]))}\n\nAVAILABLE PARTS:\n{candidate_text}",
            }],
        )
        return parse_json_response(response.content[0].text)

    async def _suggest_parts_without_db(self, requirements: dict) -> list[dict]:
        """Fallback: suggest BOM from LLM knowledge when DB has no matches."""
        response = self.client.messages.create(
            model=MODEL,
            max_tokens=8192,
            system="""You are a hardware parts expert familiar with 立创商城 (LCSC). Suggest a complete BOM for the given project.

Return ONLY a JSON array. NO markdown fences. NO explanation.
Each item: {"name":"product name","estimated_price":15.00,"quantity":1,"reason":"brief"}
Use realistic CNY (¥) prices based on LCSC pricing. Include everything: MCU, sensors, passives, connectors, power, wiring.""",
            messages=[{
                "role": "user",
                "content": f"Requirements:\n{json.dumps(requirements, indent=2)}",
            }],
        )
        return parse_json_response(response.content[0].text)
