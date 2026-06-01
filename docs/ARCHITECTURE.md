# Architecture

## System Overview

```
┌──────────────────────────────────────────────────────────────────────┐
│                         HARDWARE BUILDER                             │
│                                                                      │
│   ┌──────────┐     ┌───────────────────────────────────────────┐    │
│   │  FastAPI  │────▶│              ORCHESTRATOR                 │    │
│   │  Server   │     │                                           │    │
│   │          ◀──────│  1. Parse prompt → requirements           │    │
│   │  /build   │     │  2. Dispatch to agents (sequential)       │    │
│   │  /a2a/*   │     │  3. Aggregate results → ProjectSpec       │    │
│   └──────────┘     └──────┬──────┬──────┬──────┬──────┬────────┘    │
│                           │      │      │      │      │              │
│              ┌────────────▼┐ ┌───▼────┐ ┌▼─────┐ ┌───▼──┐ ┌──▼───┐ │
│              │    PARTS    │ │  PCB   │ │ CAD  │ │ ASM  │ │QUOTE │ │
│              │    AGENT    │ │ AGENT  │ │AGENT │ │AGENT │ │AGENT │ │
│              │             │ │        │ │      │ │      │ │      │ │
│              │ FTS5 search │ │Circuit │ │SCAD  │ │Steps │ │ Math │ │
│              │ LLM select  │ │Schema  │ │Body  │ │Tools │ │  No  │ │
│              │ BOM output  │ │Layout  │ │Lid   │ │Guide │ │ LLM  │ │
│              └──────┬──────┘ └───┬────┘ └──┬───┘ └──┬───┘ └──┬───┘ │
│                     │            │         │        │         │      │
│              ┌──────▼──────┐ ┌───▼────┐ ┌──▼───┐   │         │      │
│              │  SQLite DB  │ │ KiCad  │ │ SCAD │   │         │      │
│              │  14,758 pts │ │ export │ │ file │   │         │      │
│              │  FTS5 index │ │        │ │      │   │         │      │
│              └─────────────┘ └────────┘ └──────┘   │         │      │
│                                                     │         │      │
│   ┌─────────────────────────────────────────────────┴─────────┴──┐  │
│   │                     Anthropic Claude API                      │  │
│   │              claude-opus-4-6 (all agents)              │  │
│   └──────────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────────┘
```

## Agent Pipeline

### Stage 1: Requirements Analysis

**Model:** Opus | **Avg time:** ~10s

The orchestrator calls Claude directly to decompose the natural language prompt into a structured specification:

```json
{
  "project_name": "Autonomous Drone",
  "target_audience": "Hobbyist",
  "key_components": ["flight controller", "brushless motors", "ESCs", "GPS", "camera"],
  "complexity": "advanced",
  "constraints": { "budget_range": "moderate", "skill_level": "intermediate" }
}
```

### Stage 2: Parts Agent

**Model:** Opus | **Avg time:** ~30s

Multi-strategy component search:

1. **FTS5 full-text search** against LCSC parts 
2. **LIKE fallback** if FTS returns no results
3. **LLM selection** — Claude evaluates candidates and selects optimal BOM

The agent receives DB statistics as context (total parts, price range, top categories) to inform its search strategy.

**Output:** Array of BOM items with name, price (CNY), quantity, and selection rationale.

### Stage 3: PCB Agent

**Model:** Opus | **Avg time:** ~120s

Three-step PCB design pipeline:

1. **Circuit Design** — Component interconnections, power rails, signal routing
2. **KiCad Schematic** — Generates `.kicad_sch` format netlist
3. **Board Layout** — Layer count, dimensions, mounting holes, trace widths

**Output:** `circuit_design` (connections, power_rails), `schematic_kicad` (string), `layout` (specs).

### Stage 4: CAD Agent

**Model:** Opus | **Avg time:** ~60s

Generates parametric OpenSCAD enclosure files:

1. **Body** — Main enclosure with component mounting posts, ventilation, port cutouts
2. **Lid** — Snap-fit or screw-mount lid with alignment features

If OpenSCAD CLI is installed, compiles `.scad` → `.stl`. Otherwise saves source only.

**Output:** Array of file paths to `.scad` (and optionally `.stl`) files.

### Stage 5: Assembly Agent

**Model:** Opus | **Avg time:** ~70s

Generates step-by-step build guide:

- Ordered assembly steps with descriptions
- Required tools list
- Difficulty rating and time estimate
- Safety warnings

### Stage 6: Quoter Agent

**Model:** None (deterministic) | **Time:** <1ms

Pure arithmetic cost calculation:

| Component      | Calculation                                    |
|----------------|------------------------------------------------|
| Parts          | Σ(unit_price × quantity) × CNY_NATIVE          |
| PCB fab        | base_cost + (area - 25cm²) × rate_per_cm²     |
| 3D printing    | weight_grams × rate_per_gram                   |
| Shipping       | flat rate                                      |
| Platform fee   | 10% of subtotal                                |

**Conversion:** All internal prices are native CNY from 立创商城. No conversion needed.

## Database Schema

```sql
CREATE TABLE categories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    url TEXT UNIQUE NOT NULL,
    parent_id INTEGER REFERENCES categories(id)
);

CREATE TABLE parts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    url TEXT UNIQUE NOT NULL,
    sku TEXT,
    price REAL,                     -- CNY (立创商城)
    currency TEXT DEFAULT 'CNY',
    in_stock INTEGER DEFAULT 1,
    description TEXT,
    specs TEXT,                     -- JSON blob
    image_url TEXT,
    category_id INTEGER REFERENCES categories(id),
    scraped_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE VIRTUAL TABLE parts_fts USING fts5(
    name, description, specs,
    content=parts, content_rowid=id
);
```

**Statistics:**
- LCSC parts
- 1,587 with verified prices
- 561 categories
- Scraped via 立创EDA Pro API

## Frontend Architecture

```
App.tsx (single component, ~550 lines)
├── State: appState (idle|building|complete|error)
├── State: stages[] (6 stage cards with status tracking)
├── State: result (BuildResponse)
│
├── Idle View
│   ├── Prompt input + examples
│   ├── Config sliders (Budget, Quality)
│   └── Live graphs (canvas)
│
├── Build/Complete View
│   ├── Compact prompt bar
│   ├── Stage cards (sequential reveal)
│   │   ├── [01] REQUIREMENTS → expand to param grid
│   │   ├── [02] PARTS → expand to PartsGraph (force-directed canvas)
│   │   ├── [03] PCB → expand to connections table
│   │   ├── [04] ENCLOSURE → expand to file list
│   │   ├── [05] ASSEMBLY → expand to step list
│   │   └── [06] QUOTE → expand to cost breakdown
│   └── Live graphs
│
├── MatrixPanel.tsx (left panel)
│   ├── Idle: CORTEX-style hex cycling + scanner bar
│   └── Build: Real agent activity log
│
├── PartsGraph.tsx (canvas)
│   ├── Force-directed layout (gravity + repulsion + springs)
│   ├── Nodes sized by log(price)
│   ├── Edges from PCB connection mapping
│   ├── Glow effects (radial gradients)
│   ├── Starfield background
│   └── Hover: highlight constellation + tooltip
│
└── LiveGraph.tsx (canvas)
    └── Animated waveform display
```

**Bundle:** ~217KB gzip'd (React 19 + TypeScript + Tailwind v4)

## Memory Management

The full pipeline with Opus can exceed process memory limits on constrained environments. `run_staged.py` solves this by running each agent in a separate subprocess:

```
run_staged.py
├── subprocess: Requirements analysis (Opus, ~11s)
├── subprocess: Parts selection (Opus, ~30s)
├── subprocess: PCB design (Opus, ~120s)
├── subprocess: CAD generation (Opus, ~60s)
├── subprocess: Assembly guide (Opus, ~70s)
└── in-process: Quote calculation (<1ms)
```

State is persisted to `/tmp/pipeline_state.json` between stages. Each subprocess loads only its agent, processes the request, writes state, and exits — freeing memory for the next stage.
