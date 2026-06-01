"""
Typed exception hierarchy for pipeline error handling.

Each agent stage has a specific exception type for granular
error recovery and reporting. All inherit from PipelineError.
"""


class PipelineError(Exception):
    """Base exception for all pipeline errors."""
    def __init__(self, message: str, agent: str = "", stage: str = "", recoverable: bool = False):
        self.agent = agent
        self.stage = stage
        self.recoverable = recoverable
        super().__init__(message)


class RequirementsError(PipelineError):
    """Failed to parse or analyze user prompt."""
    def __init__(self, message: str):
        super().__init__(message, agent="orchestrator", stage="requirements")


class PartsSearchError(PipelineError):
    """Parts database search failed or returned no results."""
    def __init__(self, message: str, query: str = ""):
        self.query = query
        super().__init__(message, agent="parts", stage="search", recoverable=True)


class PartsSelectionError(PipelineError):
    """Claude failed to select parts from candidates."""
    def __init__(self, message: str, candidates: int = 0):
        self.candidates = candidates
        super().__init__(message, agent="parts", stage="selection", recoverable=True)


class PCBDesignError(PipelineError):
    """PCB circuit/schematic/layout generation failed."""
    def __init__(self, message: str, substage: str = ""):
        self.substage = substage  # circuit | schematic | layout
        super().__init__(message, agent="pcb", stage=f"pcb_{substage}")


class CADGenerationError(PipelineError):
    """OpenSCAD enclosure generation failed."""
    def __init__(self, message: str, file_type: str = ""):
        self.file_type = file_type  # body | lid
        super().__init__(message, agent="cad", stage="enclosure")


class AssemblyError(PipelineError):
    """Assembly guide generation failed."""
    def __init__(self, message: str):
        super().__init__(message, agent="assembler", stage="assembly")


class QuoteError(PipelineError):
    """Cost calculation failed."""
    def __init__(self, message: str):
        super().__init__(message, agent="quoter", stage="quote")


class JSONParseError(PipelineError):
    """Claude returned unparseable JSON."""
    def __init__(self, message: str, raw_text: str = ""):
        self.raw_text = raw_text[:200]
        super().__init__(message, stage="json_parse", recoverable=True)


class TokenLimitError(PipelineError):
    """Response was truncated by max_tokens limit."""
    def __init__(self, message: str, max_tokens: int = 0):
        self.max_tokens = max_tokens
        super().__init__(message, stage="token_limit", recoverable=True)
