# 焊武帝 IronEmperor — Skill Manifest

## Overview

焊武帝 IronEmperor exposes an Agent-to-Agent (A2A) endpoint that allows any agent to invoke hardware design as a capability.

Give it a prompt, get back:
- Bill of Materials (BOM) with CNY prices from 立创商城
- PCB schematic + layout (KiCad format)
- 3D enclosure (OpenSCAD / STL)
- Step-by-step assembly guide
- Cost breakdown in CNY (¥)

## Endpoints

### Discovery
```
GET /a2a/discover
```

### Build
```
POST /a2a/build
{
  "task": "hardware_build",
  "prompt": "自动驾驶无人机",
  "callback_url": null,
  "context": {}
}
```

## Setup

```bash
git clone https://github.com/thehengyao/iron-emperor.git
cd iron-emperor
pip3 install -r requirements.txt

# Claude
export ANTHROPIC_API_KEY=sk-ant-...

# 或 DeepSeek
export DEEPSEEK_API_KEY=sk-...
export HWB_MODEL=deepseek-chat

make scrape   # 建零件数据库（可选，不建也能跑）
make serve    # → http://localhost:8000
```
