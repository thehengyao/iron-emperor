# Agent-to-Agent (A2A) Protocol

## Overview

焊武帝 IronEmperor exposes an A2A interface that allows external agents to invoke hardware design as a capability. The protocol follows a request-response pattern with optional async callbacks.

## Discovery

```
GET /a2a/discover
```

Returns agent identity and supported capabilities:

```json
{
  "agent": "iron-emperor",
  "version": "1.0.0",
  "protocol": "a2a/1.0",
  "capabilities": [
    {
      "task": "hardware_build",
      "description": "End-to-end hardware project: BOM, PCB, enclosure, assembly, quote",
      "input_schema": {"$ref": "/openapi.json#/components/schemas/A2ABuildRequest"},
      "estimated_duration_s": 120
    }
  ]
}
```

## Build Request

```
POST /a2a/build
Content-Type: application/json

{
  "task": "hardware_build",
  "prompt": "带 GPS 和 FPV 摄像头的自动驾驶无人机",
  "callback_url": "https://caller-agent.example.com/webhook",
  "context": {
    "session_id": "abc-123",
    "upstream_agent": "project-planner"
  }
}
```

### Fields

| Field          | Type   | Required | Description                                    |
|----------------|--------|----------|------------------------------------------------|
| `task`         | string | yes      | Must match a capability task id                |
| `prompt`       | string | yes      | Natural language project description           |
| `callback_url` | string | no       | Webhook for async delivery (future)            |
| `context`      | object | no       | Opaque context returned unchanged in response  |

## Build Response

```json
{
  "protocol": "a2a/1.0",
  "task": "hardware_build",
  "status": "success",
  "duration_s": 94.2,
  "result": {
    "prompt": "自动驾驶无人机",
    "requirements": { ... },
    "bom": [ ... ],
    "pcb_design": { ... },
    "cad_files": ["output/cad/body.scad", "output/cad/lid.scad"],
    "assembly": { ... },
    "quote": {
      "total": 303.90,
      "currency": "CNY",
      "breakdown": { ... }
    },
    "total_cost": 303.90
  },
  "agent_log": [
    { "agent": "parts", "task": "select_parts", "status": "done", "duration_ms": 29600 },
    { "agent": "pcb", "task": "design_pcb", "status": "done", "duration_ms": 118400 }
  ],
  "context": { "session_id": "abc-123", "upstream_agent": "project-planner" }
}
```

## Internal Agent Protocol

Agents communicate via typed `AgentMessage` envelopes:

```python
@dataclass
class AgentMessage:
    from_agent: str          # sender id
    to_agent: str            # target agent id
    task: str                # task identifier
    payload: dict            # task-specific data
    status: str = "pending"  # pending → in_progress → done | error
    result: Any = None       # populated on completion
    error: str | None = None
    duration_ms: int = 0     # wall-clock execution time
```

### Dispatch Flow

```
Orchestrator
  ├─ analyze_requirements(prompt)  →  structured spec
  ├─ dispatch("parts",     {requirements})         →  BOM[]
  ├─ dispatch("pcb",       {requirements, bom})    →  PCBDesign
  ├─ dispatch("cad",       {requirements, bom, pcb})  →  CADFiles[]
  ├─ dispatch("assembler", {requirements, bom, pcb, cad})  →  Assembly
  └─ dispatch("quoter",    {bom, pcb, cad})        →  Quote
```

Each agent receives an `AgentMessage`, processes it via `async handle(msg)`, and returns a result dict. The orchestrator manages timing, error handling, and result aggregation.

## Error Handling

| HTTP | Status    | Meaning                        |
|------|-----------|--------------------------------|
| 200  | `success` | Pipeline completed             |
| 200  | `ready`   | Project spec ready             |
| 500  | `error`   | Agent failure (see error field)|

Agent-level errors are captured in `agent_log[].error` — the pipeline continues with empty results for failed agents.

## A2A Integration

The A2A endpoint allows any external agent to invoke hardware builds:

```
Agent receives "帮我设计一个气象站"
  → calls POST /a2a/build with prompt
  → receives full project spec
  → presents results to user
```

See `SKILL.md` for integration instructions.
