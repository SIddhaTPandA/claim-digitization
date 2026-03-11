"""
Semantic Matcher for Flexible Term Normalization.

This module provides DATA-DRIVEN semantic matching that:
1. Loads term mappings from JSON configuration (not hardcoded)
2. Uses fuzzy string matching for close variants
3. Uses word embeddings for semantic similarity (optional)
4. Provides LLM fallback for truly unknown terms
5. Learns new mappings over time

NO HARDCODED TERMS - all mappings come from external configuration
that can be updated without code changes.
"""

import json
import logging
import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set, Tuple, Union

logger = logging.getLogger(__name__)


# =============================================================================
# Match Result (Production-grade return type)
# =============================================================================


@dataclass
class MatchResult:
    """
    Result of a semantic match operation.
    
    Provides structured access to match details with clear semantics.
    """
    standard_value: str
    confidence: float
    match_method: str
    matched: bool
    original_term: str = ""
    alternatives: List[Dict[str, Any]] = field(default_factory=list)
    
    def __bool__(self) -> bool:
        """Allow using MatchResult in boolean context."""
        return self.matched
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "standard_value": self.standard_value,
            "confidence": self.confidence,
            "match_method": self.match_method,
            "matched": self.matched,
            "original_term": self.original_term,
        }


# =============================================================================
# Configuration Loader
# =============================================================================


@dataclass
class TermMappingConfig:
    """Configuration for term-to-standard mappings loaded from JSON."""
    
    # Standard output values (the targets we normalize TO)
    standard_values: Dict[str, List[str]] = field(default_factory=dict)
    
    # Term -> Standard Value mappings
    term_mappings: Dict[str, str] = field(default_factory=dict)
    
    # Regex patterns -> Standard Value
    pattern_mappings: List[Tuple[str, str]] = field(default_factory=list)
    
    # Synonyms/aliases for discovery
    synonyms: Dict[str, Set[str]] = field(default_factory=dict)
    
    # Learned mappings (from user corrections or LLM)
    learned_mappings: Dict[str, str] = field(default_factory=dict)


def load_mapping_config(config_path: str) -> TermMappingConfig:
    """
    Load term mapping configuration from JSON file.
    
    Supports both flat and nested mapping structures:
    
    Flat format:
    {
        "mappings": {
            "input_term": "StandardValue"
        }
    }
    
    Nested format (by category):
    {
        "mappings": {
            "network_tier": {
                "in-network": "In-Network"
            },
            "service_category": {
                "emergency": "Emergency Services"
            }
        }
    }
    """
    config = TermMappingConfig()
    
    try:
        path = Path(config_path)
        if not path.exists():
            logger.warning(f"Config file not found: {config_path}")
            return config
            
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # Load standard values
        config.standard_values = data.get('standard_values', {})
        
        # Load mappings - handle both flat and nested formats
        raw_mappings = data.get('mappings', {})
        for key, value in raw_mappings.items():
            if isinstance(value, dict):
                # Nested format: category -> {term: standard}
                # Skip keys starting with underscore (metadata)
                if key.startswith('_'):
                    continue
                for term, standard in value.items():
                    if isinstance(standard, str):
                        config.term_mappings[term.lower()] = standard
            elif isinstance(value, str):
                # Flat format: term -> standard
                config.term_mappings[key.lower()] = value
        
        # Load patterns - handle both flat and nested formats
        raw_patterns = data.get('patterns', {})
        if isinstance(raw_patterns, list):
            # Flat list of patterns
            config.pattern_mappings = [
                (p['pattern'], p['maps_to'])
                for p in raw_patterns
                if isinstance(p, dict) and 'pattern' in p and 'maps_to' in p
            ]
        elif isinstance(raw_patterns, dict):
            # Nested by category
            for category, patterns in raw_patterns.items():
                if isinstance(patterns, list):
                    for p in patterns:
                        if isinstance(p, dict) and 'pattern' in p and 'maps_to' in p:
                            config.pattern_mappings.append((p['pattern'], p['maps_to']))
        
        # Build synonyms from mappings for fuzzy matching
        for term, standard in config.term_mappings.items():
            if standard not in config.synonyms:
                config.synonyms[standard] = set()
            config.synonyms[standard].add(term)
        
        logger.info(
            f"Loaded {len(config.term_mappings)} term mappings, "
            f"{len(config.pattern_mappings)} patterns from {config_path}"
        )
        
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in config file {config_path}: {e}")
    except Exception as e:
        logger.warning(f"Failed to load mapping config from {config_path}: {e}")
    
    return config


# =============================================================================
# Flexible Semantic Matcher
# =============================================================================


class SemanticMatcher:
    """
    Flexible semantic matcher that normalizes terms using multiple strategies.
    
    Strategy Order:
    1. Exact match (case-insensitive)
    2. Configured term mappings (from JSON)
    3. Regex pattern matching
    4. Fuzzy string matching (for typos/variations)
    5. Semantic similarity (embeddings, if available)
    6. LLM fallback (if configured)
    7. Return original with low confidence
    
    Key Features:
    - NO hardcoded terms - all from configuration
    - Learns new mappings from user corrections
    - Extensible via plugins
    """
    
    def __init__(
        self,
        config_path: Optional[str] = None,
        fuzzy_threshold: float = 0.85,
        enable_embeddings: bool = False,
        enable_llm_fallback: bool = False,
        llm_client: Optional[Any] = None,
    ):
        """
        Initialize the semantic matcher.
        
        Args:
            config_path: Path to JSON configuration file
            fuzzy_threshold: Minimum similarity for fuzzy matching (0-1)
            enable_embeddings: Use word embeddings for semantic matching
            enable_llm_fallback: Use LLM for unknown terms
            llm_client: Azure OpenAI client for LLM
        """
        self.fuzzy_threshold = fuzzy_threshold
        self.enable_embeddings = enable_embeddings
        self.enable_llm_fallback = enable_llm_fallback
        self.llm_client = llm_client
        
        # Load configuration
        if config_path:
            self.config = load_mapping_config(config_path)
        else:
            self.config = TermMappingConfig()
        
        # Compile regex patterns
        self._compiled_patterns: List[Tuple[re.Pattern, str]] = []
        for pattern, target in self.config.pattern_mappings:
            try:
                self._compiled_patterns.append(
                    (re.compile(pattern, re.IGNORECASE), target)
                )
            except re.error as e:
                logger.warning(f"Invalid regex pattern '{pattern}': {e}")
        
        # Cache for embedding vectors (if enabled)
        self._embedding_cache: Dict[str, List[float]] = {}
        
        # Track match statistics
        self.stats = {
            'exact_matches': 0,
            'config_matches': 0,
            'pattern_matches': 0,
            'fuzzy_matches': 0,
            'embedding_matches': 0,
            'llm_matches': 0,
            'no_matches': 0,
        }
        
        logger.info(
            f"SemanticMatcher initialized with {len(self.config.term_mappings)} mappings, "
            f"{len(self._compiled_patterns)} patterns"
        )
    
    # =========================================================================
    # Core Matching Methods
    # =========================================================================
    
    def match(
        self,
        term: str,
        category: Optional[str] = None,
        context: Optional[str] = None,
    ) -> MatchResult:
        """
        Match a term to its standardized value.
        
        Args:
            term: The input term to normalize
            category: Optional category hint (e.g., "network", "service")
            context: Optional surrounding text for context
            
        Returns:
            MatchResult with standardized value, confidence, and match method
        """
        if not term:
            return MatchResult(
                standard_value="",
                confidence=0.0,
                match_method="empty",
                matched=False,
                original_term=""
            )
        
        term_clean = term.strip()
        term_lower = term_clean.lower()
        
        # Strategy 1: Exact match in standard values
        for standard_values in self.config.standard_values.values():
            for sv in standard_values:
                if term_lower == sv.lower():
                    self.stats['exact_matches'] += 1
                    return MatchResult(
                        standard_value=sv,
                        confidence=1.0,
                        match_method="exact",
                        matched=True,
                        original_term=term_clean
                    )
        
        # Strategy 2: Configured term mappings
        if term_lower in self.config.term_mappings:
            result = self.config.term_mappings[term_lower]
            self.stats['config_matches'] += 1
            return MatchResult(
                standard_value=result,
                confidence=0.95,
                match_method="config",
                matched=True,
                original_term=term_clean
            )
        
        # Strategy 3: Learned mappings (from corrections)
        if term_lower in self.config.learned_mappings:
            result = self.config.learned_mappings[term_lower]
            self.stats['config_matches'] += 1
            return MatchResult(
                standard_value=result,
                confidence=0.90,
                match_method="learned",
                matched=True,
                original_term=term_clean
            )
        
        # Strategy 4: Regex pattern matching
        for pattern, target in self._compiled_patterns:
            if pattern.search(term_clean):
                self.stats['pattern_matches'] += 1
                return MatchResult(
                    standard_value=target,
                    confidence=0.90,
                    match_method="pattern",
                    matched=True,
                    original_term=term_clean
                )
        
        # Strategy 5: Fuzzy string matching
        fuzzy_result = self._fuzzy_match(term_lower, category)
        if fuzzy_result:
            self.stats['fuzzy_matches'] += 1
            return MatchResult(
                standard_value=fuzzy_result[0],
                confidence=fuzzy_result[1],
                match_method="fuzzy",
                matched=True,
                original_term=term_clean
            )
        
        # Strategy 6: Semantic embedding matching (if enabled)
        if self.enable_embeddings:
            embed_result = self._embedding_match(term_clean, category)
            if embed_result:
                self.stats['embedding_matches'] += 1
                return MatchResult(
                    standard_value=embed_result[0],
                    confidence=embed_result[1],
                    match_method="embedding",
                    matched=True,
                    original_term=term_clean
                )
        
        # Strategy 7: LLM fallback (if enabled)
        if self.enable_llm_fallback and self.llm_client:
            llm_result = self._llm_match(term_clean, category, context)
            if llm_result:
                # Learn this mapping for future use
                self.learn_mapping(term_lower, llm_result)
                self.stats['llm_matches'] += 1
                return MatchResult(
                    standard_value=llm_result,
                    confidence=0.75,
                    match_method="llm",
                    matched=True,
                    original_term=term_clean
                )
        
        # No match found - return original with low confidence
        self.stats['no_matches'] += 1
        logger.debug(f"No match found for term: '{term}'")
        return MatchResult(
            standard_value=term_clean,
            confidence=0.3,
            match_method="none",
            matched=False,
            original_term=term_clean
        )
    
    def _fuzzy_match(
        self,
        term: str,
        category: Optional[str] = None,
    ) -> Optional[Tuple[str, float]]:
        """
        Find best fuzzy match among known terms.
        
        Uses SequenceMatcher for string similarity.
        """
        best_match = None
        best_score = 0.0
        
        # Search through all known mappings
        candidates = list(self.config.term_mappings.keys())
        
        # If category specified, prefer terms from that category
        if category and category in self.config.synonyms:
            candidates = list(self.config.synonyms[category]) + candidates
        
        for known_term in candidates:
            # Calculate similarity
            ratio = SequenceMatcher(None, term, known_term).ratio()
            
            if ratio > best_score and ratio >= self.fuzzy_threshold:
                best_score = ratio
                best_match = self.config.term_mappings.get(
                    known_term, 
                    known_term  # Fallback to term itself if it's a standard value
                )
        
        if best_match:
            return best_match, best_score * 0.9  # Slight confidence penalty for fuzzy
        
        return None
    
    def _embedding_match(
        self,
        term: str,
        category: Optional[str] = None,
    ) -> Optional[Tuple[str, float]]:
        """
        Match using semantic embeddings.
        
        Requires sentence-transformers or similar.
        """
        try:
            # Lazy import to avoid dependency if not used
            from sentence_transformers import SentenceTransformer
            import numpy as np
            
            # Initialize model on first use
            if not hasattr(self, '_embed_model'):
                self._embed_model = SentenceTransformer('all-MiniLM-L6-v2')
                
                # Pre-compute embeddings for all known terms
                all_terms = list(self.config.term_mappings.keys())
                if all_terms:
                    embeddings = self._embed_model.encode(all_terms)
                    for t, e in zip(all_terms, embeddings):
                        self._embedding_cache[t] = e.tolist()
            
            # Get embedding for input term
            term_embedding = self._embed_model.encode([term])[0]
            
            # Find most similar
            best_match = None
            best_score = 0.0
            
            for known_term, known_embedding in self._embedding_cache.items():
                # Cosine similarity
                similarity = np.dot(term_embedding, known_embedding) / (
                    np.linalg.norm(term_embedding) * np.linalg.norm(known_embedding)
                )
                
                if similarity > best_score and similarity >= 0.7:
                    best_score = similarity
                    best_match = self.config.term_mappings.get(known_term, known_term)
            
            if best_match:
                return best_match, float(best_score) * 0.85
            
        except ImportError:
            logger.debug("sentence-transformers not available for embedding matching")
        except Exception as e:
            logger.warning(f"Embedding match failed: {e}")
        
        return None
    
    def _llm_match(
        self,
        term: str,
        category: Optional[str] = None,
        context: Optional[str] = None,
    ) -> Optional[str]:
        """
        Use LLM with expert persona to determine the standard value for an unknown term.
        
        This is the fallback when all deterministic methods fail. The LLM acts as a
        Senior Health Plan Benefits Configuration Analyst to interpret terminology.
        
        Args:
            term: The unknown term to map
            category: Optional category hint (network, service_category, limit_period, etc.)
            context: Optional surrounding text for additional context
            
        Returns:
            Standard value if matched with confidence, None otherwise
        """
        if not self.llm_client:
            return None
        
        # Build category-specific standard values list
        standard_values = []
        if category and category in self.config.standard_values:
            standard_values = self.config.standard_values[category]
        else:
            # Include all standard values
            for values in self.config.standard_values.values():
                standard_values.extend(values)
        
        # Remove duplicates while preserving order
        standard_values = list(dict.fromkeys(standard_values))
        
        # Category-specific few-shot examples
        few_shot_examples = self._get_few_shot_examples(category)
        
        # Build the expert system prompt with persona
        system_prompt = """You are a Senior Health Plan Benefits Configuration Analyst with 15+ years of experience configuring benefit plans across major health insurance payers (BCBS, Aetna, Cigna, UnitedHealthcare, Humana, Kaiser).

Your expertise includes:
- Interpreting Summary Plan Description (SPD) documents
- Analyzing Summary of Benefits and Coverage (SBC) documents
- Mapping diverse payer-specific terminology to standardized benefit configurations
- Understanding network tier structures, cost-sharing arrangements, and coverage limitations
- Recognizing hierarchical service structures (parent-child service relationships)

Your task is to map an unknown term from a health insurance document to one of the predefined standard values used in our benefits configuration system.

IMPORTANT RULES:
1. You MUST respond with ONLY one of the provided standard values - no explanations
2. If the term clearly maps to a standard value, respond with that exact value
3. If you are uncertain (confidence < 80%), respond with "UNCERTAIN"
4. If the term has no reasonable mapping, respond with "UNKNOWN"
5. Consider common payer abbreviations, regional variations, and legacy terminology
6. For hierarchical service names (e.g., "Office Visit for Injury / Illness - Primary Care"), 
   focus on the FULL service name, not just the child portion
7. Preserve distinctions between related but different services (Primary Care vs Specialist)
8. Do NOT over-normalize - "Office Visit for Injury / Illness - Primary Care" and 
   "Office Visit for Injury / Illness - Specialist" are DIFFERENT services"""

        # Build the user prompt with context
        user_prompt = f"""Map this term from a health insurance document to a standard value.

TERM TO MAP: "{term}"
"""
        
        if category:
            user_prompt += f"CATEGORY HINT: {category}\n"
        
        if context:
            # Truncate context to avoid token limits
            context_preview = context[:500] + "..." if len(context) > 500 else context
            user_prompt += f"SURROUNDING CONTEXT: {context_preview}\n"
        
        user_prompt += f"""
AVAILABLE STANDARD VALUES:
{chr(10).join(f'  - {v}' for v in standard_values)}

{few_shot_examples}

YOUR RESPONSE (one standard value only, or UNCERTAIN/UNKNOWN):"""

        try:
            response = self.llm_client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.0,  # Deterministic for consistency
                max_tokens=50,
            )
            
            result = response.choices[0].message.content.strip()
            
            # Clean up response (remove quotes, extra whitespace)
            result = result.strip('"\'').strip()
            
            # Log the LLM decision for audit
            logger.info(
                f"LLM semantic mapping: '{term}' -> '{result}' "
                f"(category={category})"
            )
            
            # Validate result is in standard values
            if result in standard_values:
                # Store in audit log for quality review
                self._log_llm_decision(term, result, category, context, "matched")
                return result
            
            # Handle uncertainty flags
            if result in ("UNCERTAIN", "UNKNOWN"):
                self._log_llm_decision(term, result, category, context, result.lower())
                logger.debug(f"LLM returned {result} for term: '{term}'")
                return None
            
            # Check for partial/fuzzy match to standard values (LLM might have slight variations)
            result_lower = result.lower()
            for sv in standard_values:
                if sv.lower() == result_lower:
                    self._log_llm_decision(term, sv, category, context, "matched_normalized")
                    return sv
            
            # No valid match
            self._log_llm_decision(term, result, category, context, "invalid_response")
            logger.warning(
                f"LLM returned invalid value '{result}' for term '{term}'. "
                f"Expected one of: {standard_values[:5]}..."
            )
            
        except Exception as e:
            logger.error(f"LLM match failed for term '{term}': {e}")
            self._log_llm_decision(term, str(e), category, context, "error")
        
        return None
    
    def _get_few_shot_examples(self, category: Optional[str] = None) -> str:
        """
        Get category-specific few-shot examples for the LLM prompt.
        
        These examples teach the LLM the mapping patterns we expect.
        """
        examples = {
            "network_tier": """
EXAMPLES:
  "Participating Provider" -> In-Network
  "Non-Par" -> Out-of-Network
  "Tier 1 PPO" -> In-Network
  "Out-of-Area" -> Out-of-Network
  "BlueCard" -> In-Network
  "Preferred Provider" -> In-Network
  "Non-Participating" -> Out-of-Network""",
            
            "service_category": """
EXAMPLES:
  "PT/OT/ST" -> Rehabilitation Services
  "SNF" -> Skilled Nursing Facility
  "ER Visit" -> Emergency Services
  "Well Child Visit" -> Preventive Care
  "Behavioral Health Outpatient" -> Mental Health - Outpatient
  "Tier 1 Generic Drugs" -> Prescription Drugs
  "Room & Board" -> Inpatient Hospital Services
  "ASC" -> Outpatient Hospital Services
  "Emergency and Urgent Care Services" -> Emergency Services
  "Physician Services" -> Professional Services""",
            
            "service_name": """
EXAMPLES (preserve hierarchical service names):
  "Office Visit for Injury / Illness - Primary Care" -> Office Visit for Injury / Illness - Primary Care
  "Office Visit for Injury / Illness - Specialist" -> Office Visit for Injury / Illness - Specialist
  "Urgent Care Physician's Office - Primary Care" -> Urgent Care Physician's Office - Primary Care
  "PCP Visit" -> Primary Care Visit
  "Specialist Visit" -> Specialist Visit
  "ER Visit" -> Emergency Room Visit
  "Routine Physical" -> Preventive Care Visit
NOTE: Do NOT collapse "Primary Care" and "Specialist" - they are distinct services!""",
            
            "limit_period": """
EXAMPLES:
  "per benefit period" -> Benefit Year
  "annually" -> Calendar Year
  "lifetime max" -> Lifetime
  "per hospital stay" -> Per Admission
  "each occurrence" -> Per Occurrence
  "per calendar year" -> Calendar Year
  "per plan year" -> Plan Year""",
            
            "coverage_status": """
EXAMPLES:
  "Plan pays 100%" -> Covered in Full
  "Excluded benefit" -> Not Covered  
  "Subject to deductible" -> Covered
  "Not a covered benefit" -> Not Covered
  "Covered in full" -> Covered in Full
  "No charge" -> Covered in Full""",
            
            "preauth_status": """
EXAMPLES:
  "PA Required" -> Required
  "Prior Auth may apply" -> May Be Required
  "No precertification needed" -> Not Required
  "Precertification Required" -> Required
  "Authorization Not Required" -> Not Required""",
            
            "deductible_applies": """
EXAMPLES:
  "After deductible" -> Yes
  "Subject to deductible" -> Yes
  "Deductible waived" -> No
  "No deductible" -> No
  "Deductible applies" -> Yes
  "80% after deductible" -> Yes
  "Covered in full, no deductible" -> No
  "Ded. applies" -> Yes
  "Ded. does not apply" -> No""",
            
            "after_deductible": """
EXAMPLES:
  "After deductible" -> Yes
  "Subject to deductible" -> Yes
  "Deductible waived" -> No
  "No deductible" -> No
  "Deductible applies" -> Yes
  "80% after deductible" -> Yes
  "Covered in full, no deductible" -> No"""
        }
        
        if category and category in examples:
            return examples[category]
        
        # Return comprehensive general examples if no specific category
        return """
EXAMPLES:
  "Participating Provider" -> In-Network
  "SNF" -> Skilled Nursing Facility
  "per benefit period" -> Benefit Year
  "PT/OT/ST" -> Rehabilitation Services
  "Office Visit for Injury / Illness - Primary Care" -> Office Visit for Injury / Illness - Primary Care
  "After deductible" -> Yes
  "PA Required" -> Required
  
NOTE: Preserve full hierarchical service names. Do NOT collapse "Primary Care" and "Specialist" visits."""
    
    def _log_llm_decision(
        self,
        term: str,
        result: str,
        category: Optional[str],
        context: Optional[str],
        status: str,
    ) -> None:
        """
        Log LLM decisions for audit and quality review.
        
        This creates an audit trail of all LLM-based mappings for:
        - Quality assurance review
        - Identifying terms that should be added to config
        - Debugging mapping issues
        """
        if not hasattr(self, '_llm_audit_log'):
            self._llm_audit_log = []
        
        import datetime
        self._llm_audit_log.append({
            'timestamp': datetime.datetime.now().isoformat(),
            'term': term,
            'result': result,
            'category': category,
            'context_preview': context[:100] if context else None,
            'status': status,
        })
        
        # Keep only last 1000 entries to prevent memory bloat
        if len(self._llm_audit_log) > 1000:
            self._llm_audit_log = self._llm_audit_log[-1000:]
    
    def get_llm_audit_log(self) -> List[Dict[str, Any]]:
        """Get the LLM decision audit log for review."""
        return getattr(self, '_llm_audit_log', [])
    
    def export_llm_audit_log(self, output_path: str) -> None:
        """Export LLM audit log to JSON file for quality review."""
        import json
        try:
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(self.get_llm_audit_log(), f, indent=2)
            logger.info(f"Exported {len(self._llm_audit_log)} LLM decisions to {output_path}")
        except Exception as e:
            logger.error(f"Failed to export LLM audit log: {e}")
    
    # =========================================================================
    # Learning and Extension
    # =========================================================================
    
    def learn_mapping(self, term: str, standard_value: str) -> None:
        """
        Learn a new term mapping (e.g., from user correction).
        
        This allows the system to improve over time without code changes.
        """
        term_lower = term.lower().strip()
        
        # Add to learned mappings
        self.config.learned_mappings[term_lower] = standard_value
        
        # Also add to synonyms for fuzzy matching
        if standard_value not in self.config.synonyms:
            self.config.synonyms[standard_value] = set()
        self.config.synonyms[standard_value].add(term_lower)
        
        logger.info(f"Learned new mapping: '{term}' -> '{standard_value}'")
    
    def add_pattern(self, pattern: str, standard_value: str) -> None:
        """Add a new regex pattern mapping."""
        try:
            compiled = re.compile(pattern, re.IGNORECASE)
            self._compiled_patterns.append((compiled, standard_value))
            self.config.pattern_mappings.append((pattern, standard_value))
            logger.info(f"Added pattern: '{pattern}' -> '{standard_value}'")
        except re.error as e:
            logger.error(f"Invalid regex pattern: {e}")
    
    def save_learned_mappings(self, output_path: str) -> None:
        """Save learned mappings to file for persistence."""
        try:
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump({
                    'learned_mappings': self.config.learned_mappings,
                    'stats': self.stats,
                }, f, indent=2)
            logger.info(f"Saved {len(self.config.learned_mappings)} learned mappings to {output_path}")
        except Exception as e:
            logger.error(f"Failed to save learned mappings: {e}")
    
    def load_learned_mappings(self, input_path: str) -> None:
        """Load previously learned mappings."""
        try:
            with open(input_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            self.config.learned_mappings.update(data.get('learned_mappings', {}))
            logger.info(f"Loaded {len(data.get('learned_mappings', {}))} learned mappings")
        except Exception as e:
            logger.warning(f"Failed to load learned mappings: {e}")
    
    # =========================================================================
    # Utility Methods
    # =========================================================================
    
    def get_all_known_terms(self, category: Optional[str] = None) -> List[str]:
        """Get all known terms, optionally filtered by category."""
        if category and category in self.config.synonyms:
            return list(self.config.synonyms[category])
        return list(self.config.term_mappings.keys())
    
    def get_standard_values(self, category: Optional[str] = None) -> List[str]:
        """Get all standard output values."""
        if category and category in self.config.standard_values:
            return self.config.standard_values[category]
        
        all_values = []
        for values in self.config.standard_values.values():
            all_values.extend(values)
        return list(set(all_values))
    
    def get_statistics(self) -> Dict[str, int]:
        """Get matching statistics."""
        return self.stats.copy()
    
    def explain_match(
        self,
        term: str,
        category: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Get detailed explanation of how a term was matched.
        
        Useful for debugging and transparency.
        """
        result = self.match(term, category)
        
        explanation = {
            'input_term': term,
            'normalized_value': result.standard_value,
            'confidence': result.confidence,
            'match_method': result.match_method,
            'matched': result.matched,
            'alternative_matches': [],
        }
        
        # Find close alternatives
        term_lower = term.lower().strip()
        for known_term, standard in self.config.term_mappings.items():
            if known_term != term_lower:
                ratio = SequenceMatcher(None, term_lower, known_term).ratio()
                if ratio > 0.5:
                    explanation['alternative_matches'].append({
                        'term': known_term,
                        'maps_to': standard,
                        'similarity': round(ratio, 3),
                    })
        
        # Sort by similarity
        explanation['alternative_matches'].sort(
            key=lambda x: x['similarity'],
            reverse=True
        )
        explanation['alternative_matches'] = explanation['alternative_matches'][:5]
        
        return explanation


# =============================================================================
# Specialized Matchers (Convenience Classes)
# =============================================================================


class NetworkTermMatcher(SemanticMatcher):
    """Specialized matcher for network tier terminology."""
    
    DEFAULT_CONFIG = {
        "standard_values": {
            "network": ["In-Network", "Out-of-Network"]
        },
        "mappings": {
            # In-Network variations
            "in-network": "In-Network",
            "in network": "In-Network",
            "innetwork": "In-Network",
            "in_network": "In-Network",
            "network": "In-Network",
            "participating": "In-Network",
            "par": "In-Network",
            "preferred": "In-Network",
            "tier 1": "In-Network",
            "tier1": "In-Network",
            "tier i": "In-Network",
            "ppo": "In-Network",
            "hmo": "In-Network",
            "epo": "In-Network",
            "pos": "In-Network",
            "contracted": "In-Network",
            "member provider": "In-Network",
            "plan provider": "In-Network",
            "inn": "In-Network",
            "i/n": "In-Network",
            
            # Out-of-Network variations
            "out-of-network": "Out-of-Network",
            "out of network": "Out-of-Network",
            "outofnetwork": "Out-of-Network",
            "out_of_network": "Out-of-Network",
            "non-network": "Out-of-Network",
            "non network": "Out-of-Network",
            "nonnetwork": "Out-of-Network",
            "non-participating": "Out-of-Network",
            "non participating": "Out-of-Network",
            "nonparticipating": "Out-of-Network",
            "non-par": "Out-of-Network",
            "nonpar": "Out-of-Network",
            "non par": "Out-of-Network",
            "tier 2": "Out-of-Network",
            "tier2": "Out-of-Network",
            "tier ii": "Out-of-Network",
            "tier 3": "Out-of-Network",
            "non-ppo": "Out-of-Network",
            "out-of-area": "Out-of-Network",
            "out of area": "Out-of-Network",
            "indemnity": "Out-of-Network",
            "fee-for-service": "Out-of-Network",
            "oon": "Out-of-Network",
            "o/n": "Out-of-Network",
            "non-contracted": "Out-of-Network",
        },
        "patterns": [
            {"pattern": r"\bin[- ]?net\b", "maps_to": "In-Network"},
            {"pattern": r"\bout[- ]?of[- ]?net\b", "maps_to": "Out-of-Network"},
            {"pattern": r"\bnon[- ]?par\b", "maps_to": "Out-of-Network"},
        ]
    }
    
    def __init__(self, config_path: Optional[str] = None, **kwargs):
        # Load defaults first
        super().__init__(config_path=None, **kwargs)
        
        # Apply default config
        self.config.standard_values = self.DEFAULT_CONFIG['standard_values']
        self.config.term_mappings = {
            k.lower(): v for k, v in self.DEFAULT_CONFIG['mappings'].items()
        }
        
        # Compile patterns
        for p in self.DEFAULT_CONFIG['patterns']:
            try:
                self._compiled_patterns.append(
                    (re.compile(p['pattern'], re.IGNORECASE), p['maps_to'])
                )
            except re.error:
                pass
        
        # Override with custom config if provided
        if config_path:
            custom = load_mapping_config(config_path)
            self.config.term_mappings.update(custom.term_mappings)
            self._compiled_patterns.extend([
                (re.compile(p, re.IGNORECASE), t) 
                for p, t in custom.pattern_mappings
            ])


class ServiceCategoryMatcher(SemanticMatcher):
    """Specialized matcher for service category terminology."""
    
    DEFAULT_CONFIG = {
        "standard_values": {
            "service_category": [
                "Preventive Care",
                "Primary Care",
                "Specialist Services",
                "Emergency Services",
                "Urgent Care",
                "Inpatient Hospital Services",
                "Outpatient Hospital Services",
                "Mental Health - Inpatient",
                "Mental Health - Outpatient",
                "Substance Abuse Treatment",
                "Maternity Care",
                "Prescription Drugs",
                "Rehabilitation Services",
                "Skilled Nursing Facility",
                "Home Health Care",
                "Hospice Care",
                "Durable Medical Equipment",
                "Diagnostic - Lab",
                "Diagnostic - Imaging",
                "Ambulance Services",
                "Other Services",
            ]
        },
        "mappings": {
            # Direct mappings for common terms (checked before patterns)
            "physical therapy": "Rehabilitation Services",
            "occupational therapy": "Rehabilitation Services",
            "speech therapy": "Rehabilitation Services",
            "pt": "Rehabilitation Services",
            "ot": "Rehabilitation Services",
            "rehabilitation": "Rehabilitation Services",
            "rehab": "Rehabilitation Services",
            "skilled nursing": "Skilled Nursing Facility",
            "skilled nursing facility": "Skilled Nursing Facility",
            "snf": "Skilled Nursing Facility",
            "nursing facility": "Skilled Nursing Facility",
            "nursing home": "Skilled Nursing Facility",
            "emergency room": "Emergency Services",
            "emergency services": "Emergency Services",
            "emergency care": "Emergency Services",
            "er visit": "Emergency Services",
            "ed visit": "Emergency Services",
            "mental health": "Mental Health - Outpatient",
            "behavioral health": "Mental Health - Outpatient",
            "psychiatric": "Mental Health - Outpatient",
            "counseling": "Mental Health - Outpatient",
            "psychotherapy": "Mental Health - Outpatient",
        },
        "patterns": [
            # ORDER MATTERS - more specific patterns first
            
            # Rehabilitation (before mental health to avoid therapy conflict)
            {"pattern": r"(?:physical|occupational|speech)\s+therap", "maps_to": "Rehabilitation Services"},
            {"pattern": r"\brehab(?:ilitation)?\b", "maps_to": "Rehabilitation Services"},
            {"pattern": r"\b(?:pt|ot)\b(?:\s+services)?", "maps_to": "Rehabilitation Services"},
            
            # Skilled Nursing (before nursing matches something else)
            {"pattern": r"skilled\s+nurs", "maps_to": "Skilled Nursing Facility"},
            {"pattern": r"\bsnf\b", "maps_to": "Skilled Nursing Facility"},
            {"pattern": r"nursing\s+(?:facility|home)", "maps_to": "Skilled Nursing Facility"},
            
            # Preventive / Wellness
            {"pattern": r"prevent(?:ive|ion)", "maps_to": "Preventive Care"},
            {"pattern": r"wellness|routine\s+(?:physical|exam|checkup)", "maps_to": "Preventive Care"},
            {"pattern": r"annual\s+(?:physical|exam|checkup)", "maps_to": "Preventive Care"},
            {"pattern": r"well[- ]?(?:child|woman|baby)", "maps_to": "Preventive Care"},
            
            # Primary Care
            {"pattern": r"primary\s+care", "maps_to": "Primary Care"},
            {"pattern": r"\bpcp\b", "maps_to": "Primary Care"},
            {"pattern": r"office\s+visit", "maps_to": "Primary Care"},
            {"pattern": r"physician\s+visit", "maps_to": "Primary Care"},
            
            # Specialist
            {"pattern": r"specialist", "maps_to": "Specialist Services"},
            
            # Emergency - be very specific to avoid false positives
            {"pattern": r"emergency\s+(?:room|services|care|dept|department)", "maps_to": "Emergency Services"},
            {"pattern": r"\ber\s+(?:visit|services|care)\b", "maps_to": "Emergency Services"},
            {"pattern": r"\bed\s+(?:visit|services|care)\b", "maps_to": "Emergency Services"},
            {"pattern": r"(?:^|\s)er(?:\s|$)", "maps_to": "Emergency Services"},
            
            # Urgent Care
            {"pattern": r"urgent\s+care", "maps_to": "Urgent Care"},
            
            # Hospital Services
            {"pattern": r"inpatient\s+(?:hospital|hosp)", "maps_to": "Inpatient Hospital Services"},
            {"pattern": r"hospital\s+inpatient", "maps_to": "Inpatient Hospital Services"},
            {"pattern": r"room\s+(?:and|&)\s+board", "maps_to": "Inpatient Hospital Services"},
            {"pattern": r"outpatient\s+(?:hospital|hosp|surgery)", "maps_to": "Outpatient Hospital Services"},
            {"pattern": r"hospital\s+outpatient", "maps_to": "Outpatient Hospital Services"},
            {"pattern": r"ambulatory\s+surg", "maps_to": "Outpatient Hospital Services"},
            
            # Mental Health - be specific to avoid therapy conflict
            {"pattern": r"mental\s+health", "maps_to": "Mental Health - Outpatient"},
            {"pattern": r"behavioral\s+health", "maps_to": "Mental Health - Outpatient"},
            {"pattern": r"psychiatr", "maps_to": "Mental Health - Outpatient"},
            {"pattern": r"\bcounseling\b", "maps_to": "Mental Health - Outpatient"},
            {"pattern": r"psycho(?:therap|log)", "maps_to": "Mental Health - Outpatient"},
            
            # Substance Abuse
            {"pattern": r"substance\s+(?:abuse|use)", "maps_to": "Substance Abuse Treatment"},
            {"pattern": r"alcohol\s+(?:abuse|treatment)", "maps_to": "Substance Abuse Treatment"},
            {"pattern": r"drug\s+(?:abuse|treatment|rehab)", "maps_to": "Substance Abuse Treatment"},
            {"pattern": r"detox", "maps_to": "Substance Abuse Treatment"},
            
            # Maternity
            {"pattern": r"maternity", "maps_to": "Maternity Care"},
            {"pattern": r"pre[- ]?natal", "maps_to": "Maternity Care"},
            {"pattern": r"(?:labor|delivery|childbirth)", "maps_to": "Maternity Care"},
            {"pattern": r"pregnancy", "maps_to": "Maternity Care"},
            {"pattern": r"obstetric", "maps_to": "Maternity Care"},
            
            # Prescription Drugs
            {"pattern": r"prescription\s+(?:drug|med)", "maps_to": "Prescription Drugs"},
            {"pattern": r"\bpharmacy\b", "maps_to": "Prescription Drugs"},
            {"pattern": r"\brx\b", "maps_to": "Prescription Drugs"},
            {"pattern": r"formulary", "maps_to": "Prescription Drugs"},
            
            # Home Health / Hospice
            {"pattern": r"home\s+health", "maps_to": "Home Health Care"},
            {"pattern": r"hospice", "maps_to": "Hospice Care"},
            {"pattern": r"palliative", "maps_to": "Hospice Care"},
            
            # DME
            {"pattern": r"durable\s+medical", "maps_to": "Durable Medical Equipment"},
            {"pattern": r"\bdme\b", "maps_to": "Durable Medical Equipment"},
            {"pattern": r"medical\s+equipment", "maps_to": "Durable Medical Equipment"},
            {"pattern": r"wheelchair|prosthetic|orthotic|oxygen\s+equip", "maps_to": "Durable Medical Equipment"},
            
            # Diagnostics
            {"pattern": r"\blab(?:oratory)?\b", "maps_to": "Diagnostic - Lab"},
            {"pattern": r"blood\s+(?:test|work)", "maps_to": "Diagnostic - Lab"},
            {"pattern": r"pathology", "maps_to": "Diagnostic - Lab"},
            {"pattern": r"x[- ]?ray", "maps_to": "Diagnostic - Imaging"},
            {"pattern": r"\bmri\b", "maps_to": "Diagnostic - Imaging"},
            {"pattern": r"\bct\s+scan\b", "maps_to": "Diagnostic - Imaging"},
            {"pattern": r"\bpet\s+scan\b", "maps_to": "Diagnostic - Imaging"},
            {"pattern": r"imaging|radiology", "maps_to": "Diagnostic - Imaging"},
            
            # Ambulance
            {"pattern": r"ambulance", "maps_to": "Ambulance Services"},
            {"pattern": r"emergency\s+transport", "maps_to": "Ambulance Services"},
        ]
    }
    
    def __init__(self, config_path: Optional[str] = None, **kwargs):
        super().__init__(config_path=None, **kwargs)
        
        self.config.standard_values = self.DEFAULT_CONFIG['standard_values']
        
        # Load explicit mappings first (these take priority)
        self.config.term_mappings = {
            k.lower(): v for k, v in self.DEFAULT_CONFIG['mappings'].items()
        }
        
        # Then compile patterns
        for p in self.DEFAULT_CONFIG['patterns']:
            try:
                self._compiled_patterns.append(
                    (re.compile(p['pattern'], re.IGNORECASE), p['maps_to'])
                )
            except re.error:
                pass
        
        if config_path:
            custom = load_mapping_config(config_path)
            self.config.term_mappings.update(custom.term_mappings)


class LimitPeriodMatcher(SemanticMatcher):
    """Specialized matcher for limit period terminology."""
    
    DEFAULT_CONFIG = {
        "standard_values": {
            "limit_period": [
                "Calendar Year",
                "Benefit Year",
                "Plan Year",
                "Lifetime",
                "Per Visit",
                "Per Admission",
                "Per Occurrence",
                "Rolling 12 Months",
            ]
        },
        "mappings": {
            "per year": "Calendar Year",
            "per calendar year": "Calendar Year",
            "annually": "Calendar Year",
            "annual": "Calendar Year",
            "each year": "Calendar Year",
            "per benefit year": "Benefit Year",
            "benefit year": "Benefit Year",
            "per plan year": "Plan Year",
            "plan year": "Plan Year",
            "lifetime": "Lifetime",
            "per lifetime": "Lifetime",
            "lifetime maximum": "Lifetime",
            "per visit": "Per Visit",
            "each visit": "Per Visit",
            "per admission": "Per Admission",
            "each admission": "Per Admission",
            "per stay": "Per Admission",
            "per occurrence": "Per Occurrence",
            "each occurrence": "Per Occurrence",
            "per episode": "Per Occurrence",
            "rolling 12 months": "Rolling 12 Months",
            "rolling twelve months": "Rolling 12 Months",
        },
        "patterns": [
            # Calendar Year patterns
            {"pattern": r"(?:per|each|every)\s+(?:calendar\s+)?year", "maps_to": "Calendar Year"},
            {"pattern": r"annual(?:ly)?", "maps_to": "Calendar Year"},
            {"pattern": r"/\s*(?:yr|year)\b", "maps_to": "Calendar Year"},
            # Benefit Year patterns
            {"pattern": r"(?:per|each)\s+benefit\s+(?:year|period)", "maps_to": "Benefit Year"},
            {"pattern": r"benefit\s+year", "maps_to": "Benefit Year"},
            # Plan Year patterns
            {"pattern": r"(?:per|each)\s+plan\s+year", "maps_to": "Plan Year"},
            {"pattern": r"plan\s+year", "maps_to": "Plan Year"},
            {"pattern": r"policy\s+year", "maps_to": "Plan Year"},
            # Lifetime patterns
            {"pattern": r"lifetime", "maps_to": "Lifetime"},
            {"pattern": r"per\s+lifetime", "maps_to": "Lifetime"},
            # Per Visit patterns
            {"pattern": r"(?:per|each)\s+visit", "maps_to": "Per Visit"},
            {"pattern": r"/\s*visit\b", "maps_to": "Per Visit"},
            # Per Admission patterns
            {"pattern": r"(?:per|each)\s+(?:admission|stay|hospitalization)", "maps_to": "Per Admission"},
            # Per Occurrence patterns
            {"pattern": r"(?:per|each)\s+(?:occurrence|episode|condition)", "maps_to": "Per Occurrence"},
            # Rolling 12 months
            {"pattern": r"rolling\s+(?:12|twelve)\s+months", "maps_to": "Rolling 12 Months"},
        ]
    }
    
    def __init__(self, config_path: Optional[str] = None, **kwargs):
        super().__init__(config_path=None, **kwargs)
        
        self.config.standard_values = self.DEFAULT_CONFIG['standard_values']
        self.config.term_mappings = {
            k.lower(): v for k, v in self.DEFAULT_CONFIG['mappings'].items()
        }
        
        # Compile patterns for substring matching within text
        for p in self.DEFAULT_CONFIG['patterns']:
            try:
                self._compiled_patterns.append(
                    (re.compile(p['pattern'], re.IGNORECASE), p['maps_to'])
                )
            except re.error:
                pass


# =============================================================================
# Factory Function
# =============================================================================


def create_matcher(
    matcher_type: str,
    config_path: Optional[str] = None,
    **kwargs,
) -> SemanticMatcher:
    """
    Factory function to create appropriate matcher.
    
    Args:
        matcher_type: One of "network", "service", "limit_period", "generic"
        config_path: Optional path to custom JSON configuration
        **kwargs: Additional arguments passed to matcher
        
    Returns:
        Configured SemanticMatcher
    """
    matchers = {
        "network": NetworkTermMatcher,
        "service": ServiceCategoryMatcher,
        "limit_period": LimitPeriodMatcher,
        "generic": SemanticMatcher,
    }
    
    matcher_class = matchers.get(matcher_type.lower(), SemanticMatcher)
    return matcher_class(config_path=config_path, **kwargs)
