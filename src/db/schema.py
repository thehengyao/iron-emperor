"""Parts database schema and helpers."""
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent.parent.parent / "parts.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS categories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    url TEXT UNIQUE NOT NULL,
    parent_id INTEGER REFERENCES categories(id)
);

CREATE TABLE IF NOT EXISTS parts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    url TEXT UNIQUE NOT NULL,
    sku TEXT,
    price REAL,
    currency TEXT DEFAULT 'CNY',
    in_stock INTEGER DEFAULT 1,
    description TEXT,
    specs TEXT,  -- JSON blob of specs
    image_url TEXT,
    category_id INTEGER REFERENCES categories(id),
    scraped_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_parts_category ON parts(category_id);
CREATE INDEX IF NOT EXISTS idx_parts_sku ON parts(sku);
CREATE VIRTUAL TABLE IF NOT EXISTS parts_fts USING fts5(name, description, specs, content=parts, content_rowid=id);
"""


def init_db(db_path: str | Path = DB_PATH) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row  # dict-like access
    conn.executescript(SCHEMA)
    conn.commit()
    return conn


def search_parts(conn: sqlite3.Connection, query: str, limit: int = 20) -> list[dict]:
    """Full-text search over parts. Returns list of dicts."""
    try:
        rows = conn.execute(
            """SELECT p.id, p.name, p.url, p.sku, p.price, p.currency,
                      p.in_stock, p.description, p.specs, p.image_url, p.category_id
               FROM parts_fts f JOIN parts p ON f.rowid = p.id
               WHERE parts_fts MATCH ? LIMIT ?""",
            (query, limit)
        ).fetchall()
        return [dict(r) for r in rows]
    except Exception:
        # FTS might not be built yet — fall back to LIKE search
        return search_parts_like(conn, query, limit)


def search_parts_like(conn: sqlite3.Connection, query: str, limit: int = 20) -> list[dict]:
    """Fallback LIKE search when FTS isn't available."""
    rows = conn.execute(
        """SELECT id, name, url, sku, price, currency,
                  in_stock, description, specs, image_url, category_id
           FROM parts
           WHERE name LIKE ? OR description LIKE ?
           LIMIT ?""",
        (f"%{query}%", f"%{query}%", limit)
    ).fetchall()
    return [dict(r) for r in rows]


def get_parts_by_category(conn: sqlite3.Connection, category_name: str, limit: int = 30) -> list[dict]:
    """Get parts by category name (fuzzy match)."""
    rows = conn.execute(
        """SELECT p.id, p.name, p.url, p.price, p.in_stock, p.image_url
           FROM parts p JOIN categories c ON p.category_id = c.id
           WHERE c.name LIKE ?
           LIMIT ?""",
        (f"%{category_name}%", limit)
    ).fetchall()
    return [dict(r) for r in rows]


def get_db_stats(conn: sqlite3.Connection) -> dict:
    """Get database statistics."""
    total = conn.execute("SELECT COUNT(*) FROM parts").fetchone()[0]
    priced = conn.execute("SELECT COUNT(*) FROM parts WHERE price > 0").fetchone()[0]
    cats = conn.execute("SELECT COUNT(*) FROM categories").fetchone()[0]
    return {"total_parts": total, "priced_parts": priced, "categories": cats}
