"""
Orchestrator Agent — pipeline coordinator.

Sequential dispatch: prompt → requirements → parts → pcb → cad → assembly → quote.
All agents use claude-opus-4-6. Quoter is deterministic (no LLM).
"""
import json
import re
import time
import hashlib
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Callable

import asyncio

import src.config  # noqa: F401 — validates API key on import
from src.llm_client import get_llm_client

MODEL = src.config.CONFIG.model
MAX_RETRIES = 3
RETRY_BASE_MS = 1000

# ── Response cache (avoids re-calling Opus on retry) ──────────

_CACHE_DIR = Path("/tmp/hwb_cache")
_CACHE_DIR.mkdir(exist_ok=True)


def _cache_key(model: str, system: str, user: str) -> str:
    h = hashlib.sha256(f"{model}:{system}:{user}".encode()).hexdigest()[:16]
    return str(_CACHE_DIR / f"{h}.json")


def _cache_get(key: str) -> str | None:
    p = Path(key)
    if p.exists() and (time.time() - p.stat().st_mtime) < 3600:
        return p.read_text()
    return None


def _cache_put(key: str, text: str):
    Path(key).write_text(text)


# ── JSON extraction ───────────────────────────────────────────

def _clean_json(raw: str) -> str:
    """Fix trailing commas, comments, and other LLM JSON quirks."""
    raw = re.sub(r',\s*([}\]])', r'\1', raw)      # trailing commas
    raw = re.sub(r'//[^\n]*', '', raw)              # line comments
    raw = re.sub(r'/\*.*?\*/', '', raw, flags=re.DOTALL)  # block comments
    return raw.strip()


def _repair_truncated_json(text: str) -> str:
    """Aggressively repair truncated JSON by closing open structures."""
    # Strip trailing incomplete tokens (partial strings, keys, values)
    # Work backwards to find the last complete value
    text = text.rstrip()
    # Remove trailing partial string (unclosed quote)
    if text.count('"') % 2 != 0:
        last_q = text.rfind('"')
        text = text[:last_q]
    # Remove trailing partial value after last comma or bracket
    text = re.sub(r'[,:\s]*$', '', text)
    # Remove trailing key without value: ,"key"
    text = re.sub(r',\s*"[^"]*"\s*$', '', text)
    # Remove trailing incomplete object/array entry
    text = re.sub(r',\s*\{[^}]*$', '', text)
    text = re.sub(r',\s*\[[^\]]*$', '', text)
    text = text.rstrip(', \n\t')
    # Now close open brackets/braces
    open_braces = text.count('{') - text.count('}')
    open_brackets = text.count('[') - text.count(']')
    text += ']' * max(0, open_brackets)
    text += '}' * max(0, open_braces)
    return text


def parse_json_response(text: str) -> Any:
    """Extract JSON from Claude response. Handles fences, prose, truncation."""
    text = text.strip()

    # 1. Direct parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # 2. Extract from ```json ... ``` fences
    for m in re.finditer(r'```(?:json)?\s*\n(.*?)```', text, re.DOTALL):
        try:
            return json.loads(_clean_json(m.group(1)))
        except json.JSONDecodeError:
            continue

    # 3. Unclosed fence (response truncated at max_tokens)
    fence_start = re.search(r'```(?:json)?\s*\n', text)
    if fence_start:
        raw = _clean_json(text[fence_start.end():])
        for attempt in [raw, _repair_truncated_json(raw)]:
            try:
                return json.loads(attempt)
            except json.JSONDecodeError:
                continue
        # Aggressive: try removing last N chars until it parses
        for trim in range(1, min(500, len(raw))):
            candidate = _repair_truncated_json(raw[:-trim])
            try:
                return json.loads(candidate)
            except json.JSONDecodeError:
                continue

    # 4. Bracket matching (first [ or { to last ] or })
    for sc, ec in [('[', ']'), ('{', '}')]:
        s = text.find(sc)
        e = text.rfind(ec)
        if s >= 0 and e > s:
            try:
                return json.loads(_clean_json(text[s:e + 1]))
            except json.JSONDecodeError:
                repaired = _repair_truncated_json(_clean_json(text[s:]))
                try:
                    return json.loads(repaired)
                except json.JSONDecodeError:
                    continue

    raise ValueError(f"JSON parse failed: {text[:150]}...")


# ── Data classes ──────────────────────────────────────────────

@dataclass
class AgentMessage:
    """Inter-agent typed message envelope."""
    from_agent: str
    to_agent: str
    task: str
    payload: dict = field(default_factory=dict)
    status: str = "pending"
    result: Any = None
    error: str | None = None
    duration_ms: int = 0


@dataclass
class ProjectSpec:
    """Accumulates pipeline outputs into a complete project."""
    prompt: str
    requirements: dict = field(default_factory=dict)
    bom: list[dict] = field(default_factory=list)
    pcb_design: dict | None = None
    cad_files: list[str] = field(default_factory=list)
    assembly: dict = field(default_factory=dict)
    quote: dict = field(default_factory=dict)
    total_cost: float = 0.0
    currency: str = "CNY"
    delivery_estimate: str = ""
    status: str = "planning"
    errors: list[str] = field(default_factory=list)


# ── Orchestrator ──────────────────────────────────────────────

class Orchestrator:
    def __init__(self):
        self.client = get_llm_client()
        self.agents: dict[str, Any] = {}
        self.message_log: list[AgentMessage] = []
        self.on_status: Callable[[str], None] | None = None

    def register_agent(self, name: str, agent):
        self.agents[name] = agent

    def _status(self, msg: str):
        print(msg)
        if self.on_status:
            self.on_status(msg)

    def _call_claude(self, system: str, user: str, max_tokens: int = 4096) -> str:
        """Call Claude with caching + retry. Returns raw text."""
        ck = _cache_key(MODEL, system, user)
        cached = _cache_get(ck)
        if cached:
            return cached
        last_error = None
        for attempt in range(MAX_RETRIES):
            try:
                resp = self.client.messages.create(
                    model=MODEL, max_tokens=max_tokens,
                    system=system, messages=[{"role": "user", "content": user}],
                )
                text = resp.content[0].text
                _cache_put(ck, text)
                return text
            except Exception as e:
                last_error = e
                delay = RETRY_BASE_MS * (2 ** attempt) / 1000
                self._status(f"   ⏳ Retrying in {delay:.1f}s... ({e})")
                time.sleep(delay)
        raise last_error or RuntimeError("LLM call failed after retries")

    async def run(self, user_prompt: str) -> ProjectSpec:
        spec = ProjectSpec(prompt=user_prompt)

        # ── 1. Requirements ──
        self._status(f"🧠 Analyzing: '{user_prompt}'")
        try:
            spec.requirements = await self._analyze_requirements(user_prompt)
            self._status(f"📋 Project: {spec.requirements.get('project_name', '?')}")
            comps = spec.requirements.get('components_needed', [])
            self._status(f"   Components: {', '.join(comps[:8])}{'...' if len(comps) > 8 else ''}")
        except Exception as e:
            spec.errors.append(f"Requirements: {e}")
            spec.status = "error"
            return spec

        # ── 2. Parts ──
        self._status("\n🔩 Selecting parts...")
        bom = await self._dispatch(AgentMessage(
            "orchestrator", "parts", "select_parts", spec.requirements))
        if isinstance(bom, list) and bom:
            spec.bom = bom
            cost = sum((p.get("price") or p.get("estimated_price") or 0) * p.get("quantity", 1) for p in bom)
            self._status(f"   ✅ {len(bom)} parts selected (¥{cost:.0f} est)")
        else:
            spec.errors.append("Parts: empty BOM")

        # ── 3. PCB ──
        self._status("\n🔌 Designing PCB...")
        pcb = await self._dispatch(AgentMessage(
            "orchestrator", "pcb", "design_pcb",
            {"requirements": spec.requirements, "bom": spec.bom}))
        if isinstance(pcb, dict) and pcb:
            spec.pcb_design = pcb
            conns = pcb.get("circuit_design", {}).get("connections", [])
            self._status(f"   ✅ PCB: {len(conns)} connections")
        else:
            spec.errors.append("PCB: design failed")

        # ── 4. CAD ──
        self._status("\n📐 Generating enclosure...")
        cad = await self._dispatch(AgentMessage(
            "orchestrator", "cad", "generate_enclosure",
            {"requirements": spec.requirements, "bom": spec.bom,
             "pcb_design": spec.pcb_design or {}}))
        if isinstance(cad, dict) and cad:
            spec.cad_files = cad.get("cad_files", cad.get("files", []))
            self._status(f"   ✅ {len(spec.cad_files)} CAD files")
        else:
            spec.errors.append("CAD: generation failed")

        # ── 5. Assembly ──
        self._status("\n🔧 Creating assembly plan...")
        assembly = await self._dispatch(AgentMessage(
            "orchestrator", "assembler", "plan_assembly",
            {"requirements": spec.requirements, "bom": spec.bom,
             "pcb_design": spec.pcb_design or {}, "cad_files": spec.cad_files}))
        if isinstance(assembly, dict) and assembly:
            spec.assembly = assembly
            self._status(f"   ✅ {len(assembly.get('steps', []))} steps")
        else:
            spec.errors.append("Assembly: plan failed")

        # ── 6. Quote ──
        self._status("\n💰 Calculating quote...")
        quote = await self._dispatch(AgentMessage(
            "orchestrator", "quoter", "calculate_quote",
            {"bom": spec.bom, "pcb_design": spec.pcb_design or {},
             "cad_files": spec.cad_files}))
        if isinstance(quote, dict) and quote:
            spec.quote = quote
            spec.total_cost = quote.get("total", 0)
            self._status(f"   ✅ Total: ¥{spec.total_cost:,.2f}")

        spec.status = "ready" if not spec.errors else "partial"
        self._status(f"\n{'✅' if spec.status == 'ready' else '⚠️'} Project {spec.status} — ¥{spec.total_cost:,.2f}")
        return spec

    async def _analyze_requirements(self, prompt: str) -> dict:
        text = self._call_claude(
            system="""You are a hardware project analyzer. Extract structured requirements from a user prompt.

Return ONLY valid JSON (no markdown fences, no explanation):
{
    "project_name": "short name",
    "target_audience": "who is this for",
    "core_function": "what does it do",
    "components_needed": ["ESP32", "OV2640 camera", "18650 battery", ...],
    "size_constraint": "small|medium|large",
    "battery_powered": true/false,
    "wireless_needed": true/false,
    "display_needed": true/false,
    "estimated_complexity": "beginner|intermediate|advanced",
    "safety_requirements": ["rounded edges", ...],
    "special_notes": "anything relevant"
}

Be specific in components_needed. Use part numbers. Include passive components, connectors, power regulation, wiring.""",
            user=prompt, max_tokens=2000,
        )
        return parse_json_response(text)

    async def _dispatch(self, msg: AgentMessage) -> Any:
        self.message_log.append(msg)
        agent = self.agents.get(msg.to_agent)
        if not agent:
            msg.status = "error"
            msg.error = f"Agent '{msg.to_agent}' not registered"
            return {}
        msg.status = "in_progress"
        t0 = time.monotonic()
        try:
            result = await agent.handle(msg)
            msg.status = "done"
            msg.result = result
            msg.duration_ms = int((time.monotonic() - t0) * 1000)
            return result
        except Exception as e:
            msg.status = "error"
            msg.error = str(e)
            msg.duration_ms = int((time.monotonic() - t0) * 1000)
            self._status(f"   ❌ {msg.to_agent}: {e}")
            return {}
