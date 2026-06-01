"""
Assembly Agent — step-by-step build guide generation.

Receives a slimmed payload (part names + PCB summary) and produces
a comprehensive assembly guide with tools, safety, testing, troubleshooting.
"""
import json

from src.agents.orchestrator import AgentMessage, parse_json_response, MODEL
from src.llm_client import get_llm_client


class AssemblyAgent:
    def __init__(self):
        self.client = get_llm_client()

    async def handle(self, msg: AgentMessage) -> dict:
        requirements = msg.payload.get("requirements", {})
        bom = msg.payload.get("bom", [])
        pcb = msg.payload.get("pcb_design", msg.payload.get("pcb", {}))
        cad_files = msg.payload.get("cad_files", [])

        # Slim the payload to avoid blowing context
        part_names = [f"{p.get('name','')} x{p.get('quantity',1)}" for p in bom[:30]]
        pcb_summary = {
            "connections": len(pcb.get("circuit_design", {}).get("connections", [])),
            "layers": pcb.get("layout", {}).get("layers", 2),
        }

        response = self.client.messages.create(
            model=MODEL,
            max_tokens=8192,
            system="""You are a hardware assembly expert. Write thorough build instructions.

Return ONLY JSON (no markdown fences). Structure:
{
    "difficulty": "beginner|intermediate|advanced",
    "estimated_time_hours": 4.0,
    "tools_required": [{"name": "soldering iron", "notes": "temperature-controlled"}],
    "safety_warnings": ["Wear safety glasses when soldering"],
    "steps": [
        {
            "step": 1,
            "title": "Step Title",
            "description": "Detailed instructions...",
            "substeps": ["First do this", "Then do that"],
            "tips": ["Pro tip"]
        }
    ],
    "testing": [
        {"test": "Power-on test", "procedure": "Connect power...", "expected_result": "LED lights up"}
    ],
    "troubleshooting": [
        {"problem": "No power", "solutions": ["Check connections", "Verify polarity"]}
    ]
}

Include 8-15 steps. Cover: preparation, PCB soldering, component mounting, wiring, enclosure assembly, firmware, testing.""",
            messages=[{
                "role": "user",
                "content": (
                    f"Project: {requirements.get('project_name', 'Hardware Project')}\n"
                    f"Complexity: {requirements.get('estimated_complexity', 'intermediate')}\n"
                    f"Parts ({len(part_names)}): {', '.join(part_names)}\n"
                    f"PCB: {pcb_summary['connections']} connections, {pcb_summary['layers']} layers\n"
                    f"CAD files: {len(cad_files)} enclosure files"
                ),
            }],
        )
        return parse_json_response(response.content[0].text)
