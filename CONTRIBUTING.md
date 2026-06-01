# Contributing

## Setup

```bash
git clone https://github.com/thehengyao/iron-emperor.git
cd iron-emperor
pip install -r requirements.txt
cd frontend && npm install && cd ..
```

## Development

```bash
# Start server
PYTHONPATH=. uvicorn src.api.server:app --reload --port 8000

# Frontend dev server (proxies /api to :8000)
cd frontend && npm run dev

# Run tests
PYTHONPATH=. python -m pytest tests/ -v

# Benchmark a build
PYTHONPATH=. python benchmark.py "气象站"
```

## Architecture

See `docs/ARCHITECTURE.md` for system design and `docs/PROTOCOL.md` for the A2A spec.

### Adding a New Agent

1. Create `src/agents/<name>/<name>_agent.py`
2. Implement `async handle(self, msg: AgentMessage) -> dict`
3. Register in `Orchestrator.__init__()` or via `register_agent()`
4. Add validator in `src/validators.py`
5. Add tests in `tests/test_<name>.py`

### Pipeline Flow

```
User Prompt
  → Orchestrator._analyze_requirements()     [Opus]
  → PartsAgent.handle()                      [FTS5 + Opus]
  → PCBAgent.handle()                        [Opus × 3]
  → CADAgent.handle()                        [Opus × 2]
  → AssemblyAgent.handle()                   [Opus]
  → QuoterAgent.handle()                     [Pure math]
  → ProjectSpec
```

## Code Style

- Python: type hints, docstrings, no `# type: ignore`
- TypeScript: strict mode, explicit return types
- Commits: conventional commits (`feat:`, `fix:`, `test:`, `docs:`)

## Testing

All PRs need passing tests. Run:

```bash
PYTHONPATH=. python -m pytest tests/ -v
```

Add tests for any new agents, validators, or parser changes.
