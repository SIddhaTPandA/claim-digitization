# SPD Benefits Extraction - AI Agent Guidelines

## Project Overview
Azure-native IDP solution extracting healthcare benefit data from SPD/SBC/SOB PDFs into a standardized 15-column Excel format. Uses schema-bound table extraction with 7-strategy semantic normalization (500+ term mappings).

**Pipeline:** PDF → Classifier → Extractor → Normalizer → Validator → Excel Generator

## Build and Test

```powershell
# Setup
pip install -r requirements.txt
pip install -r requirements-dev.txt  # dev dependencies

# Run extraction (always as module)
python -m src.main --input "../Plans" --output "../OutputExcel"
python -m src.main --file "../Plans/document.pdf" --verbose

# Tests
pytest tests/unit/ -v
pytest tests/unit/ --cov=src --cov-report=html

# Lint/Format
black src/ tests/
mypy src/
```

## Architecture

| Directory | Purpose |
|-----------|---------|
| `src/agents/` | Pipeline agents - see [orchestrator.py](src/agents/orchestrator.py) |
| `src/parsers/` | Schema-bound parsing - see [table_extractor.py](src/parsers/table_extractor.py) |
| `src/ontology/` | 7-strategy semantic matching - see [semantic_matcher.py](src/ontology/semantic_matcher.py) |
| `src/config/` | ALL patterns live here - see [extraction_config.py](src/config/extraction_config.py) |
| `src/models/` | Pydantic models - see [benefit_record.py](src/models/benefit_record.py) |
| `data/` | Data-driven configs - [term_mappings.json](data/term_mappings.json), [master_service_list.json](data/master_service_list.json) |

## 15-Column Excel Output Schema

All records map to this fixed schema in [BenefitRecord](src/models/benefit_record.py):

| # | Column Name | Field | Example Values |
|---|-------------|-------|----------------|
| 1 | Header | `header` | "Emergency Services", "Physician Services" |
| 2 | Service | `service` | "Office Visit for Injury / Illness - Primary Care" |
| 3 | In-Network Coinsurance | `in_network_coinsurance` | "80%", "100%", "NOT COVERED" |
| 4 | In-Network After Deductible | `in_network_after_deductible` | "Yes", "No" |
| 5 | In-Network Copay | `in_network_copay` | "$20", "$350", "$0" |
| 6 | Out-of-Network Coinsurance | `out_of_network_coinsurance` | "60%", "NOT COVERED" |
| 7 | Out-of-Network After Deductible | `out_of_network_after_deductible` | "Yes", "No" |
| 8 | Out-of-Network Copay | `out_of_network_copay` | "$50", "$500" |
| 9 | Individual In-Network | `individual_in_network` | "$500", "$1,500" (deductible/OOP rows only) |
| 10 | Family In-Network | `family_in_network` | "$1,000", "$3,000" (deductible/OOP rows only) |
| 11 | Individual Out-of-Network | `individual_out_of_network` | "$1,000", "$5,000" |
| 12 | Family Out-of-Network | `family_out_of_network` | "$2,000", "$10,000" |
| 13 | Limit Type | `limit_type` | "90 visits", "$3,000", "25 days" |
| 14 | Limit Period | `limit_period` | "Benefit Year", "Lifetime", "Per Visit" |
| 15 | Pre-Authorization Required | `preauth_required` | "Yes", "No" |

**Metadata fields** (not in Excel, used for processing):
- `confidence_score` (0.0-1.0), `source_page`, `raw_in_network_text`, `raw_out_of_network_text`, `extraction_notes`

## Code Patterns

### Data Models Pattern
```python
# Pydantic v2 for validated output data
class BenefitRecord(BaseModel):
    header: str = Field(description="Service category")
    service: str = Field(min_length=1, max_length=500)
    
    @field_validator("in_network_coinsurance", mode="before")
    @classmethod
    def validate_coinsurance_field(cls, v: str | None) -> str | None:
        return validate_coinsurance(v) if v else None

# Dataclass for internal/config structures
@dataclass
class ColumnSchema:
    column_count: int = 0
    role_mapping: Dict[int, ColumnRole] = field(default_factory=dict)
    header_row_index: int = -1
```

### Schema-Bound Extraction Pattern
```python
class ColumnRole(Enum):
    SERVICE_NAME = "service_name"
    IN_NETWORK_VALUE = "in_network_value"
    OUT_OF_NETWORK_VALUE = "out_of_network_value"
    IN_NETWORK_COPAY = "in_network_copay"
    OUT_OF_NETWORK_COPAY = "out_of_network_copay"
    LIMITATIONS = "limitations"
    PREAUTH = "preauth"

# Column index → semantic role mapping
schema.role_mapping[0] = ColumnRole.SERVICE_NAME
schema.role_mapping[1] = ColumnRole.IN_NETWORK_VALUE
```

### MatchResult Pattern (Semantic Matcher)
```python
@dataclass
class MatchResult:
    standard_value: str     # Normalized output value
    confidence: float       # 0.0-1.0
    match_method: str       # "exact", "config", "fuzzy", "pattern", "llm"
    matched: bool           # Whether match was successful
    original_term: str      # Input term
```

### ValueParser Pattern (record_builder.py)
```python
@dataclass
class ParsedValue:
    coinsurance: Optional[str] = None    # "80%"
    copay: Optional[str] = None          # "$20"
    after_deductible: bool = False       # "Yes"/"No"
    is_not_covered: bool = False
    is_covered_in_full: bool = False
    raw_text: str = ""

# Parse combined benefit text like "$20 copay; 80% after deductible"
parsed = ValueParser.parse_combined_value(raw_text)
```

### Hierarchical Service Names Pattern
```python
# Parent-child service structure preserved as "Parent - Child"
@dataclass
class HierarchicalContext:
    current_category: Optional[str] = None
    current_parent_service: Optional[str] = None
    
# Result: "Office Visit for Injury / Illness - Primary Care"
full_service_name = f"{parent_name} - {child_name}"
```

### ExtractedRow Pattern (table_extractor.py)
```python
@dataclass
class ExtractedRow:
    service_name: str
    in_network_value: Optional[str] = None
    out_of_network_value: Optional[str] = None
    in_network_copay: Optional[str] = None
    out_of_network_copay: Optional[str] = None
    is_category_header: bool = False
    is_parent_service: bool = False
    parent_service_name: Optional[str] = None
    category: Optional[str] = None
    
    @property
    def full_service_name(self) -> str:
        """Combine parent + child for hierarchical services."""
        if self.parent_service_name:
            return f"{self.parent_service_name} - {self.service_name}"
        return self.service_name
```

## Critical Conventions

1. **NO hardcoded patterns** - ALL extraction regex patterns MUST be in [extraction_config.py](src/config/extraction_config.py), not embedded in extraction logic

2. **Data-driven normalization** - ALL term mappings in [term_mappings.json](data/term_mappings.json), not in code

3. **Run as module** - Always `python -m src.main`, not `python src/main.py`

4. **Use DEFAULT_CONFIG** - Import the singleton: `from src.config.extraction_config import DEFAULT_CONFIG`

5. **Pydantic v2 validators** - Use `field_validator`, `model_validator` (not v1's `validator`)

6. **Logging** - Module-level loggers only: `logger = logging.getLogger(__name__)`

7. **Type hints** - Full type hints on all functions: `Optional[]`, `List[]`, `Dict[]`, `Tuple[]`

## 7-Strategy Normalization Order

| Priority | Strategy | Confidence | Source |
|----------|----------|------------|--------|
| 1 | Exact match | 100% | Direct string match |
| 2 | Config mapping | 95% | term_mappings.json `mappings` |
| 3 | Learned mapping | 90% | term_mappings.json `learned_mappings` |
| 4 | Pattern match | 90% | term_mappings.json `patterns` |
| 5 | Fuzzy match | 85%+ | Levenshtein distance |
| 6 | Embedding match | variable | Semantic similarity |
| 7 | LLM fallback | variable | Azure OpenAI (optional) |

## Files to Modify by Task

| Task | File(s) |
|------|---------|
| Add term mappings | [term_mappings.json](data/term_mappings.json) → `mappings` section |
| Add regex patterns | [term_mappings.json](data/term_mappings.json) → `patterns` section |
| Add category detection | [extraction_config.py](src/config/extraction_config.py) → `CategoryDetectionPatterns` |
| Add table header patterns | [extraction_config.py](src/config/extraction_config.py) → `TableHeaderPatterns` |
| Adjust confidence thresholds | [extraction_config.py](src/config/extraction_config.py) → `ConfidenceThresholds` |
| Modify value parsing | [record_builder.py](src/parsers/record_builder.py) → `ValueParser` class |
| Modify validation rules | [deterministic_validator.py](src/validators/deterministic_validator.py) |
| Modify Excel output | [excel_generator.py](src/generators/excel_generator.py) |
| Add document type keywords | [classifier_agent.py](src/agents/classifier_agent.py) |
| Add service definitions | [master_service_list.json](data/master_service_list.json) |
| Add payer-specific terms | [term_mappings.json](data/term_mappings.json) → `payer_specific` section |

## Key Thresholds

| Threshold | Default | Purpose |
|-----------|---------|---------|
| `auto_approve` | 0.70 | Minimum confidence for auto-approval |
| `table_extraction` | 0.85 | Base confidence for table extraction |
| `text_extraction` | 0.60 | Base confidence for text fallback |
| Service name max | 80 chars | Truncated with "..." suffix |
| Dedup key length | 100 chars | Service name truncation for deduplication |

## Testing Notes

- Unit tests: `pytest tests/unit/ -v` (115 tests expected)
- Integration tests: `pytest tests/integration/ -v` (require sample PDFs)
- Tests add src to path: `sys.path.insert(0, ...)`
- Run single test file: `pytest tests/unit/test_table_extractor.py -v`
