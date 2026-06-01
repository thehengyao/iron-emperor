#!/usr/bin/env python3
"""
Pipeline benchmark — measures per-agent latency, token estimates,
and end-to-end throughput. Outputs machine-readable JSON.

Usage: PYTHONPATH=. python3 benchmark.py [prompt]
"""
import asyncio
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, ".")

from src.agents.orchestrator import Orchestrator
from src.agents.parts_agent import PartsAgent
from src.agents.pcb.pcb_agent import PCBAgent
from src.agents.cad.cad_agent import CADAgent
from src.agents.assembler.assembly_agent import AssemblyAgent
from src.agents.quoter.quoter_agent import QuoterAgent
from dataclasses import asdict


async def benchmark(prompt: str) -> dict:
    t0 = time.time()
    orch = Orchestrator()
    orch.register_agent("parts", PartsAgent())
    orch.register_agent("pcb", PCBAgent())
    orch.register_agent("cad", CADAgent())
    orch.register_agent("assembler", AssemblyAgent())
    orch.register_agent("quoter", QuoterAgent())

    spec = await orch.run(prompt)
    total_ms = int((time.time() - t0) * 1000)

    agent_timings = {}
    for msg in orch.message_log:
        agent_timings[msg.to_agent] = {
            "duration_ms": msg.duration_ms,
            "status": msg.status,
            "error": msg.error,
        }

    result = {
        "prompt": prompt,
        "status": spec.status,
        "total_ms": total_ms,
        "bom_items": len(spec.bom),
        "pcb_connections": len((spec.pcb_design or {}).get("circuit_design", {}).get("connections", [])),
        "cad_files": len(spec.cad_files),
        "assembly_steps": len(spec.assembly.get("steps", [])),
        "total_cost_usd": spec.total_cost,
        "agent_timings": agent_timings,
        "errors": spec.errors,
    }
    return result


if __name__ == "__main__":
    prompt = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "气象站"
    print(f"Benchmarking: '{prompt}'", file=sys.stderr)
    result = asyncio.run(benchmark(prompt))
    print(json.dumps(result, indent=2))

    # Summary
    print(f"\n{'='*50}", file=sys.stderr)
    print(f"Status: {result['status']}", file=sys.stderr)
    print(f"Total: {result['total_ms']/1000:.1f}s | ${result['total_cost_usd']:.2f}", file=sys.stderr)
    print(f"BOM: {result['bom_items']} | PCB: {result['pcb_connections']} conn | ASM: {result['assembly_steps']} steps", file=sys.stderr)
    for agent, t in result["agent_timings"].items():
        status = "✓" if t["status"] == "done" else "✗"
        print(f"  {status} {agent:12} {t['duration_ms']/1000:.1f}s", file=sys.stderr)
