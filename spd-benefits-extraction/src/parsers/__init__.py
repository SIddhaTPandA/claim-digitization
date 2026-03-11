# Parsers module for SPD Benefits Extraction
"""
Parsing utilities for benefit extraction.

Main components:
- StructuredTableExtractor: Schema-bound table extraction with header filtering
- SchemaRecordBuilder: Converts extracted rows to BenefitRecord objects
- BenefitTextParser: Text-based extraction fallback
"""

from src.parsers.table_extractor import (
    StructuredTableExtractor,
    ColumnRole,
    ColumnSchema,
    ExtractedRow,
)
from src.parsers.record_builder import (
    SchemaRecordBuilder,
    ValueParser,
    RecordDeduplicator,
    build_records_from_tables,
)
from src.parsers.benefit_text_parser import (
    BenefitTextParser,
    ParsedBenefit,
)

__all__ = [
    "StructuredTableExtractor",
    "ColumnRole",
    "ColumnSchema",
    "ExtractedRow",
    "SchemaRecordBuilder",
    "ValueParser",
    "RecordDeduplicator",
    "build_records_from_tables",
    "BenefitTextParser",
    "ParsedBenefit",
]