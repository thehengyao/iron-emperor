#!/usr/bin/env python3
"""
焊武帝 IronEmperor CLI — unified interface for all pipeline operations.

Usage:
  python cli.py build "自动驾驶无人机"     # Run pipeline, print results
  python cli.py serve                        # Start web server
  python cli.py search "arduino"             # Search parts database
  python cli.py stats                        # Database statistics
  python cli.py benchmark "气象站"  # Benchmark pipeline
"""
import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))


def cmd_build(args):
    """Run the full pipeline."""
    from src.agents.orchestrator import Orchestrator
    from src.agents.parts_agent import PartsAgent
    from src.agents.pcb.pcb_agent import PCBAgent
    from src.agents.cad.cad_agent import CADAgent
    from src.agents.assembler.assembly_agent import AssemblyAgent
    from src.agents.quoter.quoter_agent import QuoterAgent
    from dataclasses import asdict

    orch = Orchestrator()
    orch.register_agent("parts", PartsAgent())
    orch.register_agent("pcb", PCBAgent())
    orch.register_agent("cad", CADAgent())
    orch.register_agent("assembler", AssemblyAgent())
    orch.register_agent("quoter", QuoterAgent())

    spec = asyncio.run(orch.run(args.prompt))

    if args.json:
        print(json.dumps(asdict(spec), indent=2))
    else:
        print(f"\n{'='*50}")
        print(f"Project: {spec.requirements.get('project_name', '?')}")
        print(f"Status:  {spec.status}")
        print(f"Parts:   {len(spec.bom)}")
        conns = (spec.pcb_design or {}).get("circuit_design", {}).get("connections", [])
        print(f"PCB:     {len(conns)} connections")
        print(f"CAD:     {len(spec.cad_files)} files")
        print(f"Steps:   {len(spec.assembly.get('steps', []))}")
        print(f"Cost:    ¥{spec.total_cost:,.2f} CNY")
        if spec.errors:
            print(f"\nWarnings: {', '.join(spec.errors)}")

    if args.output:
        Path(args.output).write_text(json.dumps(asdict(spec), indent=2))
        print(f"\nSaved to {args.output}", file=sys.stderr)


def cmd_serve(args):
    """Start the web server."""
    import uvicorn
    from src.config import CONFIG
    host = args.host or CONFIG.host
    port = args.port or CONFIG.port
    print(f"Starting server on {host}:{port}")
    uvicorn.run("src.api.server:app", host=host, port=port, reload=args.reload)


def cmd_search(args):
    """Search the parts database."""
    from src.db.schema import init_db
    import sqlite3
    conn = init_db()
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            "SELECT p.name, p.price, p.url FROM parts_fts f "
            "JOIN parts p ON f.rowid = p.id WHERE parts_fts MATCH ? LIMIT ?",
            (args.query, args.limit),
        ).fetchall()
    except Exception:
        rows = conn.execute(
            "SELECT name, price, url FROM parts WHERE name LIKE ? LIMIT ?",
            (f"%{args.query}%", args.limit),
        ).fetchall()
    conn.close()

    for r in rows:
        price = f"${r['price'] * 0.012:.2f}" if r["price"] else "N/A"
        print(f"  {price:>8}  {r['name'][:60]}")
    print(f"\n{len(rows)} results")


def cmd_stats(args):
    """Show database statistics."""
    from src.db.schema import init_db
    conn = init_db()
    total = conn.execute("SELECT COUNT(*) FROM parts").fetchone()[0]
    priced = conn.execute("SELECT COUNT(*) FROM parts WHERE price > 0").fetchone()[0]
    cats = conn.execute("SELECT COUNT(*) FROM categories").fetchone()[0]
    conn.close()
    print(f"Parts:      {total:,}")
    print(f"With price: {priced:,}")
    print(f"Categories: {cats}")


def main():
    parser = argparse.ArgumentParser(
        description="焊武帝 IronEmperor — prompt to hardware project",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command")

    # build
    p_build = sub.add_parser("build", help="Run the full pipeline")
    p_build.add_argument("prompt", help="Project description")
    p_build.add_argument("--json", action="store_true", help="Output JSON")
    p_build.add_argument("-o", "--output", help="Save result to file")

    # serve
    p_serve = sub.add_parser("serve", help="Start web server")
    p_serve.add_argument("--host", default=None)
    p_serve.add_argument("--port", type=int, default=None)
    p_serve.add_argument("--reload", action="store_true")

    # search
    p_search = sub.add_parser("search", help="Search parts database")
    p_search.add_argument("query", help="Search query")
    p_search.add_argument("--limit", type=int, default=20)

    # stats
    sub.add_parser("stats", help="Database statistics")

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        return

    {"build": cmd_build, "serve": cmd_serve, "search": cmd_search, "stats": cmd_stats}[args.command](args)


if __name__ == "__main__":
    main()
