"""
Typed data models for the hardware builder pipeline.

All inter-agent data flows through these types for validation
and IDE support. JSON-serializable via dataclasses.asdict().
"""
from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class Complexity(str, Enum):
    BEGINNER = "beginner"
    INTERMEDIATE = "intermediate"
    ADVANCED = "advanced"


class ConnectionType(str, Enum):
    I2C = "I2C"
    SPI = "SPI"
    UART = "UART"
    PWM = "PWM"
    ANALOG = "analog"
    POWER = "power"
    GPIO = "GPIO"
    USB = "USB"
    CAN = "CAN"


# ── Requirements ──────────────────────────────────────────────

@dataclass
class Requirements:
    project_name: str = ""
    target_audience: str = ""
    core_function: str = ""
    components_needed: list[str] = field(default_factory=list)
    size_constraint: str = "medium"
    battery_powered: bool = False
    wireless_needed: bool = False
    display_needed: bool = False
    estimated_complexity: str = "intermediate"
    safety_requirements: list[str] = field(default_factory=list)
    special_notes: str = ""


# ── BOM ───────────────────────────────────────────────────────

@dataclass
class BOMItem:
    name: str
    quantity: int = 1
    price: Optional[float] = None          # CNY from LCSC
    estimated_price: Optional[float] = None # CNY estimated
    url: Optional[str] = None
    category: str = ""
    reason: str = ""
    in_stock: bool = True

    @property
    def unit_cost_cny(self) -> float:
        return self.price or self.estimated_price or 0.0

    @property
    def line_total_cny(self) -> float:
        return self.unit_cost_cny * self.quantity


# ── PCB ───────────────────────────────────────────────────────

@dataclass
class Connection:
    from_pin: str  # "Component.Pin"
    to_pin: str
    conn_type: str = "GPIO"


@dataclass
class PowerRail:
    name: str
    voltage: str
    source: str = ""
    max_current_ma: int = 0


@dataclass
class BoardLayout:
    layers: int = 2
    width_mm: float = 60.0
    height_mm: float = 40.0
    mounting_holes: int = 4
    trace_signal_mm: float = 0.25
    trace_power_mm: float = 0.5
    surface_finish: str = "HASL"


@dataclass
class PCBDesign:
    connections: list[Connection] = field(default_factory=list)
    power_rails: list[PowerRail] = field(default_factory=list)
    layout: Optional[BoardLayout] = None
    schematic_path: str = ""


# ── Assembly ──────────────────────────────────────────────────

@dataclass
class AssemblyStep:
    step: int
    title: str
    description: str = ""
    substeps: list[str] = field(default_factory=list)
    tips: list[str] = field(default_factory=list)


@dataclass
class TestProcedure:
    test: str
    procedure: str = ""
    expected_result: str = ""


@dataclass
class AssemblyGuide:
    difficulty: str = "intermediate"
    estimated_time_hours: float = 2.0
    tools_required: list[dict] = field(default_factory=list)
    safety_warnings: list[str] = field(default_factory=list)
    steps: list[AssemblyStep] = field(default_factory=list)
    testing: list[TestProcedure] = field(default_factory=list)
    troubleshooting: list[dict] = field(default_factory=list)


# ── Quote ─────────────────────────────────────────────────────

@dataclass
class QuoteBreakdown:
    parts_cny: float = 0.0
    pcb_fab_cny: float = 0.0
    printing_cny: float = 0.0
    assembly_cny: float = 0.0
    shipping_cny: float = 0.0
    platform_fee_cny: float = 0.0

    @property
    def subtotal(self) -> float:
        return (self.parts_cny + self.pcb_fab_cny + self.printing_cny +
                self.assembly_cny + self.shipping_cny)

    @property
    def total(self) -> float:
        return self.subtotal + self.platform_fee_cny


@dataclass
class Quote:
    breakdown: QuoteBreakdown = field(default_factory=QuoteBreakdown)
    total: float = 0.0
    currency: str = "CNY"
    delivery: str = ""
    notes: list[str] = field(default_factory=list)
