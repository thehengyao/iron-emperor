"""
Quoter Agent — deterministic cost breakdown in CNY.

Computes costs from BOM (sourced in CNY from 立创商城/LCSC),
adds PCB fab via 嘉立创, 3D printing, and shipping estimates.
No LLM needed — pure arithmetic.
"""
from src.agents.orchestrator import AgentMessage


class QuoterAgent:
    """Calculates project cost — no LLM, just math. All prices in CNY (¥)."""

    # Base costs in CNY
    PCB_BASE_CNY = 30.0          # 嘉立创 5-pack, small board
    PCB_PER_SQCM_CNY = 1.5      # per sq cm over 25 sq cm
    PRINT_PER_GRAM_CNY = 0.15   # PLA cost/gram (domestic bureau)
    PRINT_BASE_GRAMS = 40       # estimated enclosure weight
    SHIPPING_CNY = 15.0          # domestic flat rate (顺丰/菜鸟)
    ASSEMBLY_FEE_CNY = 0         # DIY
    PLATFORM_FEE_PCT = 0.05     # 5%

    async def handle(self, msg: AgentMessage) -> dict:
        bom = msg.payload.get("bom", [])
        cad = msg.payload.get("cad", {})
        pcb = msg.payload.get("pcb_design", msg.payload.get("pcb", {}))

        # ── Parts cost (CNY from DB) ──
        parts_cny = 0.0
        items = []
        for part in bom:
            price = part.get("price", part.get("estimated_price", 0)) or 0
            qty = part.get("quantity", 1)
            line = price * qty
            parts_cny += line
            items.append({
                "name": part.get("name", "Unknown"),
                "unit_price_cny": round(price, 2),
                "quantity": qty,
                "total_cny": round(line, 2),
            })

        # ── PCB fabrication (嘉立创) ──
        dims = pcb.get("layout", pcb.get("dimensions", {}))
        board_w = dims.get("width", dims.get("dimensions_mm", {}).get("width", 60))
        board_h = dims.get("height", dims.get("dimensions_mm", {}).get("height", 40))
        if isinstance(board_w, dict): board_w = board_w.get("width", 60)
        if isinstance(board_h, dict): board_h = board_h.get("height", 40)
        board_area = board_w * board_h / 100  # sq cm
        pcb_cny = self.PCB_BASE_CNY
        if board_area > 25:
            pcb_cny += (board_area - 25) * self.PCB_PER_SQCM_CNY

        # ── 3D printing ──
        ps = cad.get("print_settings", {})
        grams = ps.get("estimated_weight_grams", self.PRINT_BASE_GRAMS)
        print_cny = grams * self.PRINT_PER_GRAM_CNY

        # ── Assembly / Shipping ──
        asm_cny = self.ASSEMBLY_FEE_CNY
        ship_cny = self.SHIPPING_CNY

        subtotal = parts_cny + pcb_cny + print_cny + asm_cny + ship_cny
        platform = subtotal * self.PLATFORM_FEE_PCT
        total = subtotal + platform

        return {
            "breakdown": {
                "parts": {"total_cny": round(parts_cny, 2), "items": items},
                "pcb_fabrication": {
                    "total_cny": round(pcb_cny, 2),
                    "board_size_mm": f"{board_w}x{board_h}",
                    "quantity": 5,
                    "vendor": "嘉立创 (JLCPCB China)",
                },
                "3d_printing": {
                    "total_cny": round(print_cny, 2),
                    "weight_grams": grams,
                    "material": ps.get("material", "PLA"),
                },
                "assembly": {"total_cny": round(asm_cny, 2), "type": "DIY"},
                "shipping": {"total_cny": round(ship_cny, 2), "method": "国内顺丰"},
                "platform_fee": {
                    "total_cny": round(platform, 2),
                    "rate": f"{self.PLATFORM_FEE_PCT * 100:.0f}%",
                },
            },
            "subtotal": round(subtotal, 2),
            "total": round(total, 2),
            "currency": "CNY",
            "delivery": "3-5天（零件）+ 2-3天（PCB打板）",
            "notes": [
                "零件来源：立创商城 (LCSC)，价格单位：人民币（¥）",
                "PCB 打板：嘉立创，5片起单",
                "3D 打印：国内服务商，PLA 材料",
                "组装：自行焊接，附详细教程",
            ],
        }
