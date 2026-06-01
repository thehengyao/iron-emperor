"""
CAD Agent — generates 3D-printable STL enclosures via OpenSCAD.

Uses Claude to generate parametric OpenSCAD code, then compiles to STL
if OpenSCAD is installed.
"""
import json
import subprocess
from pathlib import Path

from src.agents.orchestrator import AgentMessage, MODEL
from src.llm_client import get_llm_client

OUTPUT_DIR = Path("output/cad")


class CADAgent:
    def __init__(self):
        self.client = get_llm_client()

    async def handle(self, msg: AgentMessage) -> dict:
        requirements = msg.payload.get("requirements", {})
        bom = msg.payload.get("bom", [])
        pcb = msg.payload.get("pcb", {})

        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

        # Get board dimensions from PCB agent or use defaults
        dims = pcb.get("dimensions", {"width": 60, "height": 40})

        # Generate OpenSCAD code
        print("      Generating OpenSCAD enclosure...")
        scad_code = await self._generate_openscad(requirements, bom, dims)
        scad_path = OUTPUT_DIR / "enclosure.scad"
        scad_path.write_text(scad_code)

        # Generate lid separately
        print("      Generating lid...")
        lid_code = await self._generate_lid(requirements, dims)
        lid_path = OUTPUT_DIR / "lid.scad"
        lid_path.write_text(lid_code)

        files = [str(scad_path), str(lid_path)]

        # Try to compile to STL
        for scad_file in [scad_path, lid_path]:
            stl_file = scad_file.with_suffix(".stl")
            if await self._compile_stl(scad_file, stl_file):
                files.append(str(stl_file))

        return {
            "files": files,
            "scad_source": str(scad_path),
            "dimensions": dims,
            "print_settings": {
                "layer_height": 0.2,
                "infill": "20%",
                "supports": "minimal",
                "material": "PLA",
                "estimated_time_hours": 3,
                "estimated_weight_grams": 45,
            },
            "notes": "OpenSCAD source included — modify and re-export as needed",
        }

    async def _generate_openscad(self, requirements: dict, bom: list, dims: dict) -> str:
        """Generate parametric OpenSCAD code for the enclosure body."""
        audience = requirements.get("target_audience", "general")
        safety = requirements.get("safety_requirements", [])
        
        response = self.client.messages.create(
            model=MODEL,
            max_tokens=6000,
            system=f"""You are an expert mechanical/CAD designer. Generate OpenSCAD code for a 3D-printable enclosure.

Design constraints:
- PCB dimensions: {dims.get('width', 60)}mm x {dims.get('height', 40)}mm
- Target audience: {audience}
- Safety: {', '.join(safety) if safety else 'standard'}
- Wall thickness: 2.5mm
- Must be printable without supports (or minimal supports)

Requirements:
- Main body with PCB mounting standoffs (M3, 5mm height)
- Cutouts for USB port, buttons, LEDs, sensors, camera (as needed by BOM)
- Ventilation slots if the project generates heat
- Rounded corners (fillet radius 3mm+) for safety
- Snap-fit tabs or screw posts for the lid
- Parametric design: key dimensions as variables at top of file
- Clear comments explaining each section

Output ONLY valid OpenSCAD code. No markdown, no explanation outside comments.""",
            messages=[{
                "role": "user",
                "content": f"Project: {json.dumps(requirements)}\nBOM: {json.dumps(bom)}",
            }],
        )
        text = response.content[0].text.strip()
        # Strip markdown fences if present
        if text.startswith("```"):
            lines = text.split("\n")
            text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
        return text

    async def _generate_lid(self, requirements: dict, dims: dict) -> str:
        """Generate the lid as a separate OpenSCAD file."""
        response = self.client.messages.create(
            model=MODEL,
            max_tokens=3000,
            system=f"""Generate OpenSCAD code for a LID that fits the enclosure body.

Enclosure inner dimensions: {dims.get('width', 60) + 5}mm x {dims.get('height', 40) + 5}mm
Wall thickness: 2.5mm

The lid should:
- Have a lip that fits inside the body walls (0.3mm tolerance)
- Include snap-fit clips or screw holes matching the body
- Have ventilation if needed
- Include text label on top (project name)
- Rounded edges matching the body

Output ONLY valid OpenSCAD code.""",
            messages=[{
                "role": "user",
                "content": f"Project: {json.dumps(requirements)}",
            }],
        )
        text = response.content[0].text.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
        return text

    async def _compile_stl(self, scad_path: Path, stl_path: Path) -> bool:
        """Compile OpenSCAD to STL if CLI is available."""
        try:
            result = subprocess.run(
                ["openscad", "-o", str(stl_path), str(scad_path)],
                capture_output=True, text=True, timeout=120,
            )
            if result.returncode == 0:
                print(f"      ✅ Compiled: {stl_path.name}")
                return True
            else:
                print(f"      ⚠ OpenSCAD error: {result.stderr[:200]}")
                return False
        except FileNotFoundError:
            print("      ℹ OpenSCAD not installed — .scad source saved")
            return False
        except subprocess.TimeoutExpired:
            print("      ⚠ OpenSCAD compile timed out")
            return False
