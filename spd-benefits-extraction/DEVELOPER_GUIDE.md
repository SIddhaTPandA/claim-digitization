# SPD Benefits Extraction - Developer Guide

> **Version:** 2.0.0  
> **Last Updated:** February 2026  
> **Python Version:** 3.11+

---

## Table of Contents

1. [Overview](#overview)
2. [Architecture](#architecture)
3. [Installation](#installation)
4. [Running the Program](#running-the-program)
5. [Configuration](#configuration)
6. [Component Reference](#component-reference)
7. [Output Schema](#output-schema)
8. [Quality Validation](#quality-validation)
9. [Extending the System](#extending-the-system)
10. [Troubleshooting](#troubleshooting)
11. [API Reference](#api-reference)

---

## Overview

**SPD Benefits Extraction** is an Intelligent Document Processing (IDP) solution that extracts healthcare benefit details from PDF documents and generates standardized Excel output for HealthEdge HRP platform configuration.

### Supported Document Types

| Type | Description |
|------|-------------|
| **SPD** | Summary Plan Description - Detailed plan documents |
| **SBC** | Summary of Benefits and Coverage - Standardized 8-page format |
| **SOB** | Schedule of Benefits - Benefit tables and schedules |
| **COC** | Certificate of Coverage - Coverage certificates |

### Key Capabilities

- **Multi-Format Support**: Processes SPD, SBC, SOB, and COC documents
- **Schema-Bound Extraction**: Maps table columns to semantic roles
- **7-Strategy Semantic Matching**: Normalizes 500+ term variations
- **Confidence Scoring**: Record-level confidence with explanatory notes
- **15-Column Output**: Standardized Excel format for HealthEdge HRP
- **Generic Validation**: Plan-agnostic quality checks

### Pipeline Overview

```
PDF → PDF Processor → Classifier → Extractor → Normalizer → Validator → Excel Generator
```

---

## Architecture

### High-Level Data Flow

```
┌─────────────────────────────────────────────────────────────────┐
│                         INPUT                                    │
│                    SPD/SBC PDF Files                            │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    EXTRACTION PIPELINE                          │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐          │
│  │  main.py     │→ │ Orchestrator │→ │PDF Processor │          │
│  │  Entry Point │  │  Controller  │  │Text/Tables   │          │
│  └──────────────┘  └──────────────┘  └──────────────┘          │
│         │                                    │                   │
│         ▼                                    ▼                   │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐          │
│  │ Classifier   │→ │  Extractor   │→ │ Normalizer   │          │
│  │ Agent        │  │  Agent       │  │ Agent        │          │
│  └──────────────┘  └──────────────┘  └──────────────┘          │
│                           │                 │                    │
│                           ▼                 ▼                    │
│  ┌──────────────────────────────────────────────────┐           │
│  │            StructuredTableExtractor              │           │
│  │         SchemaRecordBuilder + ValueParser        │           │
│  └──────────────────────────────────────────────────┘           │
│                           │                                      │
│                           ▼                                      │
│  ┌──────────────────────────────────────────────────┐           │
│  │              Semantic Matcher                     │           │
│  │         (7-Strategy Term Matching)               │           │
│  │         + term_mappings.json (500+ terms)        │           │
│  └──────────────────────────────────────────────────┘           │
│                           │                                      │
│                           ▼                                      │
│  ┌──────────────────────────────────────────────────┐           │
│  │     Deterministic Validator + Confidence Scorer  │           │
│  └──────────────────────────────────────────────────┘           │
│                           │                                      │
│                           ▼                                      │
│  ┌──────────────────────────────────────────────────┐           │
│  │              Excel Generator                      │           │
│  │          (15-Column Schema Output)               │           │
│  └──────────────────────────────────────────────────┘           │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                         OUTPUT                                   │
│              Excel Files (15-Column Schema)                      │
│           + Optional Quality Validation Report                   │
└─────────────────────────────────────────────────────────────────┘
```

### Directory Structure

```
spd-benefits-extraction/
├── src/
│   ├── main.py                          # CLI entry point
│   ├── __init__.py
│   │
│   ├── agents/                          # Processing agents
│   │   ├── __init__.py
│   │   ├── orchestrator.py              # Pipeline coordinator
│   │   ├── classifier_agent.py          # Document classification
│   │   ├── extractor_agent.py           # Benefit extraction
│   │   └── normalizer_agent.py          # Data normalization
│   │
│   ├── config/                          # Configuration
│   │   ├── __init__.py
│   │   └── extraction_config.py         # Patterns & thresholds
│   │
│   ├── document_intelligence/           # PDF processing
│   │   ├── __init__.py
│   │   └── pdf_processor.py             # PDF text/table extraction
│   │
│   ├── generators/                      # Output generation
│   │   ├── __init__.py
│   │   └── excel_generator.py           # Excel output creation
│   │
│   ├── models/                          # Data models
│   │   ├── __init__.py
│   │   └── benefit_record.py            # Pydantic data models
│   │
│   ├── ontology/                        # Semantic matching
│   │   ├── __init__.py
│   │   └── semantic_matcher.py          # 7-strategy term matching
│   │
│   ├── parsers/                         # Table/text parsing
│   │   ├── __init__.py
│   │   ├── table_extractor.py           # Schema-bound table parsing
│   │   ├── record_builder.py            # Value parsing
│   │   └── benefit_text_parser.py       # Text-based fallback
│   │
│   ├── validators/                      # Validation
│   │   ├── __init__.py
│   │   ├── deterministic_validator.py   # Rule-based validation
│   │   ├── confidence_scorer.py         # Multi-factor scoring
│   │   └── quality_validator.py         # Output quality checks
│   │
│   └── utils/                           # Utilities
│       ├── __init__.py
│       └── logging_config.py            # Logging configuration
│
├── data/                                # Reference data
│   ├── term_mappings.json               # 500+ term mappings
│   └── master_service_list.json         # Service reference catalog
│
├── tests/                               # Test suite
│   ├── __init__.py
│   ├── unit/                            # Unit tests (115 tests)
│   │   ├── test_benefit_record.py
│   │   ├── test_classifier_agent.py
│   │   ├── test_extractor_agent.py
│   │   ├── test_normalizer_agent.py
│   │   ├── test_record_builder.py
│   │   ├── test_semantic_matcher.py
│   │   ├── test_table_extractor.py
│   │   └── test_validator.py
│   └── integration/                     # Integration tests
│       └── test_end_to_end.py
│
├── functions/                           # Azure Functions (optional)
│   ├── __init__.py
│   ├── function_app.py
│   ├── pdf_upload_trigger/
│   ├── orchestration_trigger/
│   └── human_review_trigger/
│
├── infra/                               # Azure Bicep templates
│   ├── main.bicep
│   ├── modules/
│   └── parameters/
│
├── requirements.txt                     # Production dependencies
├── requirements-dev.txt                 # Development dependencies
├── pyproject.toml                       # Project configuration
├── host.json                            # Azure Functions config
├── local.settings.json.example          # Local settings template
├── README.md                            # Quick start guide
└── DEVELOPER_GUIDE.md                   # This file
```

---

## Installation

### Prerequisites

- Python 3.11 or higher
- pip package manager

### Step 1: Clone and Setup

```powershell
# Clone repository
git clone <repository-url>
cd spd-benefits-extraction

# Create virtual environment
python -m venv venv

# Activate virtual environment (Windows PowerShell)
.\venv\Scripts\Activate.ps1

# For Command Prompt:
# .\venv\Scripts\activate.bat

# For Linux/Mac:
# source venv/bin/activate
```

### Step 2: Install Dependencies

```powershell
# Production dependencies
pip install -r requirements.txt

# Development dependencies (includes pytest, mypy, black)
pip install -r requirements-dev.txt
```

### Step 3: Configure Environment (Optional)

Copy `local.settings.json.example` to `local.settings.json` and configure Azure services if needed:

```json
{
  "IsEncrypted": false,
  "Values": {
    "AzureWebJobsStorage": "UseDevelopmentStorage=true",
    "FUNCTIONS_WORKER_RUNTIME": "python",
    "AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT": "https://<resource>.cognitiveservices.azure.com/",
    "AZURE_DOCUMENT_INTELLIGENCE_KEY": "<your-key>",
    "LOG_LEVEL": "INFO"
  }
}
```

> **Note**: The system runs fully offline using pdfplumber for PDF extraction. Azure services are optional enhancements.

---

## Running the Program

### Basic Usage

```powershell
# Process all PDFs in a directory
python -m src.main --input "../Plans" --output "../OutputExcel"

# Process a single file
python -m src.main --file "../Plans/document.pdf"

# Enable verbose logging
python -m src.main --input "../Plans" --output "../OutputExcel" --verbose

# Adjust confidence threshold (default: 0.70)
python -m src.main --input "../Plans" --output "../OutputExcel" --confidence-threshold 0.80

# Skip validation checks
python -m src.main --input "../Plans" --output "../OutputExcel" --skip-validation

# Show help
python -m src.main --help
```

### Command Line Arguments

| Argument | Default | Description |
|----------|---------|-------------|
| `--input`, `-i` | `Plans` | Input directory containing PDF files |
| `--output`, `-o` | `OutputExcel` | Output directory for Excel files |
| `--file`, `-f` | - | Process a single PDF file |
| `--confidence-threshold` | `0.70` | Minimum confidence for auto-approval (0.0-1.0) |
| `--skip-validation` | `False` | Skip validation checks |
| `--verbose`, `-v` | `False` | Enable verbose logging |
| `--quiet`, `-q` | `False` | Suppress output except errors |

### Validate Output Quality

```powershell
# Validate a single Excel file
python -m src.validators.quality_validator "../OutputExcel/document.xlsx"

# Validate all Excel files in a directory
python -m src.validators.quality_validator "../OutputExcel/test_run/"
```

### Running Tests

```powershell
# Run all unit tests
python -m pytest tests/unit/ -v

# Run with coverage report
python -m pytest tests/unit/ --cov=src --cov-report=html

# Run specific test file
python -m pytest tests/unit/test_table_extractor.py -v
```

---

## Configuration

### Configuration Files

| File | Purpose |
|------|---------|
| `src/config/extraction_config.py` | All patterns, thresholds, and extraction parameters |
| `data/term_mappings.json` | 500+ term mappings for semantic normalization |
| `data/master_service_list.json` | Reference catalog of healthcare services |

### Key Configuration Classes

```python
from src.config.extraction_config import (
    ExtractionConfig,
    DEFAULT_CONFIG,
    ConfidenceThresholds,
    BenefitValuePatterns,
    TableHeaderPatterns,
)

# Use default configuration
config = DEFAULT_CONFIG

# Create custom configuration
config = ExtractionConfig(
    confidence_thresholds=ConfidenceThresholds(
        auto_approve=0.80,
        table_extraction=0.90
    )
)
```

### Confidence Thresholds

| Threshold | Default | Description |
|-----------|---------|-------------|
| `auto_approve` | 0.70 | Minimum confidence for auto-approval |
| `table_extraction` | 0.85 | Base confidence for table-based extraction |
| `text_extraction` | 0.60 | Base confidence for text-based fallback |
| `pattern_extraction` | 0.75 | Base confidence for regex pattern matches |
| `missing_field_penalty` | 0.10 | Penalty per missing required field |
| `ambiguous_value_penalty` | 0.05 | Penalty for ambiguous values |

### Adding Term Mappings

Edit `data/term_mappings.json`:

```json
{
  "mappings": {
    "service_category": {
      "physician services": "Physician Services",
      "doctor visit": "Physician Services",
      "office visit": "Office Visit"
    },
    "network_tier": {
      "in network": "In-Network",
      "participating": "In-Network",
      "non-par": "Out-of-Network"
    }
  }
}
```

---

## Component Reference

### Core Components

| Component | File | Description |
|-----------|------|-------------|
| **Orchestrator** | `src/agents/orchestrator.py` | Coordinates the 6-step extraction pipeline |
| **PDF Processor** | `src/document_intelligence/pdf_processor.py` | Extracts text and tables from PDFs |
| **Classifier Agent** | `src/agents/classifier_agent.py` | Detects document type and structure |
| **Extractor Agent** | `src/agents/extractor_agent.py` | Extracts raw benefit data from tables |
| **Normalizer Agent** | `src/agents/normalizer_agent.py` | Standardizes values using SemanticMatcher |
| **Excel Generator** | `src/generators/excel_generator.py` | Creates formatted Excel output |

### Parser Components

| Component | File | Description |
|-----------|------|-------------|
| **StructuredTableExtractor** | `src/parsers/table_extractor.py` | Schema-bound table parsing with column role detection |
| **SchemaRecordBuilder** | `src/parsers/record_builder.py` | Converts extracted rows to BenefitRecord format |
| **ValueParser** | `src/parsers/record_builder.py` | Parses benefit value strings (coinsurance, copay, etc.) |
| **BenefitTextParser** | `src/parsers/benefit_text_parser.py` | Text-based fallback parser |

### Semantic Matching (7 Strategies)

| # | Strategy | Confidence | Description |
|---|----------|------------|-------------|
| 1 | Exact Match | 100% | Case-insensitive exact match |
| 2 | Config Mapping | 95% | Lookup in `term_mappings.json` |
| 3 | Learned Mapping | 90% | Previously learned from corrections |
| 4 | Pattern Match | 90% | Regex patterns from config |
| 5 | Fuzzy Match | 85%+ | SequenceMatcher similarity |
| 6 | Embedding Match | Variable | Semantic similarity (optional) |
| 7 | LLM Fallback | Variable | Azure OpenAI GPT-4 (optional) |

### Validation Components

| Component | File | Description |
|-----------|------|-------------|
| **DeterministicValidator** | `src/validators/deterministic_validator.py` | Rule-based validation |
| **ConfidenceScorer** | `src/validators/confidence_scorer.py` | Multi-factor confidence scoring |
| **QualityValidator** | `src/validators/quality_validator.py` | Output quality validation |

---

## Output Schema

### 15-Column Excel Format

| # | Column | Field | Example Values |
|---|--------|-------|----------------|
| 1 | Header | `header` | "Emergency Services", "Physician Services" |
| 2 | Service | `service` | "Office Visit - Primary Care" |
| 3 | In-Network Coinsurance | `in_network_coinsurance` | "80%", "100%", "NOT COVERED" |
| 4 | In-Network After Deductible | `in_network_after_deductible` | "Yes", "No" |
| 5 | In-Network Copay | `in_network_copay` | "$20", "$350", "$0" |
| 6 | Out-of-Network Coinsurance | `out_of_network_coinsurance` | "60%", "NOT COVERED" |
| 7 | Out-of-Network After Deductible | `out_of_network_after_deductible` | "Yes", "No" |
| 8 | Out-of-Network Copay | `out_of_network_copay` | "$50", "N/A" |
| 9 | Individual In-Network | `individual_in_network` | "$1,500", "N/A" |
| 10 | Family In-Network | `family_in_network` | "$3,000", "N/A" |
| 11 | Individual Out-of-Network | `individual_out_of_network` | "$3,000", "N/A" |
| 12 | Family Out-of-Network | `family_out_of_network` | "$6,000", "N/A" |
| 13 | Limit Type | `limit_type` | "60 visits", "$3,000 max" |
| 14 | Limit Period | `limit_period` | "Benefit Year", "Lifetime" |
| 15 | Pre-Authorization Required | `preauth_required` | "Yes", "No" |
| 16 | Confidence Score | `confidence_score` | 0.85, 0.92 |

### Value Parsing Examples

| Input Text | Parsed Output |
|------------|---------------|
| `"80% after deductible"` | `coinsurance="80%", after_deductible="Yes"` |
| `"$50 copay; 80% after ded"` | `copay="$50", coinsurance="80%", after_deductible="Yes"` |
| `"Covered in full"` | `coinsurance="100%"` |
| `"Not covered"` | `coinsurance="NOT COVERED"` |
| `"Plan pays 80%"` | `coinsurance="80%"` |
| `"You pay 20%"` | `coinsurance="80%"` (normalized to plan-pays) |

---

## Quality Validation

### Generic Quality Validator

The `QualityValidator` class performs plan-agnostic validation without hardcoded expectations:

```python
from src.validators.quality_validator import QualityValidator, validate_excel

# Validate an Excel file
report = validate_excel("../OutputExcel/document.xlsx")

print(f"File: {report.file_path}")
print(f"Records: {report.total_records}")
print(f"Schema Valid: {report.schema_valid}")
print(f"Errors: {report.error_count}")
print(f"Warnings: {report.warning_count}")
print(f"Production Ready: {report.is_production_ready}")

# Print detailed summary
print(report.summary())

# Review individual validations
for validation in report.validations:
    status = "PASS" if validation.passed else "FAIL"
    print(f"[{status}] {validation.rule_name}: {validation.message}")
```

### Validation Rules

| Rule | Severity | Description |
|------|----------|-------------|
| `schema_validation` | Error | All required columns present |
| `service_names_present` | Error | All records have service names |
| `header_values_present` | Warning | All records have header/category |
| `coinsurance_format` | Warning | Valid percentage or special value |
| `copay_format` | Warning | Valid dollar amount or special value |
| `deductible_flag_format` | Warning | Valid Yes/No values |
| `network_consistency` | Info | IN/OON values show expected variation |
| `confidence_scores` | Error/Info | Valid range and above threshold |
| `limit_consistency` | Warning | Family limits >= Individual limits |
| `preauth_values` | Warning | Valid Yes/No values |
| `no_empty_rows` | Warning | All records have at least one value |
| `no_duplicate_services` | Info | No exact duplicate service names |

> **Note**: The validator does NOT make plan-specific assumptions about what coinsurance percentages should be. It only validates format and logical consistency.

### Command Line Usage

```powershell
# Validate single file
python -m src.validators.quality_validator "../OutputExcel/document.xlsx"

# Validate all files in directory
python -m src.validators.quality_validator "../OutputExcel/test_run/"
```

---

## Extending the System

### Adding New Term Mappings

1. Edit `data/term_mappings.json`
2. Add mappings to the appropriate section:

```json
{
  "mappings": {
    "service_category": {
      "new term": "Standard Term"
    }
  }
}
```

### Adding New Extraction Patterns

1. Edit `src/config/extraction_config.py`
2. Add patterns to the appropriate class:

```python
@dataclass
class BenefitValuePatterns:
    coinsurance: List[str] = field(default_factory=lambda: [
        r"(\d{1,3})\s*%",
        r"plan\s+pays\s+(\d{1,3})\s*%",
        # Add new pattern here
    ])
```

### Adding New Document Types

1. Edit `src/agents/classifier_agent.py`
2. Add keywords to `DOCUMENT_TYPE_KEYWORDS`:

```python
DOCUMENT_TYPE_KEYWORDS = {
    "SPD": ["summary plan description", ...],
    "SBC": ["summary of benefits", ...],
    "NEW_TYPE": ["keywords", "for", "new", "type"],
}
```

### Adding Custom Validation Rules

1. Edit `src/validators/quality_validator.py`
2. Add a new validation method:

```python
def _validate_custom_rule(self, df: pd.DataFrame) -> ValidationResult:
    invalid_rows = []
    # Your validation logic here
    if invalid_rows:
        return ValidationResult(
            rule_name="custom_rule",
            passed=False,
            message="Description of issue",
            severity="warning",
            affected_rows=invalid_rows
        )
    return ValidationResult(
        rule_name="custom_rule",
        passed=True,
        message="Validation passed"
    )
```

3. Add to the `validate()` method's validation list.

---

## Troubleshooting

### Common Issues

| Issue | Solution |
|-------|----------|
| "Permission denied" on Excel | Close the Excel file before running |
| Low confidence scores | Check `data/term_mappings.json` for missing terms |
| Missing service categories | Add to `term_mappings.json` → `standard_values.service_category` |
| PDF text extraction fails | Ensure pdfplumber is installed; check PDF isn't image-based |
| Missing IN/OON values | Check column detection in `table_extractor.py` |
| Incorrect value parsing | Debug `record_builder.py` → `ValueParser` patterns |
| Validation errors | Review `deterministic_validator.py` rules |
| Duplicate records | Adjust similarity threshold in `RecordDeduplicator` |

### Debug Logging

Enable verbose logging to diagnose issues:

```powershell
python -m src.main --input "../Plans" --output "../OutputExcel" --verbose
```

Or set the log level programmatically:

```python
import logging
logging.getLogger("src.parsers.table_extractor").setLevel(logging.DEBUG)
logging.getLogger("src.agents.normalizer_agent").setLevel(logging.DEBUG)
```

### Key Files for Debugging

| Issue Type | Files to Check |
|------------|----------------|
| Table detection | `src/parsers/table_extractor.py` |
| Value parsing | `src/parsers/record_builder.py` |
| Term normalization | `src/ontology/semantic_matcher.py`, `data/term_mappings.json` |
| Column mapping | `src/config/extraction_config.py` |
| Output formatting | `src/generators/excel_generator.py` |

---

## API Reference

### Orchestrator

```python
from src.agents.orchestrator import Orchestrator, ProcessingResult

# Initialize
orchestrator = Orchestrator(
    output_dir="OutputExcel",
    confidence_threshold=0.70,
    enable_validation=True
)

# Process single document
result: ProcessingResult = orchestrator.process_document("path/to/document.pdf")

# Process directory
results: List[ProcessingResult] = orchestrator.process_directory("Plans")
```

### ProcessingResult

```python
@dataclass
class ProcessingResult:
    success: bool
    source_file: str
    output_file: str
    records_extracted: int
    overall_confidence: float
    requires_review: bool
    error_message: Optional[str]
    validation_issues: List[ValidationIssue]
```

### BenefitRecord

```python
from src.models.benefit_record import BenefitRecord

record = BenefitRecord(
    header="Physician Services",
    service="Office Visit - Primary Care",
    in_network_coinsurance="80%",
    in_network_after_deductible="Yes",
    in_network_copay="$20",
    out_of_network_coinsurance="60%",
    out_of_network_after_deductible="Yes",
    out_of_network_copay="$50",
    confidence_score=0.92
)

# Convert to Excel row
excel_row = record.to_excel_row()

# Get column headers
headers = BenefitRecord.get_excel_headers()
```

### QualityValidator

```python
from src.validators.quality_validator import (
    QualityValidator, 
    QualityReport,
    validate_excel,
    validate_all_in_directory
)

# Validate single file
validator = QualityValidator(confidence_threshold=0.70)
report: QualityReport = validator.validate(Path("output.xlsx"))

print(f"Production Ready: {report.is_production_ready}")
print(report.summary())

# Validate directory
reports = validate_all_in_directory("OutputExcel/", print_summary=True)
```

### SemanticMatcher

```python
from src.ontology.semantic_matcher import create_matcher, MatchResult

# Create matcher
matcher = create_matcher()

# Match a term
result: MatchResult = matcher.match_service_category("primary care visit")
print(f"Matched: {result.matched_term}")
print(f"Confidence: {result.confidence}")
print(f"Strategy: {result.strategy}")
```

---

## Quick Reference

### Common Commands

```powershell
# Process all PDFs
python -m src.main --input "../Plans" --output "../OutputExcel"

# Process single file with verbose output
python -m src.main --file "../Plans/document.pdf" --verbose

# Run unit tests
python -m pytest tests/unit/ -v

# Validate output quality
python -m src.validators.quality_validator "../OutputExcel/"

# Check for Python errors
python -m py_compile src/main.py
```

### Key Files to Modify

| Task | File |
|------|------|
| Add term mappings | `data/term_mappings.json` |
| Modify extraction patterns | `src/config/extraction_config.py` |
| Change output columns | `src/generators/excel_generator.py` |
| Add document types | `src/agents/classifier_agent.py` |
| Add validation rules | `src/validators/quality_validator.py` |

### Test Coverage Summary

```
115 unit tests across 8 test files:
- test_benefit_record.py      (29 tests)
- test_classifier_agent.py    (9 tests)
- test_extractor_agent.py     (8 tests)
- test_normalizer_agent.py    (18 tests)
- test_record_builder.py      (22 tests)
- test_semantic_matcher.py    (12 tests)
- test_table_extractor.py     (6 tests)
- test_validator.py           (11 tests)
```

---

## Support

For questions or issues:

1. Check logs using `--verbose` flag
2. Review `data/term_mappings.json` for term mapping issues
3. Run unit tests to verify component functionality
4. Check the troubleshooting section above
5. Review the validation report using `quality_validator.py`

---

*SPD Benefits Extraction - Version 2.0.0*
