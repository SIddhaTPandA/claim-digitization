# This file marks the ontology directory as a Python package.
"""
Ontology module for semantic normalization of benefits terminology.

Provides data-driven, flexible term matching that loads configurations
from external JSON files - no hardcoded terms in Python code.
"""

from src.ontology.semantic_matcher import (
    MatchResult,
    SemanticMatcher,
    NetworkTermMatcher,
    ServiceCategoryMatcher,
    LimitPeriodMatcher,
    TermMappingConfig,
    load_mapping_config,
    create_matcher,
)

__all__ = [
    "MatchResult",
    "SemanticMatcher",
    "NetworkTermMatcher",
    "ServiceCategoryMatcher",
    "LimitPeriodMatcher",
    "TermMappingConfig",
    "load_mapping_config",
    "create_matcher",
]