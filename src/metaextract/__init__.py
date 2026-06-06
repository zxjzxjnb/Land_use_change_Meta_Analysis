"""metaextract: LLM-assisted data extraction for ecological meta-analysis."""

from .extractor import extract_from_pdf
from .pipeline import run_folder
from .schema import ExtractionResult
from .validator import validate_result

__all__ = [
    "extract_from_pdf",
    "run_folder",
    "ExtractionResult",
    "validate_result",
]

__version__ = "0.1.0"
