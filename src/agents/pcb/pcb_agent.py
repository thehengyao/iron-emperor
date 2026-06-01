"""
PCB Design Agent — three-stage circuit design pipeline.

Stage 1: Circuit design (component interconnections, power rails)
Stage 2: KiCad schematic generation (.kicad_sch format)
Stage 3: Board layout (layers, dimensions, trace widths, mounting)

Each stage uses Claude Opus with structured JSON output.
Schematic is saved to output/pcb/ directory.
"""
import json
from pathlib import Path

from src.agents.orchestrator import AgentMessage, parse_json_response, MODEL
from src.llm_client import get_llm_client

OUTPUT_DIR = Path("output/pcb")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


class PCBAgent:
    def __init__(self):
        self.client = get_llm_client()

    async def handle(self, msg: AgentMessage) -> dict:
        requirements = msg.payload.get("requirements", {})
        bom = msg.payload.get("bom", [])

        # Slim BOM for context efficiency
        part_names = [p.get("name", "") for p in bom[:25]]

        # Stage 1: Circuit design
        print("      Generating circuit design...")
        circuit = await self._design_circuit(requirements, part_names)

        # Stage 2: KiCad schematic
        print("      Generating KiCad schematic...")
        schematic = await self._generate_schematic(requirements, part_names, circuit)
        sch_path = OUTPUT_DIR / "project.kicad_sch"
        sch_path.write_text(schematic)

        # Stage 3: Board layout
        print("      Generating board layout...")
        layout = await self._generate_layout(requirements, part_names, circuit)

        return {
            "circuit_design": circuit,
            "schematic_kicad": schematic,
            "schematic_path": str(sch_path),
            "layout": layout,
        }

    async def _design_circuit(self, requirements: dict, parts: list[str]) -> dict:
        response = self.client.messages.create(
            model=MODEL, max_tokens=8192,
            system="""You are a PCB design engineer. Design the circuit interconnections.

Return ONLY JSON (no markdown fences):
{
    "connections": [
        {"from": "Component.Pin", "to": "Component.Pin", "type": "I2C|SPI|UART|PWM|analog|power|GPIO"}
    ],
    "power_rails": [
        {"name": "3V3", "voltage": "3.3V", "source": "voltage regulator", "max_current_ma": 500}
    ],
    "board_dimensions": {"width": 60, "height": 40},
    "notes": "any design considerations"
}

Be thorough with connections. Include power, ground, data, and control lines.""",
            messages=[{
                "role": "user",
                "content": f"Project: {requirements.get('project_name','')}\nParts: {', '.join(parts)}",
            }],
        )
        return parse_json_response(response.content[0].text)

    async def _generate_schematic(self, requirements: dict, parts: list[str], circuit: dict) -> str:
        conn_summary = f"{len(circuit.get('connections',[]))} connections, {len(circuit.get('power_rails',[]))} power rails"
        response = self.client.messages.create(
            model=MODEL, max_tokens=8192,
            system="""You are a KiCad expert. Generate a .kicad_sch schematic file.

Return ONLY the KiCad schematic content (no markdown fences, no explanation).
Start with (kicad_sch and end with the closing parenthesis.
Include component symbols, wire connections, power flags, and labels.""",
            messages=[{
                "role": "user",
                "content": f"Project: {requirements.get('project_name','')}\nParts: {', '.join(parts[:15])}\nCircuit: {conn_summary}",
            }],
        )
        text = response.content[0].text.strip()
        # Extract schematic content (may be in fences)
        if "```" in text:
            import re
            m = re.search(r'```(?:\w*)\s*\n(.*?)```', text, re.DOTALL)
            if m:
                return m.group(1).strip()
        return text

    async def _generate_layout(self, requirements: dict, parts: list[str], circuit: dict) -> dict:
        response = self.client.messages.create(
            model=MODEL, max_tokens=4096,
            system="""You are a PCB layout engineer. Design the board layout.

Return ONLY JSON (no markdown fences):
{
    "layers": 2,
    "dimensions_mm": {"width": 60, "height": 40},
    "mounting_holes": 4,
    "trace_width_mm": {"signal": 0.25, "power": 0.5},
    "copper_weight_oz": 1,
    "board_thickness_mm": 1.6,
    "surface_finish": "HASL",
    "notes": "layout considerations"
}""",
            messages=[{
                "role": "user",
                "content": f"Project: {requirements.get('project_name','')}\nParts: {len(parts)}\nConnections: {len(circuit.get('connections',[]))}",
            }],
        )
        return parse_json_response(response.content[0].text)
