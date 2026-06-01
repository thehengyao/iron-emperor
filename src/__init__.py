"""
焊武帝 IronEmperor — multi-agent pipeline for hardware project generation.

Public API:
    from src import Orchestrator, PartsAgent, PCBAgent, CADAgent
    from src import AssemblyAgent, QuoterAgent
    from src.types import BOMItem, PCBDesign, ProjectSpec
    from src.config import CONFIG
"""
from src.agents.orchestrator import Orchestrator, AgentMessage, ProjectSpec, MODEL
from src.config import CONFIG

__version__ = "1.0.0"
__all__ = ["Orchestrator", "AgentMessage", "ProjectSpec", "CONFIG", "MODEL"]
