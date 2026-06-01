#!/usr/bin/env bash
set -euo pipefail

echo "── 焊武帝 IronEmperor Setup ──"

# Python deps
echo "[1/4] Installing Python dependencies..."
pip3 install -r requirements.txt

# Frontend
if command -v node &>/dev/null; then
    echo "[2/4] Building frontend..."
    cd frontend && npm install && npm run build && cd ..
else
    echo "[2/4] SKIP: Node.js not found (frontend build optional)"
fi

# Database
if [ ! -f parts.db ]; then
    echo "[3/4] No parts.db found. Run 'make scrape' to build the parts database."
    echo "       (Scrapes 立创商城 via 立创EDA Pro API)"
else
    echo "[3/4] parts.db exists ($(sqlite3 parts.db 'SELECT COUNT(*) FROM parts') parts)"
fi

# API key check
if [ -n "${ANTHROPIC_API_KEY:-}" ]; then
    echo "[4/4] Anthropic API key detected ✓"
elif [ -n "${DEEPSEEK_API_KEY:-}" ]; then
    echo "[4/4] DeepSeek API key detected ✓  (HWB_MODEL=${HWB_MODEL:-deepseek-chat})"
else
    echo "[4/4] WARNING: No API key set. Export ANTHROPIC_API_KEY or DEEPSEEK_API_KEY."
fi

echo ""
echo "── Ready ──"
echo "  make serve                          → Start web UI + API on :8000"
echo "  make run PROMPT='自动驾驶无人机'    → CLI build (Claude)"
echo "  make run-deepseek PROMPT='...'      → CLI build (DeepSeek)"
echo "  make scrape                         → Build parts database (立创商城)"
