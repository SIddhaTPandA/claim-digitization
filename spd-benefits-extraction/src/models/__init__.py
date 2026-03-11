"""
Data models for SPD Benefits Extraction.

This module provides Pydantic models for the complete extraction pipeline:
- Classification models for document structure detection
- Extraction models for raw and normalized benefit data
- Validation models for quality assurance
- Result models for output generation
"""

from src.models.benefit_record import (
    # Enums
    CoverageStatus,
    DocumentType,
    LimitPeriod,
    NetworkTier,
    ServiceCategoryType,
    # Core models
    BenefitRecord,
    DocumentClassification,
    DocumentSection,
    ExtractionMetadata,
    ExtractionResult,
    NetworkColumnMapping,
    RawExtractionRecord,
    ValidationIssue,
    # Validation utilities
    validate_coinsurance,
    validate_copay,
    validate_limit,
    validate_monetary_amount,
)

__all__ = [
    # Enums
    "DocumentType",
    "NetworkTier",
    "CoverageStatus",
    "LimitPeriod",
    "ServiceCategoryType",
    # Core models
    "BenefitRecord",
    "RawExtractionRecord",
    "DocumentSection",
    "NetworkColumnMapping",
    "DocumentClassification",
    "ExtractionMetadata",
    "ValidationIssue",
    "ExtractionResult",
    # Validation utilities
    "validate_coinsurance",
    "validate_copay",
    "validate_monetary_amount",
    "validate_limit",
]