"""
FastAPI server — REST + Agent-to-Agent (A2A) endpoints.

POST /build         → full pipeline from prompt to quote
POST /a2a/build     → A2A protocol: agent-to-agent build request
GET  /a2a/discover  → A2A capability advertisement
GET  /search        → search parts database
GET  /stats         → database statistics
GET  /health        → healthcheck
GET  /openapi.json  → OpenAPI 3.1 schema (auto-generated)
"""
import json
import sqlite3
import time
from dataclasses import asdict
from pathlib import Path

from fastapi import FastAPI, Query
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from src.agents.orchestrator import Orchestrator
from src.agents.parts_agent import PartsAgent
from src.agents.pcb.pcb_agent import PCBAgent
from src.agents.cad.cad_agent import CADAgent
from src.agents.assembler.assembly_agent import AssemblyAgent
from src.agents.quoter.quoter_agent import QuoterAgent
from src.db.schema import DB_PATH, init_db

app = FastAPI(
    title="焊武帝 IronEmperor",
    description=(
        "多 agent 硬件设计系统。输入自然语言，输出 BOM、PCB、3D 外壳、组装教程、CNY 报价。"
        "零件来自立创商城，支持 Claude 和 DeepSeek。"
        "Multi-agent hardware design system. Prompt → BOM + PCB + CAD + CNY quote. "
        "Supports REST and Agent-to-Agent (A2A) protocol."
    ),
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

from src.middleware import RequestTracingMiddleware, ConcurrencyLimitMiddleware

app.add_middleware(RequestTracingMiddleware)
app.add_middleware(ConcurrencyLimitMiddleware, max_concurrent=2)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class BuildRequest(BaseModel):
    prompt: str = Field(..., description="Natural language hardware project description")


class AgentLogEntry(BaseModel):
    agent: str
    task: str
    status: str
    duration_ms: int
    error: str | None = None


class ProjectResult(BaseModel):
    """Core project specification returned by the pipeline."""
    prompt: str
    status: str = "planning"
    requirements: dict = {}
    bom: list[dict] = []
    pcb_design: dict | None = None
    cad_files: list[str] = []
    assembly: dict = {}
    quote: dict = {}
    total_cost: float = 0.0
    currency: str = "CNY"
    errors: list[str] = []


class BuildResponse(BaseModel):
    status: str
    project: ProjectResult
    agent_log: list[AgentLogEntry] = []


class A2ABuildRequest(BaseModel):
    """Agent-to-Agent protocol request envelope."""
    task: str = Field("hardware_build", description="Task identifier")
    prompt: str = Field(..., description="Project description")
    callback_url: str | None = Field(None, description="Webhook for async result delivery")
    context: dict = Field(default_factory=dict, description="Upstream agent context")


def create_orchestrator() -> Orchestrator:
    orch = Orchestrator()
    orch.register_agent("parts", PartsAgent())
    orch.register_agent("pcb", PCBAgent())
    orch.register_agent("cad", CADAgent())
    orch.register_agent("assembler", AssemblyAgent())
    orch.register_agent("quoter", QuoterAgent())
    return orch


@app.post("/build", response_model=BuildResponse)
async def build_project(req: BuildRequest):
    """Build a hardware project from a natural language prompt."""
    orch = create_orchestrator()
    try:
        spec = await orch.run(req.prompt)
        return {
            "status": spec.status,
            "project": asdict(spec),
            "agent_log": [
                {
                    "agent": m.to_agent,
                    "task": m.task,
                    "status": m.status,
                    "duration_ms": m.duration_ms,
                    "error": m.error,
                }
                for m in orch.message_log
            ],
        }
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"status": "error", "detail": str(e)},
        )


## ── SSE Streaming Build ──────────────────────────────────────

from starlette.responses import StreamingResponse
import asyncio


@app.post("/build/stream")
async def build_stream(req: BuildRequest):
    """Server-Sent Events stream of build progress. Each event is a stage update."""
    async def event_generator():
        orch = create_orchestrator()
        queue: asyncio.Queue = asyncio.Queue()

        def on_status(msg: str):
            queue.put_nowait(msg)

        orch.on_status = on_status

        async def run_pipeline():
            try:
                spec = await orch.run(req.prompt)
                queue.put_nowait(f"__RESULT__:{json.dumps(asdict(spec))}")
            except Exception as e:
                queue.put_nowait(f"__ERROR__:{str(e)}")
            queue.put_nowait("__DONE__")

        task = asyncio.create_task(run_pipeline())

        while True:
            msg = await queue.get()
            if msg == "__DONE__":
                yield f"event: done\ndata: {{}}\n\n"
                break
            elif msg.startswith("__RESULT__:"):
                payload = msg[len("__RESULT__:"):]
                yield f"event: result\ndata: {payload}\n\n"
            elif msg.startswith("__ERROR__:"):
                yield f"event: error\ndata: {json.dumps({'error': msg[len('__ERROR__'):]})}\n\n"
            else:
                yield f"event: status\ndata: {json.dumps({'message': msg})}\n\n"

        await task

    return StreamingResponse(event_generator(), media_type="text/event-stream")


## ── A2A Protocol ──────────────────────────────────────────────

@app.get("/a2a/discover")
async def a2a_discover():
    """Agent-to-Agent capability discovery. Returns supported tasks and schema refs."""
    return {
        "agent": "iron-emperor",
        "version": "1.0.0",
        "protocol": "a2a/1.0",
        "capabilities": [
            {
                "task": "hardware_build",
                "description": "End-to-end hardware project: BOM, PCB, enclosure, assembly, CNY quote",
                "input_schema": {"$ref": "/openapi.json#/components/schemas/A2ABuildRequest"},
                "output_schema": {"$ref": "/openapi.json#/components/schemas/BuildResponse"},
                "estimated_duration_s": 120,
            },
            {
                "task": "parts_search",
                "description": "Search 立创商城 (LCSC) electronic components",
                "input_schema": {"type": "object", "properties": {"query": {"type": "string"}}},
            },
        ],
    }


@app.post("/a2a/build")
async def a2a_build(req: A2ABuildRequest):
    """Agent-to-Agent build endpoint. Wraps /build with A2A envelope."""
    t0 = time.time()
    orch = create_orchestrator()
    try:
        spec = await orch.run(req.prompt)
        return {
            "protocol": "a2a/1.0",
            "task": req.task,
            "status": "success",
            "duration_s": round(time.time() - t0, 1),
            "result": asdict(spec),
            "agent_log": [
                {"agent": m.to_agent, "task": m.task, "status": m.status,
                 "duration_ms": m.duration_ms, "error": m.error}
                for m in orch.message_log
            ],
            "context": req.context,
        }
    except Exception as e:
        return JSONResponse(status_code=500, content={
            "protocol": "a2a/1.0", "task": req.task,
            "status": "error", "error": str(e),
            "duration_s": round(time.time() - t0, 1),
        })


## ── Parts Database ───────────────────────────────────────────

@app.get("/search")
async def search_parts(
    q: str = Query(..., description="Search query"),
    limit: int = Query(20, ge=1, le=100),
):
    """Search the parts database."""
    conn = init_db()
    conn.row_factory = sqlite3.Row
    
    # Try FTS
    try:
        rows = conn.execute(
            """SELECT p.name, p.url, p.price, p.in_stock, p.image_url, c.name as category
               FROM parts_fts f
               JOIN parts p ON f.rowid = p.id
               LEFT JOIN categories c ON p.category_id = c.id
               WHERE parts_fts MATCH ?
               LIMIT ?""",
            (q, limit),
        ).fetchall()
    except Exception:
        rows = conn.execute(
            """SELECT p.name, p.url, p.price, p.in_stock, p.image_url, c.name as category
               FROM parts p
               LEFT JOIN categories c ON p.category_id = c.id
               WHERE p.name LIKE ?
               LIMIT ?""",
            (f"%{q}%", limit),
        ).fetchall()
    
    conn.close()
    return {"query": q, "count": len(rows), "results": [dict(r) for r in rows]}


@app.get("/stats")
async def db_stats():
    """Get database statistics."""
    conn = init_db()
    total = conn.execute("SELECT COUNT(*) FROM parts").fetchone()[0]
    priced = conn.execute("SELECT COUNT(*) FROM parts WHERE price > 0").fetchone()[0]
    cats = conn.execute("SELECT COUNT(*) FROM categories").fetchone()[0]
    price_stats = conn.execute(
        "SELECT MIN(price), AVG(price), MAX(price) FROM parts WHERE price > 0"
    ).fetchone()
    
    top_cats = conn.execute(
        """SELECT c.name, COUNT(p.id) as count
           FROM categories c
           JOIN parts p ON p.category_id = c.id
           GROUP BY c.id
           ORDER BY count DESC
           LIMIT 15""",
    ).fetchall()
    
    conn.close()
    return {
        "total_parts": total,
        "priced_parts": priced,
        "categories": cats,
        "price_range": {
            "min": price_stats[0],
            "avg": round(price_stats[1], 2) if price_stats[1] else None,
            "max": price_stats[2],
            "currency": "CNY (¥) — 立创商城 (LCSC)",
        },
        "top_categories": [{"name": r[0], "count": r[1]} for r in top_cats],
    }


@app.get("/metrics")
async def metrics():
    """Pipeline performance metrics (agent timings, cache rates, throughput)."""
    from src.metrics import PipelineMetrics
    return PipelineMetrics().snapshot()


@app.get("/health")
async def health():
    db_exists = Path(DB_PATH).exists()
    return {
        "status": "ok" if db_exists else "no_db",
        "db_path": str(DB_PATH),
        "db_exists": db_exists,
    }


# Serve frontend (must come last — catch-all for SPA routing)
_frontend_dist = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"
if _frontend_dist.is_dir():
    # Serve static assets
    app.mount("/assets", StaticFiles(directory=str(_frontend_dist / "assets")), name="assets")

    # SPA fallback — serve index.html for all other routes
    from starlette.responses import FileResponse

    @app.get("/{path:path}")
    async def spa_fallback(path: str):
        index = _frontend_dist / "index.html"
        file = _frontend_dist / path
        if file.is_file():
            return FileResponse(str(file))
        return FileResponse(str(index))
