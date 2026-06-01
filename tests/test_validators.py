"""Tests for output validators."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.validators import (
    validate_requirements, validate_bom, validate_pcb,
    validate_assembly, validate_quote, validate_stage,
)


class TestRequirementsValidator:
    def test_valid(self):
        ok, errs = validate_requirements({
            "project_name": "Drone",
            "components_needed": ["ESC", "motor"],
        })
        assert ok and not errs

    def test_missing_name(self):
        ok, errs = validate_requirements({"components_needed": ["a"]})
        assert not ok
        assert any("project_name" in e for e in errs)

    def test_not_dict(self):
        ok, errs = validate_requirements([1, 2])
        assert not ok


class TestBOMValidator:
    def test_valid(self):
        ok, errs = validate_bom([
            {"name": "ESP32", "quantity": 1, "price": 500},
            {"name": "LED", "quantity": 10, "price": 10},
        ])
        assert ok and not errs

    def test_empty(self):
        ok, errs = validate_bom([])
        assert not ok

    def test_missing_name(self):
        ok, errs = validate_bom([{"quantity": 1}])
        assert not ok

    def test_half_unpriced(self):
        items = [{"name": f"P{i}", "quantity": 1} for i in range(10)]
        items[:3] = [{"name": f"P{i}", "quantity": 1, "price": 100} for i in range(3)]
        ok, errs = validate_bom(items)
        assert any("no price" in e for e in errs)


class TestPCBValidator:
    def test_valid(self):
        ok, errs = validate_pcb({
            "circuit_design": {"connections": [{"from": "A.1", "to": "B.1"}]},
            "layout": {"layers": 4},
        })
        assert ok and not errs

    def test_no_connections(self):
        ok, errs = validate_pcb({"circuit_design": {}})
        assert not ok

    def test_bad_layers(self):
        ok, errs = validate_pcb({
            "circuit_design": {"connections": [{"from": "A", "to": "B"}]},
            "layout": {"layers": 32},
        })
        assert not ok


class TestAssemblyValidator:
    def test_valid(self):
        ok, errs = validate_assembly({
            "steps": [{"step": 1, "title": "Solder"}],
        })
        assert ok

    def test_no_steps(self):
        ok, errs = validate_assembly({"steps": []})
        assert not ok


class TestQuoteValidator:
    def test_valid(self):
        ok, errs = validate_quote({"total": 2800.0, "currency": "CNY"})
        assert ok

    def test_negative(self):
        ok, errs = validate_quote({"total": -5})
        assert not ok


class TestRegistryDispatch:
    def test_unknown_stage(self):
        ok, errs = validate_stage("unknown", {})
        assert ok  # no validator = pass

    def test_dispatch(self):
        ok, errs = validate_stage("requirements", {"project_name": "X", "components_needed": ["a"]})
        assert ok
