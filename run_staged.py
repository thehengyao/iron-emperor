#!/usr/bin/env python3
"""Run the pipeline one agent at a time in separate subprocesses to stay under memory limits.
Each step spawns a fresh Python process so Opus responses don't accumulate in RAM."""
import json, subprocess, sys, os, time

PROMPT = sys.argv[1] if len(sys.argv) > 1 else "自动驾驶无人机"
SF = "/tmp/pipeline_state.json"  # shared state file

def run_step(code: str):
    env = {**os.environ, "PYTHONPATH": "."}
    r = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True, timeout=240)
    if r.stdout.strip():
        print(r.stdout.strip())
    if r.returncode != 0:
        print(f"  STDERR (last 600): {r.stderr[-600:]}")
        raise RuntimeError(f"Step failed (code {r.returncode})")

# Init
json.dump({"prompt": PROMPT}, open(SF, "w"))

# ─── 1: Requirements ───
print("━━━ [1/6] REQUIREMENTS (Opus) ━━━")
t0 = time.time()
run_step(f'''
import json, asyncio, sys; sys.path.insert(0, ".")
from src.agents.orchestrator import Orchestrator
async def main():
    s = json.load(open("{SF}"))
    o = Orchestrator()
    req = await o._analyze_requirements(s["prompt"])
    s["requirements"] = req
    json.dump(s, open("{SF}", "w"))
    print(f"  Project: {{req.get('project_name','?')}}")
    print(f"  Components: {{', '.join(req.get('key_components',[])[:5])}}")
asyncio.run(main())
''')
print(f"  ✓ {time.time()-t0:.1f}s\n")

# ─── 2: Parts ───
print("━━━ [2/6] PARTS (Opus) ━━━")
t0 = time.time()
run_step(f'''
import json, asyncio, sys; sys.path.insert(0, ".")
from src.agents.parts_agent import PartsAgent
from src.agents.orchestrator import AgentMessage
async def main():
    s = json.load(open("{SF}"))
    agent = PartsAgent()
    msg = AgentMessage(from_agent="orchestrator", to_agent="parts",
                       task="select_parts", payload={{"requirements": s["requirements"]}})
    bom = await agent.handle(msg)
    s["bom"] = bom
    json.dump(s, open("{SF}", "w"))
    total = sum((p.get("price") or p.get("estimated_price") or 0) * (p.get("quantity") or 1) for p in bom)
    print(f"  {{len(bom)}} items, ${{total:,.0f}}")
asyncio.run(main())
''')
print(f"  ✓ {time.time()-t0:.1f}s\n")

# ─── 3: PCB ───
print("━━━ [3/6] PCB DESIGN (Opus) ━━━")
t0 = time.time()
run_step(f'''
import json, asyncio, sys; sys.path.insert(0, ".")
from src.agents.pcb.pcb_agent import PCBAgent
from src.agents.orchestrator import AgentMessage
async def main():
    s = json.load(open("{SF}"))
    agent = PCBAgent()
    msg = AgentMessage(from_agent="orchestrator", to_agent="pcb",
                       task="design_pcb", payload={{"requirements": s["requirements"], "bom": s["bom"]}})
    pcb = await agent.handle(msg)
    s["pcb_design"] = pcb
    json.dump(s, open("{SF}", "w"))
    conns = pcb.get("circuit_design", {{}}).get("connections", [])
    print(f"  {{len(conns)}} connections, {{pcb.get('layout',{{}}).get('layers',2)}} layers")
asyncio.run(main())
''')
print(f"  ✓ {time.time()-t0:.1f}s\n")

# ─── 4: CAD ───
print("━━━ [4/6] CAD ENCLOSURE (Opus) ━━━")
t0 = time.time()
run_step(f'''
import json, asyncio, sys; sys.path.insert(0, ".")
from src.agents.cad.cad_agent import CADAgent
from src.agents.orchestrator import AgentMessage
async def main():
    s = json.load(open("{SF}"))
    agent = CADAgent()
    msg = AgentMessage(from_agent="orchestrator", to_agent="cad",
                       task="generate_enclosure", payload={{
                           "requirements": s["requirements"], "bom": s["bom"],
                           "pcb_design": s.get("pcb_design", {{}})
                       }})
    cad = await agent.handle(msg)
    s["cad_files"] = cad.get("cad_files", cad.get("files", []))
    json.dump(s, open("{SF}", "w"))
    print(f"  {{len(s['cad_files'])}} files")
asyncio.run(main())
''')
print(f"  ✓ {time.time()-t0:.1f}s\n")

# ─── 5: Assembly ───
print("━━━ [5/6] ASSEMBLY (Opus) ━━━")
t0 = time.time()
run_step(f'''
import json, asyncio, sys; sys.path.insert(0, ".")
from src.agents.assembler.assembly_agent import AssemblyAgent
from src.agents.orchestrator import AgentMessage
async def main():
    s = json.load(open("{SF}"))
    agent = AssemblyAgent()
    msg = AgentMessage(from_agent="orchestrator", to_agent="assembler",
                       task="create_assembly_plan", payload={{
                           "requirements": s["requirements"], "bom": s["bom"],
                           "pcb_design": s.get("pcb_design", {{}}),
                           "cad_files": s.get("cad_files", [])
                       }})
    asm = await agent.handle(msg)
    s["assembly"] = asm
    json.dump(s, open("{SF}", "w"))
    print(f"  {{len(asm.get('steps',[]))}} steps, {{asm.get('difficulty','?')}}")
asyncio.run(main())
''')
print(f"  ✓ {time.time()-t0:.1f}s\n")

# ─── 6: Quote (pure math, no LLM) ───
print("━━━ [6/6] QUOTE ━━━")
t0 = time.time()
run_step(f'''
import json, asyncio, sys; sys.path.insert(0, ".")
from src.agents.quoter.quoter_agent import QuoterAgent
from src.agents.orchestrator import AgentMessage
async def main():
    s = json.load(open("{SF}"))
    agent = QuoterAgent()
    msg = AgentMessage(from_agent="orchestrator", to_agent="quoter",
                       task="calculate_quote", payload={{
                           "bom": s["bom"],
                           "pcb_design": s.get("pcb_design", {{}}),
                           "cad_files": s.get("cad_files", [])
                       }})
    quote = await agent.handle(msg)
    s["quote"] = quote
    s["total_cost"] = quote.get("total", 0)
    json.dump(s, open("{SF}", "w"))
    print(f"  ${{quote.get('total', 0):,.0f}}")
asyncio.run(main())
''')
print(f"  ✓ {time.time()-t0:.1f}s\n")

# ─── Finalize ───
s = json.load(open(SF))
output = {
    "status": "success",
    "project": {
        "prompt": s["prompt"],
        "requirements": s["requirements"],
        "bom": s["bom"],
        "pcb_design": s.get("pcb_design", {}),
        "cad_files": s.get("cad_files", []),
        "assembly": s.get("assembly", {}),
        "quote": s.get("quote", {}),
        "total_cost": s.get("total_cost", 0),
        "status": "ready",
    },
    "agent_log": [],
}
json.dump(output, open("/tmp/drone-opus.json", "w"))
print(f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
print(f"✅ ALL OPUS — ${s.get('total_cost', 0):,.0f}")
print(f"Saved: /tmp/drone-opus.json")
