"""metaextract: LLM-assisted data extraction for ecological meta-analysis."""

from .extractor import extract_from_pdf
from .families import FAMILIES, AnalysisFamily, RecordField, get_family
from .highlight import Match, locate_value
from .ingest import ingest_pdf
from .locate import SOIL_AGRI_SPEC, LocateOutput, TargetVar, TaskSpec, locate
from .pipeline import run_folder
from .records import Citation, LocatedRegion, ScreeningResult
from .schema import ExtractionResult
from .sampling import find_sample_size_candidates
from .sourcedoc import BBox, SourceBlock, SourceDoc, Word
from .tabular import TableRow, make_pairings, parse_block
from .validator import validate_result

__all__ = [
    "extract_from_pdf",
    "run_folder",
    "ExtractionResult",
    "validate_result",
    # v3.1 cockpit foundation (M0a)
    "ingest_pdf",
    "SourceDoc",
    "SourceBlock",
    "BBox",
    "Word",
    "locate_value",
    "Match",
    # v3.1 screen + locate (M0b)
    "locate",
    "LocateOutput",
    "TaskSpec",
    "TargetVar",
    "SOIL_AGRI_SPEC",
    # analysis families (per-record field set)
    "AnalysisFamily",
    "RecordField",
    "get_family",
    "FAMILIES",
    "LocatedRegion",
    "ScreeningResult",
    "Citation",
    # multi-pairing assist (cockpit M0b+)
    "parse_block",
    "make_pairings",
    "TableRow",
    "find_sample_size_candidates",
]

__version__ = "0.1.0"
