"""
Output validators for each pipeline agent.

Validates structural integrity of agent responses before passing
downstream. Returns (is_valid, errors) tuple. Errors are recoverable
warnings — pipeline continues with partial data.
"""
from typing import Any


def validate_requirements(data: Any) -> tuple[bool, list[str]]:
    """Validate requirements agent output."""
    errors = []
    if not isinstance(data, dict):
        return False, ["Requirements must be a dict"]
    if not data.get("project_name"):
        errors.append("Missing project_name")
    if not data.get("components_needed"):
        errors.append("No components_needed specified")
    elif not isinstance(data["components_needed"], list):
        errors.append("components_needed must be a list")
    return len(errors) == 0, errors


def validate_bom(data: Any) -> tuple[bool, list[str]]:
    """Validate BOM (parts agent output)."""
    errors = []
    if not isinstance(data, list):
        return False, ["BOM must be a list"]
    if len(data) == 0:
        return False, ["BOM is empty"]
    for i, item in enumerate(data[:50]):
        if not isinstance(item, dict):
            errors.append(f"BOM[{i}] is not a dict")
            continue
        if not item.get("name"):
            errors.append(f"BOM[{i}] missing name")
        qty = item.get("quantity", 1)
        if not isinstance(qty, (int, float)) or qty < 1:
            errors.append(f"BOM[{i}] invalid quantity: {qty}")
    unpriced = sum(1 for p in data if not (p.get("price") or p.get("estimated_price")))
    if unpriced > len(data) * 0.5:
        errors.append(f"{unpriced}/{len(data)} parts have no price")
    return len(errors) == 0, errors


def validate_pcb(data: Any) -> tuple[bool, list[str]]:
    """Validate PCB design output."""
    errors = []
    if not isinstance(data, dict):
        return False, ["PCB design must be a dict"]
    circuit = data.get("circuit_design", {})
    connections = circuit.get("connections", [])
    if not connections:
        errors.append("No PCB connections")
    for i, c in enumerate(connections[:100]):
        if not isinstance(c, dict):
            errors.append(f"Connection[{i}] is not a dict")
            continue
        if not (c.get("from") or c.get("from_pin")):
            errors.append(f"Connection[{i}] missing 'from'")
        if not (c.get("to") or c.get("to_pin")):
            errors.append(f"Connection[{i}] missing 'to'")
    layout = data.get("layout", {})
    if layout:
        layers = layout.get("layers", 2)
        if not isinstance(layers, int) or layers < 1 or layers > 16:
            errors.append(f"Invalid layer count: {layers}")
    return len(errors) == 0, errors


def validate_assembly(data: Any) -> tuple[bool, list[str]]:
    """Validate assembly guide output."""
    errors = []
    if not isinstance(data, dict):
        return False, ["Assembly must be a dict"]
    steps = data.get("steps", [])
    if not steps:
        errors.append("No assembly steps")
    for i, step in enumerate(steps[:30]):
        if not isinstance(step, dict):
            errors.append(f"Step[{i}] is not a dict")
            continue
        if not step.get("title"):
            errors.append(f"Step[{i}] missing title")
    return len(errors) == 0, errors


def validate_quote(data: Any) -> tuple[bool, list[str]]:
    """Validate quoter output."""
    errors = []
    if not isinstance(data, dict):
        return False, ["Quote must be a dict"]
    total = data.get("total", 0)
    if not isinstance(total, (int, float)) or total < 0:
        errors.append(f"Invalid total: {total}")
    if data.get("currency") not in ("CNY", None):
        errors.append(f"Expected CNY currency, got {data.get('currency')}")
    return len(errors) == 0, errors


# Registry for dispatch
VALIDATORS = {
    "requirements": validate_requirements,
    "parts": validate_bom,
    "pcb": validate_pcb,
    "assembly": validate_assembly,
    "quote": validate_quote,
}


def validate_stage(stage: str, data: Any) -> tuple[bool, list[str]]:
    """Validate any pipeline stage output. Returns (valid, errors)."""
    validator = VALIDATORS.get(stage)
    if not validator:
        return True, []
    return validator(data)
