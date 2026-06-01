"""
Pipeline unit + integration tests.

Run: python -m pytest tests/ -v
Or:  make test
"""
import json
import sys
import sqlite3
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.agents.orchestrator import parse_json_response, _clean_json, _repair_truncated_json
from src.agents.parts_agent import PartsAgent
from src.agents.quoter.quoter_agent import QuoterAgent
from src.agents.orchestrator import AgentMessage
from src.types import BOMItem, QuoteBreakdown


# ── JSON Parser Tests ────────────────────────────────────────

class TestJsonParser:
    def test_direct_json(self):
        assert parse_json_response('{"a": 1}') == {"a": 1}

    def test_json_array(self):
        assert parse_json_response('[1, 2, 3]') == [1, 2, 3]

    def test_fenced_json(self):
        text = '```json\n{"key": "value"}\n```'
        assert parse_json_response(text) == {"key": "value"}

    def test_prose_before_json(self):
        text = 'Here is the result:\n\n{"data": true}'
        assert parse_json_response(text) == {"data": True}

    def test_trailing_comma(self):
        text = '{"a": 1, "b": 2,}'
        assert parse_json_response(text) == {"a": 1, "b": 2}

    def test_truncated_fence(self):
        text = '```json\n{"layers": 4, "dims": {"w": 75}}'
        result = parse_json_response(text)
        assert result["layers"] == 4

    def test_truncated_mid_array(self):
        text = '```json\n[{"name": "a"}, {"name": "b"'
        result = parse_json_response(text)
        assert isinstance(result, list)
        assert len(result) >= 1

    def test_line_comments(self):
        text = '{"a": 1, // comment\n"b": 2}'
        assert _clean_json(text).replace('\n', '') in ['{"a": 1, "b": 2}', '{"a": 1,"b": 2}']


# ── FTS Sanitizer Tests ─────────────────────────────────────

class TestFTSSanitizer:
    def test_strip_parenthetical(self):
        tokens = PartsAgent._sanitize_fts("Flight controller (Pixhawk or similar)")
        assert "flight" in tokens
        assert "controller" in tokens
        assert "or" not in tokens
        assert "similar" not in tokens

    def test_strip_hyphens(self):
        tokens = PartsAgent._sanitize_fts("NEO-M8N GPS Module")
        assert any("neo" in t or "m8n" in t or "gps" in t for t in tokens)

    def test_stop_words(self):
        tokens = PartsAgent._sanitize_fts("A module for the sensor")
        assert "a" not in tokens
        assert "for" not in tokens
        assert "the" not in tokens


# ── Quoter Tests ─────────────────────────────────────────────

class TestQuoter:
    def test_empty_bom(self):
        import asyncio
        msg = AgentMessage("t", "q", "q", {"bom": []})
        result = asyncio.run(QuoterAgent().handle(msg))
        assert result["currency"] == "CNY"
        assert result["total"] >= 0

    def test_bom_pricing(self):
        import asyncio
        msg = AgentMessage("t", "q", "q", {
            "bom": [
                {"name": "LED", "price": 0.5, "quantity": 5},
                {"name": "Resistor", "price": 0.1, "quantity": 10},
            ]
        })
        result = asyncio.run(QuoterAgent().handle(msg))
        parts_cny = result["breakdown"]["parts"]["total_cny"]
        # 2.5 + 1.0 = 3.5 CNY
        assert abs(parts_cny - 3.5) < 0.1
        assert result["total"] > parts_cny  # includes fees


# ── Type Model Tests ─────────────────────────────────────────

class TestTypes:
    def test_bom_item_cost(self):
        item = BOMItem(name="ESP32", price=15.0, quantity=2)
        assert abs(item.unit_cost_cny - 15.0) < 0.01
        assert abs(item.line_total_cny - 30.0) < 0.01

    def test_quote_breakdown(self):
        bd = QuoteBreakdown(parts_usd=100, pcb_fab_usd=10, platform_fee_usd=11)
        assert bd.subtotal == 110
        assert bd.total == 121


# ── Repair Tests ─────────────────────────────────────────────

class TestRepair:
    def test_balanced_braces(self):
        text = '{"a": {"b": 1}'
        result = _repair_truncated_json(text)
        parsed = json.loads(result)
        assert parsed["a"]["b"] == 1

    def test_trailing_key(self):
        text = '{"a": 1, "b"'
        result = _repair_truncated_json(text)
        parsed = json.loads(result)
        assert parsed["a"] == 1


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
