# SPD Benefits Extraction - Project Overview & Execution Flow

## Overview

**SPD Benefits Extraction** is an Azure-native Intelligent Document Processing (IDP) solution that extracts healthcare benefits data from two-tier network SPD/SBC PDF documents and outputs standardized 15-column Excel files.

---

## 🔄 End-to-End Execution Flow Diagram

```
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│                        SPD BENEFITS EXTRACTION PIPELINE                                  │
│                     Azure-Native IDP Solution Architecture                               │
└─────────────────────────────────────────────────────────────────────────────────────────┘

┌──────────────────┐
│   INPUT SOURCE   │
│  ┌────────────┐  │
│  │ SPD/SBC    │  │     ┌─────────────────────────────────────────────────────────────┐
│  │ PDF Files  │──┼────▶│                    src/main.py                              │
│  │ (Plans/)   │  │     │  Entry point: Parses CLI args, initializes orchestrator    │
│  └────────────┘  │     └──────────────────────────┬──────────────────────────────────┘
└──────────────────┘                                │
                                                    ▼
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│                              ORCHESTRATOR (src/agents/orchestrator.py)                   │
│         Coordinates full extraction workflow: PDF → Classification → Extraction →       │
│                    Normalization → Validation → Excel Generation                         │
│                                                                                          │
│  ┌─────────────────────────────────────────────────────────────────────────────────┐    │
│  │                           6-STEP PROCESSING PIPELINE                             │    │
│  └─────────────────────────────────────────────────────────────────────────────────┘    │
│                                                                                          │
│  ╔═══════════════════════════════════════════════════════════════════════════════════╗  │
│  ║  STEP 1: PDF CONTENT EXTRACTION                                                   ║  │
│  ╠═══════════════════════════════════════════════════════════════════════════════════╣  │
│  ║                                                                                    ║  │
│  ║   ┌────────────────────────────────────────────────────────────────────────────┐  ║  │
│  ║   │           src/document_intelligence/pdf_processor.py                       │  ║  │
│  ║   │   Extracts text, tables, and layout from PDF using Azure Document          │  ║  │
│  ║   │   Intelligence (prebuilt-layout model) or local PyPDF2 fallback            │  ║  │
│  ║   └────────────────────────────────────────────────────────────────────────────┘  ║  │
│  ║                                        │                                          ║  │
│  ║                                        ▼                                          ║  │
│  ║                        ┌───────────────────────────────┐                          ║  │
│  ║                        │  Output: Dict containing:     │                          ║  │
│  ║                        │  • text: Full document text   │                          ║  │
│  ║                        │  • tables: List[Dict] tables  │                          ║  │
│  ║                        │  • page_count: int            │                          ║  │
│  ║                        └───────────────────────────────┘                          ║  │
│  ╚═══════════════════════════════════════════════════════════════════════════════════╝  │
│                                          │                                               │
│                                          ▼                                               │
│  ╔═══════════════════════════════════════════════════════════════════════════════════╗  │
│  ║  STEP 2: DOCUMENT CLASSIFICATION                                                  ║  │
│  ╠═══════════════════════════════════════════════════════════════════════════════════╣  │
│  ║                                                                                    ║  │
│  ║   ┌────────────────────────────────────────────────────────────────────────────┐  ║  │
│  ║   │              src/agents/classifier_agent.py                                │  ║  │
│  ║   │   Detects document type (SPD/SBC/SOB/COC), identifies two-tier network    │  ║  │
│  ║   │   column structure (IN/OON), maps sections to service categories           │  ║  │
│  ║   └────────────────────────────────────────────────────────────────────────────┘  ║  │
│  ║                                        │                                          ║  │
│  ║            ┌───────────────────────────┼───────────────────────────┐              ║  │
│  ║            ▼                           ▼                           ▼              ║  │
│  ║   ┌─────────────────┐    ┌──────────────────────┐    ┌─────────────────────┐     ║  │
│  ║   │ _detect_        │    │ _detect_network_     │    │ _detect_sections()  │     ║  │
│  ║   │ document_type() │    │ columns()            │    │ Identifies benefit  │     ║  │
│  ║   │ SPD/SBC/SOB/COC │    │ Maps IN/OON columns  │    │ table sections      │     ║  │
│  ║   └─────────────────┘    └──────────────────────┘    └─────────────────────┘     ║  │
│  ║                                        │                                          ║  │
│  ║                                        ▼                                          ║  │
│  ║                        ┌───────────────────────────────┐                          ║  │
│  ║                        │  Output: DocumentClassification│                         ║  │
│  ║                        │  • document_type: DocumentType │                         ║  │
│  ║                        │  • network_columns: List       │                         ║  │
│  ║                        │  • sections: List[Section]     │                         ║  │
│  ║                        │  • is_two_tier: bool           │                         ║  │
│  ║                        └───────────────────────────────┘                          ║  │
│  ╚═══════════════════════════════════════════════════════════════════════════════════╝  │
│                                          │                                               │
│                                          ▼                                               │
│  ╔═══════════════════════════════════════════════════════════════════════════════════╗  │
│  ║  STEP 3: BENEFITS DATA EXTRACTION                                                 ║  │
│  ╠═══════════════════════════════════════════════════════════════════════════════════╣  │
│  ║                                                                                    ║  │
│  ║   ┌────────────────────────────────────────────────────────────────────────────┐  ║  │
│  ║   │              src/agents/extractor_agent.py                                 │  ║  │
│  ║   │   Extracts raw benefit service rows from tables, captures IN/OON values,  │  ║  │
│  ║   │   detects limits, identifies pre-auth requirements                         │  ║  │
│  ║   └────────────────────────────────────────────────────────────────────────────┘  ║  │
│  ║                                        │                                          ║  │
│  ║            ┌───────────────────────────┼───────────────────────────┐              ║  │
│  ║            ▼                           ▼                           ▼              ║  │
│  ║   ┌─────────────────┐    ┌──────────────────────┐    ┌─────────────────────┐     ║  │
│  ║   │ _extract_from_  │    │ _find_column_index() │    │ _is_category_row()  │     ║  │
│  ║   │ tables()        │    │ Matches headers to   │    │ Detects service     │     ║  │
│  ║   │ Iterates rows   │    │ network keywords     │    │ category headers    │     ║  │
│  ║   └─────────────────┘    └──────────────────────┘    └─────────────────────┘     ║  │
│  ║                                        │                                          ║  │
│  ║                                        ▼                                          ║  │
│  ║                        ┌───────────────────────────────┐                          ║  │
│  ║                        │  Output: List[RawExtraction   │                          ║  │
│  ║                        │          Record]               │                         ║  │
│  ║                        │  • service_category: str       │                         ║  │
│  ║                        │  • in_network_text: str        │                         ║  │
│  ║                        │  • out_of_network_text: str    │                         ║  │
│  ║                        │  • limit_text: str             │                         ║  │
│  ║                        │  • page_number: int            │                         ║  │
│  ║                        └───────────────────────────────┘                          ║  │
│  ╚═══════════════════════════════════════════════════════════════════════════════════╝  │
│                                          │                                               │
│                                          ▼                                               │
│  ╔═══════════════════════════════════════════════════════════════════════════════════╗  │
│  ║  STEP 4: NORMALIZATION (Raw Text → 15-Column Schema)                              ║  │
│  ╠═══════════════════════════════════════════════════════════════════════════════════╣  │
│  ║                                                                                    ║  │
│  ║   ┌────────────────────────────────────────────────────────────────────────────┐  ║  │
│  ║   │              src/agents/normalizer_agent.py                                │  ║  │
│  ║   │   Transforms raw text to standardized schema: parses "80% after           │  ║  │
│  ║   │   Deductible" → {coinsurance: 80%, after_ded: Yes}, maps network terms    │  ║  │
│  ║   └────────────────────────────────────────────────────────────────────────────┘  ║  │
│  ║                                        │                                          ║  │
│  ║   ┌────────────────────────────────────┴────────────────────────────────────┐    ║  │
│  ║   │                   NORMALIZATION TRANSFORMATIONS                          │    ║  │
│  ║   │                                                                          │    ║  │
│  ║   │  "80% after Deductible"  ───▶  coinsurance: "80%"                       │    ║  │
│  ║   │                                after_deductible: "Yes"                   │    ║  │
│  ║   │                                                                          │    ║  │
│  ║   │  "$20 copay"             ───▶  copay: "$20"                             │    ║  │
│  ║   │                                                                          │    ║  │
│  ║   │  "Non-Network"           ───▶  "Out-of-Network"                         │    ║  │
│  ║   │  "Non-Par", "OON"        ───▶  "Out-of-Network"                         │    ║  │
│  ║   │                                                                          │    ║  │
│  ║   │  "90 visits per year"    ───▶  limit_type: "90 visits"                  │    ║  │
│  ║   │                                limit_period: "Benefit Year"              │    ║  │
│  ║   └──────────────────────────────────────────────────────────────────────────┘    ║  │
│  ║                                        │                                          ║  │
│  ║               Uses: src/ontology/benefits_ontology.py for mappings               ║  │
│  ║                                        │                                          ║  │
│  ║                                        ▼                                          ║  │
│  ║                        ┌───────────────────────────────┐                          ║  │
│  ║                        │  Output: List[BenefitRecord]  │                          ║  │
│  ║                        │  (15-column schema)           │                          ║  │
│  ║                        │  See model definition below   │                          ║  │
│  ║                        └───────────────────────────────┘                          ║  │
│  ╚═══════════════════════════════════════════════════════════════════════════════════╝  │
│                                          │                                               │
│                                          ▼                                               │
│  ╔═══════════════════════════════════════════════════════════════════════════════════╗  │
│  ║  STEP 5: VALIDATION & CONFIDENCE SCORING                                          ║  │
│  ╠═══════════════════════════════════════════════════════════════════════════════════╣  │
│  ║                                                                                    ║  │
│  ║   ┌──────────────────────────────────┐  ┌──────────────────────────────────────┐  ║  │
│  ║   │ src/validators/                  │  │ src/validators/                      │  ║  │
│  ║   │ deterministic_validator.py       │  │ confidence_scorer.py                 │  ║  │
│  ║   │                                  │  │                                      │  ║  │
│  ║   │ Validates extracted data using   │  │ Calculates confidence score (0-1)   │  ║  │
│  ║   │ deterministic rules:             │  │ based on:                           │  ║  │
│  ║   │ • IN/OON coinsurance: 0-100%    │  │ • Field completeness                │  ║  │
│  ║   │ • Family ded >= Individual ded  │  │ • Pattern matching accuracy          │  ║  │
│  ║   │ • Required fields present        │  │ • Validation rule compliance        │  ║  │
│  ║   │ • Format consistency checks      │  │ • Data consistency                   │  ║  │
│  ║   └──────────────────────────────────┘  └──────────────────────────────────────┘  ║  │
│  ║                       │                              │                            ║  │
│  ║                       ▼                              ▼                            ║  │
│  ║              ┌─────────────────┐            ┌─────────────────────┐               ║  │
│  ║              │ ValidationIssue │            │ confidence_score:   │               ║  │
│  ║              │ • record_index  │            │ 0.0 - 1.0           │               ║  │
│  ║              │ • field_name    │            │                     │               ║  │
│  ║              │ • issue_type    │            │ Threshold: 0.70     │               ║  │
│  ║              │ • severity      │            │ (configurable)      │               ║  │
│  ║              └─────────────────┘            └─────────────────────┘               ║  │
│  ║                                                     │                             ║  │
│  ║                              ┌──────────────────────┴──────────────────────┐      ║  │
│  ║                              ▼                                              ▼     ║  │
│  ║              ┌─────────────────────────────┐      ┌─────────────────────────────┐ ║  │
│  ║              │    Confidence >= 70%        │      │    Confidence < 70%         │ ║  │
│  ║              │    ✅ AUTO-APPROVE          │      │    ⚠️ HUMAN REVIEW QUEUE    │ ║  │
│  ║              │    Direct to Excel          │      │    Azure App Service        │ ║  │
│  ║              └─────────────────────────────┘      └─────────────────────────────┘ ║  │
│  ╚═══════════════════════════════════════════════════════════════════════════════════╝  │
│                                          │                                               │
│                                          ▼                                               │
│  ╔═══════════════════════════════════════════════════════════════════════════════════╗  │
│  ║  STEP 6: EXCEL GENERATION                                                          ║  │
│  ╠═══════════════════════════════════════════════════════════════════════════════════╣  │
│  ║                                                                                    ║  │
│  ║   ┌────────────────────────────────────────────────────────────────────────────┐  ║  │
│  ║   │              src/generators/excel_generator.py                             │  ║  │
│  ║   │   Generates Excel files using openpyxl with 15-column schema,              │  ║  │
│  ║   │   applies styling, creates metadata sheet if configured                     │  ║  │
│  ║   └────────────────────────────────────────────────────────────────────────────┘  ║  │
│  ║                                        │                                          ║  │
│  ║                                        ▼                                          ║  │
│  ║   ┌────────────────────────────────────────────────────────────────────────────┐  ║  │
│  ║   │                       15-COLUMN EXCEL SCHEMA                                │  ║  │
│  ║   ├────────────────────────────────────────────────────────────────────────────┤  ║  │
│  ║   │  Col 1-2:  Header | Service                                                │  ║  │
│  ║   │  Col 3-5:  In-Network Coinsurance | After Deductible | Copay              │  ║  │
│  ║   │  Col 6-8:  Out-of-Network Coinsurance | After Deductible | Copay          │  ║  │
│  ║   │  Col 9-12: Individual IN | Family IN | Individual OON | Family OON        │  ║  │
│  ║   │  Col 13-14: Limit Type | Limit Period                                      │  ║  │
│  ║   │  Col 15: Pre-Authorization Required                                        │  ║  │
│  ║   └────────────────────────────────────────────────────────────────────────────┘  ║  │
│  ╚═══════════════════════════════════════════════════════════════════════════════════╝  │
│                                          │                                               │
│                                          ▼                                               │
│  ┌─────────────────────────────────────────────────────────────────────────────────┐    │
│  │                           ProcessingResult                                       │    │
│  │  • source_file: str           • overall_confidence: float                       │    │
│  │  • output_file: str           • requires_review: bool                           │    │
│  │  • success: bool              • validation_issues: int                          │    │
│  │  • records_extracted: int     • error_message: Optional[str]                   │    │
│  └─────────────────────────────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────────────────────────────┘
                                           │
                                           ▼
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│                                    OUTPUT                                                │
│                                                                                          │
│   ┌─────────────────────────────┐              ┌─────────────────────────────────────┐  │
│   │     OutputExcel/            │              │       Azure Blob Storage            │  │
│   │  ┌────────────────────┐     │              │   ┌─────────────────────────────┐   │  │
│   │  │ {plan_name}_       │     │     OR       │   │ spd-output container        │   │  │
│   │  │  Benefits.xlsx     │     │ ◄───────────▶│   │ • Excel files               │   │  │
│   │  │                    │     │              │   │ • Download URL              │   │  │
│   │  │ 15-column schema   │     │              │   └─────────────────────────────┘   │  │
│   │  └────────────────────┘     │              │                                     │  │
│   └─────────────────────────────┘              └─────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 📊 Data Models Flow

```
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│                         DATA MODELS (src/models/benefit_record.py)                       │
└─────────────────────────────────────────────────────────────────────────────────────────┘

  ┌───────────────────┐         ┌───────────────────┐         ┌───────────────────┐
  │ RawExtractionRecord│   ───▶ │   BenefitRecord   │   ───▶ │ ExtractionResult  │
  │                   │  Norm.  │  (15-col schema)  │  Aggr.  │   (Container)     │
  └───────────────────┘         └───────────────────┘         └───────────────────┘
         │                              │                              │
         ▼                              ▼                              ▼
  ┌─────────────────────┐      ┌─────────────────────┐      ┌─────────────────────┐
  │ • service_category  │      │ • header            │      │ • document_id       │
  │ • service_name      │      │ • service           │      │ • classification    │
  │ • in_network_text   │      │ • in_network_coins  │      │ • benefit_records[] │
  │   "80% after ded"   │      │   "80%"             │      │ • raw_records[]     │
  │ • out_network_text  │      │ • in_network_aft_ded│      │ • validation_issues │
  │ • limit_text        │      │   "Yes"             │      │ • overall_confidence│
  │ • page_number       │      │ • copay "$20"       │      │ • requires_review   │
  │ • raw_confidence    │      │ • limit_type        │      │ • metadata          │
  └─────────────────────┘      │ • limit_period      │      └─────────────────────┘
                               │ • preauth_required  │
                               │ • confidence_score  │
                               └─────────────────────┘
```

---

## 🔧 Component Summary Table

| Step | Component | File Path | One-Line Description |
|------|-----------|-----------|---------------------|
| Entry | **Main** | `src/main.py` | Entry point that parses CLI arguments and invokes the orchestrator |
| 0 | **Orchestrator** | `src/agents/orchestrator.py` | Coordinates the 6-step pipeline and manages agent workflow |
| 1 | **PDF Processor** | `src/document_intelligence/pdf_processor.py` | Extracts text/tables from PDF using Azure Doc Intelligence or PyPDF2 |
| 2 | **Classifier Agent** | `src/agents/classifier_agent.py` | Detects document type (SPD/SBC) and two-tier network column structure |
| 3 | **Extractor Agent** | `src/agents/extractor_agent.py` | Extracts raw benefit rows from tables with IN/OON values and limits |
| 4 | **Normalizer Agent** | `src/agents/normalizer_agent.py` | Transforms raw text to 15-column schema (parses "80% after ded" → structured) |
| 5a | **Deterministic Validator** | `src/validators/deterministic_validator.py` | Validates data with rules (coinsurance 0-100%, family≥individual ded) |
| 5b | **Confidence Scorer** | `src/validators/confidence_scorer.py` | Calculates confidence score (0-1) for human review routing |
| 6 | **Excel Generator** | `src/generators/excel_generator.py` | Generates 15-column Excel output with openpyxl styling |
| Data | **BenefitRecord** | `src/models/benefit_record.py` | Pydantic model defining the 15-column output schema with validators |
| Config | **Settings** | `src/config/settings.py` | Pydantic BaseSettings for Azure services and processing configuration |

---

## 🌐 Azure Services Integration

```
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│                          SUPPORTING AZURE SERVICES                                       │
└─────────────────────────────────────────────────────────────────────────────────────────┘

┌──────────────────┐    ┌──────────────────┐    ┌──────────────────┐    ┌──────────────────┐
│  Blob Storage    │    │   Service Bus    │    │    Azure SQL     │    │   Key Vault      │
│  PDFs & Output   │    │   Job Queue      │    │   Data Store     │    │   Secrets        │
└────────┬─────────┘    └────────┬─────────┘    └────────┬─────────┘    └────────┬─────────┘
         │                       │                       │                       │
         ▼                       ▼                       ▼                       ▼
┌──────────────────┐    ┌──────────────────┐    ┌──────────────────┐    ┌──────────────────┐
│ blob_storage_    │    │ service_bus_     │    │ sql_service.py   │    │ key_vault_       │
│ service.py       │    │ service.py       │    │                  │    │ service.py       │
│                  │    │                  │    │                  │    │                  │
│ • upload_blob()  │    │ • send_message() │    │ • execute_query()│    │ • get_secret()   │
│ • download_blob()│    │ • receive_msgs() │    │ • store_result() │    │ • set_secret()   │
│ • list_blobs()   │    │ • close()        │    │                  │    │                  │
└──────────────────┘    └──────────────────┘    └──────────────────┘    └──────────────────┘
         │                       │                       │                       │
         └───────────────────────┴───────────────────────┴───────────────────────┘
                                               │
                                               ▼
                                    ┌──────────────────┐
                                    │   App Insights   │
                                    │   Monitoring     │
                                    │                  │
                                    │ • Traces         │
                                    │ • Metrics        │
                                    │ • Exceptions     │
                                    └──────────────────┘
```

---

## 📁 Project Structure

```
spd-benefits-extraction/
├── src/
│   ├── main.py                              # 🚀 CLI entry point
│   ├── config/settings.py                   # ⚙️ Pydantic configuration
│   ├── agents/
│   │   ├── orchestrator.py                  # 🎯 Pipeline coordinator
│   │   ├── classifier_agent.py              # 📋 Document type detection
│   │   ├── extractor_agent.py               # 🔍 Raw data extraction
│   │   └── normalizer_agent.py              # 🔄 Schema transformation
│   ├── document_intelligence/
│   │   └── pdf_processor.py                 # 📄 Azure DI integration
│   ├── validators/
│   │   ├── deterministic_validator.py       # ✅ Rule-based validation
│   │   └── confidence_scorer.py             # 📊 Confidence calculation
│   ├── generators/
│   │   └── excel_generator.py               # 📊 Excel output
│   └── models/
│       └── benefit_record.py                # 📝 15-column Pydantic models
├── functions/                               # ☁️ Azure Functions triggers
├── OutputExcel/                             # 📁 Generated Excel files
└── Plans/ (InputData/)                      # 📁 Input PDF documents
```

---

## 🚀 Usage

### Process all PDFs in a directory
```powershell
python -m src.main --input "../Plans" --output "../OutputExcel"
```

### Process a single file
```powershell
python -m src.main --file "../Plans/M000-999 HDHP 1500 (Q)_HDHP_SPD.pdf"
```

### Verbose logging
```powershell
python -m src.main --input "../Plans" --output "../OutputExcel" --verbose
```

---

## ⚙️ Configuration

Configure Azure services in `.env`:

```env
# Azure OpenAI
AZURE_OPENAI_ENDPOINT=https://your-endpoint.openai.azure.com/
AZURE_OPENAI_KEY=your_key
AZURE_OPENAI_DEPLOYMENT=gpt-4.1

# Azure Document Intelligence (for better table extraction)
AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT=your_endpoint
AZURE_DOCUMENT_INTELLIGENCE_KEY=your_key
```

---

## 📈 Output Format (15-Column Schema)

| Column | Description |
|--------|-------------|
| Header | Service category (e.g., "Inpatient Services") |
| Service | Specific service name |
| In-Network Coinsurance | Plan pays percentage (e.g., "80%") |
| In-Network After Deductible Flag | "Yes" or "No" |
| In-Network Copay | Fixed copay amount (e.g., "$20") |
| Out-Of-Network Coinsurance | OON plan pays percentage |
| Out-Of-Network After Deductible Flag | "Yes" or "No" |
| Out-Of-Network Copay | OON fixed copay amount |
| Individual In-Network | Individual deductible/OOP max |
| Family In-Network | Family deductible/OOP max |
| Individual Out-Of-Network | OON individual deductible/OOP max |
| Family Out-Of-Network | OON family deductible/OOP max |
| Limit Type | Visit/dollar limits (e.g., "60 visits") |
| Limit Period | "Benefit Year", "Calendar Year", "Lifetime" |
| Pre-Authorization Required | "Yes", "No", or "N/A" |
