"""
Schema-Bound Record Builder for SPD Benefits Extraction.

Converts extracted table rows into validated BenefitRecord objects
using explicit field mappings and robust parsing.

Design Principles:
- Explicit mapping: Each field has a defined source and transformation
- Validation-first: All values validated before assignment
- Extensible: Easy to add new fields or modify mappings
- Traceable: Every transformation is logged for debugging
"""

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple, Callable

from src.models.benefit_record import BenefitRecord, RawExtractionRecord
from src.parsers.table_extractor import ExtractedRow, ColumnRole

logger = logging.getLogger(__name__)


@dataclass
class FieldMapping:
    """Defines how to map an extracted value to a BenefitRecord field."""
    target_field: str
    source_role: Optional[ColumnRole] = None
    source_attribute: Optional[str] = None
    transformer: Optional[Callable[[str], Any]] = None
    validator: Optional[Callable[[Any], bool]] = None
    default_value: Any = None
    required: bool = False


@dataclass
class ParsedValue:
    """Result of parsing a raw value string."""
    coinsurance: Optional[str] = None
    copay: Optional[str] = None
    after_deductible: bool = False
    not_covered: bool = False
    no_charge: bool = False
    raw_text: str = ""
    confidence: float = 0.8
    notes: List[str] = field(default_factory=list)


class ValueParser:
    """
    Parses raw benefit value strings into structured components.
    
    Handles ALL common healthcare benefit formats including:
    - Percentages: "80%", "80% coinsurance", "You pay 20%", "Plan pays 80%"
    - Copays: "$50 copay", "$50/visit", "50 dollars per visit"
    - Combined: "80% after deductible", "$50 copay + 20% coinsurance"
    - Zero cost: "No charge", "Covered in full", "$0", "No cost sharing"
    - Not covered: "Not covered", "Excluded", "N/A", "Does not apply"
    - Deductible: "After deductible", "Subject to deductible", "Ded waived"
    - Limits: "20 visits/year", "60 days maximum", "$5000 per occurrence"
    """
    
    # ==========================================================================
    # COINSURANCE PATTERNS - Handle all percentage variations
    # ==========================================================================
    COINSURANCE_PATTERNS = [
        # Standard: "80%", "80 %", "80% coinsurance"
        re.compile(r"(\d{1,3})\s*%\s*(?:coinsurance|coins?\.|co-?ins)?(?:\s|$|;|,)", re.I),
        # With context: "plan pays 80%", "covered at 80%"
        re.compile(r"(?:plan|we)\s+pays?\s+(\d{1,3})\s*%", re.I),
        re.compile(r"covered\s+(?:at\s+)?(\d{1,3})\s*%", re.I),
        # You pay: "you pay 20%", "member pays 20%"
        re.compile(r"(?:you|member|patient)\s+pays?\s+(\d{1,3})\s*%", re.I),
        # Percentage of: "80% of allowed", "80% of R&C"
        re.compile(r"(\d{1,3})\s*%\s+(?:of\s+)?(?:allowed|r\s*&\s*c|usual|reasonable|customary|eligible|covered)", re.I),
    ]
    
    # Legacy single pattern for backward compatibility
    COINSURANCE_PATTERN = re.compile(
        r"(\d{1,3})\s*%\s*(?:coinsurance|coins?\.?)?",
        re.IGNORECASE
    )
    
    # ==========================================================================
    # COPAY PATTERNS - Handle all dollar amount variations
    # ==========================================================================
    COPAY_PATTERNS = [
        # Standard: "$50", "$50.00", "$5,000"
        re.compile(r"\$\s*([\d,]+(?:\.\d{2})?)", re.I),
        # With label: "$50 copay", "$50 co-pay", "$50 copayment"
        re.compile(r"\$\s*([\d,]+(?:\.\d{2})?)\s*(?:copay(?:ment)?|co-?pay)", re.I),
        # Label first: "copay $50", "copay: $50"
        re.compile(r"(?:copay(?:ment)?|co-?pay)[:\s]+\$\s*([\d,]+(?:\.\d{2})?)", re.I),
        # Per unit: "$50/visit", "$50 per visit"
        re.compile(r"\$\s*([\d,]+(?:\.\d{2})?)\s*(?:/|per\s+)(?:visit|day|admission)", re.I),
        # Written out: "50 dollars", "fifty dollars"
        re.compile(r"(\d{1,5})\s+dollars?", re.I),
    ]
    
    # Legacy single pattern
    COPAY_PATTERN = re.compile(
        r"\$\s*([\d,]+(?:\.\d{2})?)",
        re.IGNORECASE
    )
    
    # ==========================================================================
    # NO CHARGE / COVERED IN FULL PATTERNS
    # ==========================================================================
    NO_CHARGE_PATTERNS = [
        re.compile(r"no\s+charge", re.I),
        re.compile(r"covered\s+in\s+full", re.I),
        re.compile(r"paid\s+in\s+full", re.I),
        re.compile(r"no\s+cost(?:\s+sharing)?", re.I),
        re.compile(r"100\s*%\s*(?:covered|coverage|paid)", re.I),
        re.compile(r"plan\s+pays\s+100\s*%", re.I),
        re.compile(r"(?:^|\s)\$\s*0(?:\.00)?\s*(?:copay)?(?:\s|$)", re.I),
        re.compile(r"(?:^|\s)0\s*%\s*(?:coinsurance)?(?:\s|$)", re.I),
        re.compile(r"free(?:\s|$)", re.I),
        re.compile(r"at\s+no\s+(?:additional\s+)?(?:charge|cost)", re.I),
        re.compile(r"no\s+(?:copay|co-?pay|coinsurance|deductible)\s+(?:required|applies)", re.I),
        re.compile(r"waived", re.I),
    ]
    
    # Legacy single pattern
    NO_CHARGE_PATTERN = re.compile(
        r"(?:no\s+charge|covered\s+in\s+full|paid\s+in\s+full|"
        r"(?:^\s*|\s)\$?\s*0(?:\.00)?\s*(?:copay)?\s*$|"
        r"(?:^|\s)100\s*%\s*(?:covered|coverage))",
        re.IGNORECASE
    )
    
    # ==========================================================================
    # NOT COVERED PATTERNS - All exclusion variations
    # ==========================================================================
    NOT_COVERED_PATTERNS = [
        re.compile(r"not\s+(?:a\s+)?covered(?:\s+benefit)?", re.I),
        re.compile(r"no\s+(?:coverage|benefit)", re.I),
        re.compile(r"excluded", re.I),
        re.compile(r"(?:^|[\s,;])n/?a(?:[\s,;]|$)", re.I),
        re.compile(r"not\s+applicable", re.I),
        re.compile(r"does\s+not\s+(?:apply|cover)", re.I),
        re.compile(r"benefit\s+not\s+(?:available|provided)", re.I),
        re.compile(r"(?:you|member)\s+pays?\s+100\s*%", re.I),
        re.compile(r"not\s+(?:eligible|included)", re.I),
        re.compile(r"(?:^|\s)none(?:\s|$)", re.I),
        # Use word boundary to avoid matching "0" in "100%"
        re.compile(r"(?<!\d)0\s*%\s+(?:coverage|covered)", re.I),
        re.compile(r"coverage\s+(?:is\s+)?not\s+(?:available|provided)", re.I),
        re.compile(r"see\s+exclusions?", re.I),
    ]
    
    # Legacy single pattern
    NOT_COVERED_PATTERN = re.compile(
        r"(?:not\s+covered|no\s+(?:coverage|benefit)|excluded|"
        r"(?:^|\s)n/?a(?:\s|$)|does\s+not\s+apply|not\s+applicable)",
        re.IGNORECASE
    )
    
    # ==========================================================================
    # DEDUCTIBLE PATTERNS
    # ==========================================================================
    AFTER_DEDUCTIBLE_PATTERNS = [
        re.compile(r"after\s+(?:(?:the|your|annual|plan)\s+)?deductible", re.I),
        re.compile(r"subject\s+to\s+(?:(?:the|your|annual|plan)\s+)?deductible", re.I),
        re.compile(r"deductible\s+applies", re.I),
        re.compile(r"(?:once|after)\s+(?:you|member)\s+meets?\s+(?:the\s+)?deductible", re.I),
        re.compile(r"after\s+(?:you\s+)?(?:meet|reach|satisfy)\s+(?:the\s+)?deductible", re.I),
        re.compile(r"\+\s*ded(?:uctible)?", re.I),
        re.compile(r"ded(?:uctible)?\s+then", re.I),
    ]
    
    # Legacy single pattern
    AFTER_DEDUCTIBLE_PATTERN = re.compile(
        r"(?:after|subject\s+to)\s+(?:the\s+)?(?:plan\s+)?(?:annual\s+)?deductible",
        re.IGNORECASE
    )
    
    DEDUCTIBLE_WAIVED_PATTERNS = [
        re.compile(r"deductible\s+(?:does\s+not|doesn't)\s+apply", re.I),
        re.compile(r"no\s+deductible", re.I),
        re.compile(r"deductible\s+(?:is\s+)?waived", re.I),
        re.compile(r"ded(?:uctible)?\.?\s+(?:n/?a|waived)", re.I),
        re.compile(r"not\s+subject\s+to\s+deductible", re.I),
        re.compile(r"exempt\s+from\s+deductible", re.I),
        re.compile(r"before\s+(?:the\s+)?deductible", re.I),
        re.compile(r"without\s+(?:meeting\s+)?deductible", re.I),
        re.compile(r"deductible\s+(?:is\s+)?not\s+required", re.I),
    ]
    
    # Legacy single pattern
    DEDUCTIBLE_WAIVED_PATTERN = re.compile(
        r"(?:deductible\s+(?:does\s+not|doesn't)\s+apply|no\s+deductible|deductible\s+waived|ded\.?\s+n/?a)",
        re.IGNORECASE
    )
    
    # ==========================================================================
    # LIMIT PATTERNS
    # ==========================================================================
    LIMIT_PATTERNS = [
        re.compile(r"(\d+)\s*(?:visits?|days?|times?)\s*(?:per|/|each)?\s*(year|benefit\s+period|calendar\s+year|lifetime)?", re.I),
        re.compile(r"(?:up\s+to|max(?:imum)?(?:\s+of)?|limit(?:ed)?\s+to)\s*(\d+)\s*(visits?|days?|treatments?|sessions?)", re.I),
        re.compile(r"(\d+)\s*(visit|day|treatment|session)\s+(?:limit|max(?:imum)?)", re.I),
    ]
    
    # Per-unit pattern
    PER_UNIT_PATTERNS = [
        re.compile(r"(?:per|each|/)\s*(visit|day|admission|occurrence|stay|treatment|session|night|procedure)", re.I),
        re.compile(r"(visit|day|admission|occurrence|stay|treatment|session)[\s-]+(?:copay|charge)", re.I),
    ]
    
    # Legacy single pattern
    PER_UNIT_PATTERN = re.compile(
        r"(?:per|each|/)\s*(visit|day|admission|occurrence|stay|treatment|session)",
        re.IGNORECASE
    )
    
    # ==========================================================================
    # PREAUTHORIZATION PATTERNS
    # ==========================================================================
    PREAUTH_REQUIRED_PATTERNS = [
        re.compile(r"(?:pre[- ]?)?(?:auth(?:orization)?|cert(?:ification)?)\s+(?:is\s+)?required", re.I),
        re.compile(r"prior\s+(?:auth(?:orization)?|approval)\s+(?:is\s+)?required", re.I),
        re.compile(r"requires?\s+(?:pre[- ]?)?(?:auth|approval|pa)", re.I),
        re.compile(r"must\s+(?:be\s+)?(?:pre[- ]?)?(?:approved|authorized|certified)", re.I),
        re.compile(r"\bpa\s+req(?:uired)?", re.I),
        re.compile(r"\*\s*$", re.I),  # Often * indicates preauth
    ]
    
    PREAUTH_NOT_REQUIRED_PATTERNS = [
        re.compile(r"(?:no|not)\s+(?:pre[- ]?)?(?:auth|cert)\s+(?:required|needed)", re.I),
        re.compile(r"pre[- ]?(?:auth|cert)\s+(?:is\s+)?not\s+required", re.I),
        re.compile(r"no\s+(?:approval|pa)\s+(?:needed|required)", re.I),
    ]
    
    @classmethod
    def _match_any(cls, patterns: List[re.Pattern], text: str) -> Optional[re.Match]:
        """Try to match any pattern from a list, return first match."""
        for pattern in patterns:
            match = pattern.search(text)
            if match:
                return match
        return None
    
    @classmethod
    def _matches_any(cls, patterns: List[re.Pattern], text: str) -> bool:
        """Check if text matches any pattern from a list."""
        return any(p.search(text) for p in patterns)
    
    @classmethod
    def _normalize_text(cls, text: str) -> str:
        """Normalize text for better pattern matching."""
        if not text:
            return ""
        # Normalize whitespace
        text = re.sub(r'\s+', ' ', text.strip())
        # Normalize common OCR issues (curly quotes, dashes)
        text = text.replace('\u2013', '-').replace('\u2014', '-')  # en-dash, em-dash
        text = text.replace('\u2019', "'").replace('\u201c', '"').replace('\u201d', '"')  # curly quotes
        # Fix common OCR mistakes
        text = re.sub(r'(?<!\d)O(?=\d)', '0', text)  # O -> 0 when followed by digit
        text = re.sub(r'(?<=\d)O(?!\d)', '0', text)  # O -> 0 when preceded by digit
        return text
    
    @classmethod
    def parse(cls, raw_value: Optional[str]) -> ParsedValue:
        """
        Parse a raw value string into structured components.
        
        Uses comprehensive pattern matching to handle all variations:
        - Percentages with various labels and positions
        - Dollar amounts with copay/per-unit context
        - Coverage status (not covered, covered in full, waived)
        - Deductible applicability
        - Limits and preauthorization
        
        Args:
            raw_value: Raw text like "80% after deductible" or "$50 copay"
            
        Returns:
            ParsedValue with extracted components
        """
        result = ParsedValue(raw_text=raw_value or "")
        
        if not raw_value:
            result.confidence = 0.5
            return result
        
        # Normalize text for better matching
        raw_value = cls._normalize_text(raw_value)
        raw_lower = raw_value.lower()
        
        # ======================================================================
        # STEP 1: Check for NOT COVERED (takes precedence over everything)
        # ======================================================================
        if cls._matches_any(cls.NOT_COVERED_PATTERNS, raw_value):
            result.not_covered = True
            result.coinsurance = "Not Covered"
            result.confidence = 0.95
            return result
        
        # ======================================================================
        # STEP 2: Check for NO CHARGE / COVERED IN FULL
        # ======================================================================
        if cls._matches_any(cls.NO_CHARGE_PATTERNS, raw_value):
            result.no_charge = True
            result.coinsurance = "0%"
            result.copay = "$0"
            result.confidence = 0.95
            return result
        
        # ======================================================================
        # STEP 3: Extract COINSURANCE percentage
        # ======================================================================
        coinsurance_match = cls._match_any(cls.COINSURANCE_PATTERNS, raw_value)
        if not coinsurance_match:
            # Fall back to legacy single pattern
            coinsurance_match = cls.COINSURANCE_PATTERN.search(raw_value)
        
        if coinsurance_match:
            pct = int(coinsurance_match.group(1))
            
            # Determine if this is "plan pays" or "you pay" perspective
            # Only look for EXPLICIT indicators - don't infer from percentage value
            is_plan_pays = any(phrase in raw_lower for phrase in [
                'plan pays', 'we pay', 'covered at', 'coverage at',
                'paid at', 'reimbursed at', 'plan covers'
            ])
            is_you_pay = any(phrase in raw_lower for phrase in [
                'you pay', 'member pays', 'patient pays', 'your cost',
                'your share'  # Removed 'coinsurance' - too generic
            ])
            
            # Convert "plan pays X%" to "you pay (100-X)%" for consistency
            # ONLY when there's EXPLICIT "plan pays" language - never infer
            if is_plan_pays and not is_you_pay and pct >= 50:
                # This is "plan pays 80%" meaning "you pay 20%"
                original_pct = pct
                pct = 100 - pct
                result.notes.append(f"Converted from plan pays {original_pct}%")
            elif not is_plan_pays and not is_you_pay:
                # Ambiguous perspective - preserve value as-is, log for audit
                # Most documents show "member pays" coinsurance directly
                result.notes.append(f"Ambiguous perspective for {pct}% - preserved as-is")
            
            # Validate percentage range
            if 0 <= pct <= 100:
                result.coinsurance = f"{pct}%"
                result.confidence += 0.1
            else:
                result.notes.append(f"Invalid percentage: {pct}")
        
        # ======================================================================
        # STEP 4: Extract COPAY amount
        # ======================================================================
        copay_match = cls._match_any(cls.COPAY_PATTERNS, raw_value)
        if not copay_match:
            copay_match = cls.COPAY_PATTERN.search(raw_value)
        
        if copay_match:
            amount_str = copay_match.group(1).replace(",", "")
            try:
                amount = float(amount_str)
                # More generous sanity check (some high-cost services have high copays)
                if 0 <= amount < 50000:
                    # Format nicely
                    if amount == int(amount):
                        result.copay = f"${int(amount):,}"
                    else:
                        result.copay = f"${amount:,.2f}"
                    result.confidence += 0.1
                    
                    # Check for per-unit suffix
                    per_match = cls._match_any(cls.PER_UNIT_PATTERNS, raw_value)
                    if per_match:
                        unit = per_match.group(1).lower()
                        result.copay += f" per {unit}"
                else:
                    result.notes.append(f"Copay amount seems too high: ${amount_str}")
            except ValueError:
                result.notes.append(f"Could not parse copay: {amount_str}")
        
        # ======================================================================
        # STEP 5: Determine DEDUCTIBLE applicability (improved logic)
        # ======================================================================
        # The deductible logic needs to handle multiple scenarios:
        # 1. "After deductible" - coinsurance applies after deductible
        # 2. "Deductible waived" - deductible doesn't apply at all
        # 3. "Copay, then 20% after deductible" - copay first, then coinsurance after ded
        # 4. "Subject to deductible" - must meet deductible first
        # 5. Both patterns present - be more careful about interpretation
        
        has_waived = cls._matches_any(cls.DEDUCTIBLE_WAIVED_PATTERNS, raw_value)
        has_after_ded = cls._matches_any(cls.AFTER_DEDUCTIBLE_PATTERNS, raw_value)
        
        if has_waived and has_after_ded:
            # Both present - check context more carefully
            # If "copay" appears near "waived" and "coinsurance" near "after deductible"
            # then after_deductible should be True (coinsurance part applies after ded)
            raw_lower = raw_value.lower()
            
            # Find positions to determine which applies to coinsurance
            ded_pos = raw_lower.find('after deductible')
            if ded_pos == -1:
                ded_pos = raw_lower.find('subject to deductible')
            
            waived_pos = raw_lower.find('waived')
            if waived_pos == -1:
                waived_pos = raw_lower.find('does not apply')
            if waived_pos == -1:
                waived_pos = raw_lower.find('no deductible')
            
            # If "after deductible" appears later in text, it likely applies to main value
            if ded_pos > waived_pos and ded_pos != -1:
                result.after_deductible = True
                result.notes.append("Deductible applies (complex case with waiver)")
            else:
                result.after_deductible = False
                result.notes.append("Deductible waived (complex case)")
        elif has_waived:
            result.after_deductible = False
            result.notes.append("Deductible waived/does not apply")
        elif has_after_ded:
            result.after_deductible = True
        
        # ======================================================================
        # STEP 6: Check for PREAUTHORIZATION requirements
        # ======================================================================
        if cls._matches_any(cls.PREAUTH_REQUIRED_PATTERNS, raw_value):
            result.notes.append("Preauthorization required")
        elif cls._matches_any(cls.PREAUTH_NOT_REQUIRED_PATTERNS, raw_value):
            result.notes.append("Preauthorization not required")
        
        # ======================================================================
        # STEP 7: Extract LIMITS if present
        # ======================================================================
        for limit_pattern in cls.LIMIT_PATTERNS:
            limit_match = limit_pattern.search(raw_value)
            if limit_match:
                groups = limit_match.groups()
                if len(groups) >= 1:
                    result.notes.append(f"Limit: {limit_match.group(0)}")
                break
        
        # ======================================================================
        # STEP 8: Calculate final confidence
        # ======================================================================
        if result.coinsurance or result.copay:
            result.confidence = min(0.95, result.confidence + 0.1)
        elif not result.not_covered and not result.no_charge:
            result.confidence = 0.5
            # Try to extract any useful information from the text
            if raw_value and len(raw_value) > 5:
                result.notes.append(f"Could not parse: '{raw_value[:50]}'")
        
        return result


class SchemaRecordBuilder:
    """
    Builds BenefitRecord objects from extracted table rows.
    
    Features:
    - Schema-bound field mapping
    - Value parsing and normalization
    - Validation at every step
    - Confidence scoring
    - Detailed extraction notes
    """
    
    # Default field mappings
    DEFAULT_MAPPINGS: List[FieldMapping] = [
        FieldMapping(
            target_field="header",
            source_attribute="category",
            required=True,
        ),
        FieldMapping(
            target_field="service",
            source_attribute="service_name",
            required=True,
        ),
        FieldMapping(
            target_field="in_network_coinsurance",
            source_attribute="in_network_value",
        ),
        FieldMapping(
            target_field="out_of_network_coinsurance",
            source_attribute="out_of_network_value",
        ),
        FieldMapping(
            target_field="in_network_copay",
            source_attribute="in_network_copay",
        ),
        FieldMapping(
            target_field="out_of_network_copay",
            source_attribute="out_of_network_copay",
        ),
        FieldMapping(
            target_field="preauth_required",
            source_attribute="preauth",
        ),
    ]
    
    def __init__(
        self,
        mappings: Optional[List[FieldMapping]] = None,
        strict_mode: bool = False,
    ):
        """
        Initialize the record builder.
        
        Args:
            mappings: Custom field mappings (uses defaults if None)
            strict_mode: If True, reject records with missing required fields
        """
        self.mappings = mappings or self.DEFAULT_MAPPINGS
        self.strict_mode = strict_mode
        self.value_parser = ValueParser()
        
        # Header terms that should NOT be treated as service names
        # These are column headers that sometimes get misclassified
        self._header_terms = {
            # Network column headers
            "in-network", "in network", "innetwork", "in",
            "out-of-network", "out of network", "outofnetwork", "out",
            "oon", "non-par", "non-participating", "non participating",
            "participating", "par", "ppo", "hmo", "epo",
            "network", "network provider", "out-of-network provider",
            "in-network provider", "preferred provider",
            # Payment column headers
            "what you pay", "what you will pay", "you pay", "member pays",
            "plan pays", "we pay", "your cost", "member cost",
            "copay", "copayment", "co-pay", "coinsurance",
            # Other column headers
            "service", "services", "benefit", "benefits", "covered service",
            "coverage", "description", "limit", "limitation", "limitations",
            "preauthorization", "prior authorization", "notes",
            "type of service", "services you may need",
            # Common header fragments
            "(you will pay the least)", "(you will pay the most)",
            "required", "not required",
        }

    def _is_header_term(self, service_name: str) -> bool:
        """
        Check if service name is actually a misclassified header term.
        
        Returns True if the service name matches common column headers
        that should not be treated as benefit services.
        """
        name_lower = service_name.lower().strip()
        
        # Direct match
        if name_lower in self._header_terms:
            return True
        
        # Check if it's just a network indicator
        if re.match(r'^(in|out)[- ]?(of[- ]?)?network\s*(provider)?s?$', name_lower):
            return True
        
        # Check if it's a short generic term
        if len(name_lower) <= 3 and name_lower in {"in", "out", "n/a", "na", "oon"}:
            return True
        
        # Check if it starts with "what you" (column header)
        if name_lower.startswith("what you"):
            return True
        
        return False
    
    def _is_explanatory_text(self, service_name: str) -> bool:
        """
        Check if service name appears to be explanatory text rather than a service.
        
        Returns True if the text looks like a paragraph fragment, note, or disclaimer.
        """
        name_lower = service_name.lower().strip()
        original_name = service_name.strip()
        
        # Check for incomplete/truncated names (end with special characters)
        truncation_indicators = ['/', 'û', '–', '-', '*', ',', 'and', 'or', '+', '&']
        for indicator in truncation_indicators:
            if original_name.endswith(indicator) or original_name.endswith(indicator + ' '):
                return True
        
        # Check for names that start with fragments
        fragment_starters = ['of ', 'and ', 'or ', 'to ', 'with ', 'for ', 'at ', 'in ', 'on ', 'by ']
        for starter in fragment_starters:
            if name_lower.startswith(starter):
                return True
        
        # Check for common paragraph/sentence starters that indicate explanatory text
        explanatory_starters = [
            "see the ", "see also ", "refer to ", "please ", "note:", "note that",
            "if you ", "when you ", "once you ", "after you ", "before you ",
            "you may ", "you will ", "you can ", "you must ", "you should ",
            "the plan ", "this plan ", "your plan ", "the mit ", "mit's ",
            "benefits are ", "benefits will ", "coverage is ", "coverage will ",
            "includes ", "including ", "excludes ", "excluding ",
            "for more ", "for additional ", "for further ", "for details ",
            "failure to ", "in the event ", "in accordance ",
            "deductibles and ", "maximums are ", "limits are ",
            "charges for ", "charges made ",
            "individual will ", "individual and ", 
            "member pays ", "member must ", "members must ",
            "family members ", "family out-of-pocket ",
            "pursuant to ", "according to ", "based on ",
            "participants are ", "participants must ",
            "determined based ", "subject to ",
            "procedures are ", "services are ", "treatments are ",
            "enrolled in ", "must be enrolled ",
            "(booklet)", "(spd)", "booklet will ",
            "following ", "the following ",
            "complications of ", "reversal of ", "termination of ",
            "check)", "check),", "routine *",
            "non-network limited", "lifetime maximum",
            "treatment, including", "treatment including",
        ]
        
        for starter in explanatory_starters:
            if name_lower.startswith(starter):
                return True
        
        # Check for sentence fragments that indicate explanatory text
        explanatory_patterns = [
            r"\bwill be\s+(based|determined|considered|provided|covered)\b",
            r"\bwill result in\b",
            r"\bis required\b$",
            r"\bare covered\b$",
            r"\bare covered when\b",
            r"\bare not\b",
            r"\bhas been met\b",
            r"\bprior to\b",
            r"\bmaximum of\b$",
            r"\blimited to\b$",
            r"\bper benefit\b",
            r"\bper year\b$",
            r"\bmost complex\b",
            r"\bcomplexity of\b",
            r"\bis not covered\b",
            r"\bparticipants are\b",
            r"limited/combined",  # e.g. "Routine *Non-Network Limited/Combined"
        ]
        
        for pattern in explanatory_patterns:
            if re.search(pattern, name_lower):
                return True
        
        # Check for very short generic terms that are not services on their own
        generic_standalone_terms = {
            "specialist", "primary care", "emergency", "treatment", "imaging",
            "office visit", "outpatient/ambulatory", "inpatient", "outpatient",
            "radiologist", "inpatient services", "30 day supply",
            "generic", "preferred brand", "preferred brand *", "non-preferred brand", 
            "retail pharmacy", "mandatory specialty pharmacy",
            "family", "individual", "deductible", "incentive",
            "cardiac", "routine wellness /", "surgical sterilization",
            "nutritional counseling", "allergy testing", "allergy treatment",
            "ambulance, air*", "applied behavioral", "cam program",
            "chemotherapy /", "colonoscopy", "covid-19", "dialysis management",
            "durable medical", "home health care and", "mammogram",
            "prosthetics and", "room and board", "treatment, including",
            "scans", "mri, ct, pet", "routine wellness", "home health care",
            "lifetime maximum", "to a lifetime maximum", "participants are",
            "non-network limited", "preferred brand",
        }
        if name_lower in generic_standalone_terms:
            return True
        
        # Check for patterns with Unicode dashes (en-dash, em-dash, etc.)
        fragment_patterns = [
            r'^(colonoscopy|mammogram|chemotherapy|routine wellness)\s*[–\-û]?\s*$',
            r'^scans\s*[–\-û]\s*mri',
            r'^(inpatient|outpatient|emergency|treatment)\s*$',
            r'^(primary care|specialist|radiologist|imaging)\s*$',
            r'^(room and board)\s*$',  # only when standalone without context
            r'^(allergy testing|allergy treatment|ambulance.*air)\s*$',
            r'^(applied behavioral|cam program|nutritional)\s*$',
            r'^(covid-?19|dialysis management|durable medical)\s*$',
            r'^(prosthetics and|home health care and)\s*$',
            r'^(of\s+\w+\s+is)$',  # "of infertility is"
            r'^(to a )?lifetime maximum',
            r'^participants are\b',
            r'^non-network limited',
            r'^routine\s*\*',  # "routine *..."
        ]
        
        for pattern in fragment_patterns:
            if re.search(pattern, name_lower):
                return True
        
        # Check for text that ends with certain patterns indicating incomplete sentences
        explanatory_endings = [
            " to", " of", " for", " in", " at", " the", " a", " an",
            " and", " or", " but", " with", " by", " as", " if", " when",
            " is", " are", " was", " were", " will", " would", " should",
        ]
        
        for ending in explanatory_endings:
            if name_lower.endswith(ending) and len(name_lower) > 30:
                return True
        
        # Check word count - very long phrases are likely explanatory
        words = name_lower.split()
        if len(words) > 12:
            return True
        
        return False

    def build_from_extracted_rows(
        self,
        rows: List[ExtractedRow],
        document_type: str = "SPD",
    ) -> List[RawExtractionRecord]:
        """
        Build RawExtractionRecord objects from extracted rows.
        
        Args:
            rows: List of ExtractedRow from StructuredTableExtractor
            document_type: Type of document being processed
            
        Returns:
            List of RawExtractionRecord objects
        """
        records: List[RawExtractionRecord] = []
        current_category = "General Services"
        
        for row in rows:
            # Update category if this is a category header
            if row.is_category_header:
                current_category = row.service_name
                continue
            
            # Skip parent service rows (they are markers for hierarchy, not data rows)
            if row.is_parent_service:
                logger.debug(f"Skipping parent service marker: {row.service_name}")
                continue
            
            # Build record from row
            record = self._build_record(row, current_category)
            
            if record:
                records.append(record)
        
        logger.info(f"Built {len(records)} records from {len(rows)} extracted rows")
        return records

    def build_benefit_records(
        self,
        rows: List[ExtractedRow],
        document_type: str = "SPD",
    ) -> List[BenefitRecord]:
        """
        Build fully normalized BenefitRecord objects.
        
        Args:
            rows: List of ExtractedRow from StructuredTableExtractor
            document_type: Type of document being processed
            
        Returns:
            List of BenefitRecord objects
        """
        raw_records = self.build_from_extracted_rows(rows, document_type)
        benefit_records: List[BenefitRecord] = []
        
        for raw in raw_records:
            try:
                benefit = self._convert_to_benefit_record(raw)
                if benefit:
                    benefit_records.append(benefit)
            except Exception as e:
                logger.warning(f"Failed to convert record '{raw.service_name}': {e}")
        
        return benefit_records

    def _build_record(
        self,
        row: ExtractedRow,
        current_category: str,
    ) -> Optional[RawExtractionRecord]:
        """Build a single RawExtractionRecord from an ExtractedRow."""
        # Validate service name
        if not row.service_name or len(row.service_name.strip()) < 2:
            return None
        
        # Use full_service_name property to include parent context
        # This handles hierarchical structures like:
        #   "Office Visit for Injury / Illness" (parent)
        #       "Primary Care" (child) -> becomes "Office Visit for Injury / Illness - Primary Care"
        service_name = row.full_service_name.strip()
        
        # Skip if service name is a header term (misclassified column header)
        if self._is_header_term(service_name):
            logger.debug(f"Skipping header-like service name: {service_name}")
            return None
        
        # Check if row has any coverage values (IN or OUT network)
        has_values = bool(row.in_network_value or row.out_of_network_value or 
                         row.in_network_copay or row.out_of_network_copay)
        
        # Skip if service name appears to be explanatory text
        # BUT only if there are no associated values - services with values are legitimate
        if not has_values and self._is_explanatory_text(service_name):
            logger.debug(f"Skipping explanatory text (no values): {service_name[:60]}...")
            return None
        
        # Skip if service name is too long (likely explanatory text, not a service)
        # Increased limit to 300 to accommodate hierarchical names
        if len(service_name) > 300:
            logger.debug(f"Skipping row with overly long service name ({len(service_name)} chars)")
            return None
        
        # Truncate service names longer than 150 chars (increased for hierarchical names)
        if len(service_name) > 150:
            service_name = service_name[:147] + "..."
            logger.debug(f"Truncated long service name to 150 chars")
        
        # Skip if service name looks like explanatory text (contains too many sentences/periods)
        if service_name.count('. ') > 2:
            logger.debug(f"Skipping row that appears to be explanatory text: {service_name[:50]}...")
            return None
        
        # Determine category - prefer row's category if set, otherwise use current
        category = row.category if row.category and row.category != "General Services" else current_category
        
        # Parse in-network value
        in_parsed = self.value_parser.parse(row.in_network_value)
        out_parsed = self.value_parser.parse(row.out_of_network_value)
        
        # Build in-network text
        in_network_text = self._build_value_text(in_parsed, row.in_network_copay)
        
        # Build out-of-network text
        out_network_text = self._build_value_text(out_parsed, row.out_of_network_copay)
        
        # Determine preauth
        preauth_text = None
        if row.preauth:
            preauth_text = self._normalize_preauth(row.preauth)
        
        # Calculate combined confidence
        confidence = self._calculate_confidence(row, in_parsed, out_parsed)
        
        return RawExtractionRecord(
            service_category=category,
            service_name=service_name,  # Use potentially truncated service_name
            in_network_text=in_network_text,
            out_of_network_text=out_network_text,
            preauth_text=preauth_text,
            limit_text=row.limitations,
            page_number=row.page_number if row.page_number > 0 else None,
            table_index=row.table_index if row.table_index >= 0 else None,
            row_index=row.row_index if row.row_index >= 0 else None,
            extraction_method="schema_bound",
            raw_confidence=confidence,
        )

    def _build_value_text(
        self,
        parsed: ParsedValue,
        copay_override: Optional[str] = None,
    ) -> Optional[str]:
        """Build a formatted value text from parsed components."""
        parts = []
        
        if parsed.not_covered:
            return "Not covered"
        
        if parsed.no_charge:
            return "No charge"
        
        # Add copay (prefer explicit copay field)
        copay = copay_override or parsed.copay
        if copay:
            parts.append(copay)
        
        # Add coinsurance
        if parsed.coinsurance:
            parts.append(parsed.coinsurance)
        
        if not parts:
            return None
        
        result = "; ".join(parts)
        
        # Add after deductible suffix
        if parsed.after_deductible:
            result += " after deductible"
        
        return result

    def _normalize_preauth(self, preauth_text: str) -> Optional[str]:
        """Normalize preauth text to standard value."""
        if not preauth_text:
            return None
        
        text_lower = preauth_text.lower().strip()
        
        # Check "may be" first before "required" (order matters)
        if any(kw in text_lower for kw in ["may be", "sometimes", "possible"]):
            return "May Be Required"
        elif any(kw in text_lower for kw in ["not required"]):
            return "Not Required"
        elif any(kw in text_lower for kw in ["required", "yes", "needed", "must"]):
            return "Required"
        elif text_lower in ["no", "none"]:
            return "Not Required"
        
        # If it's just a checkmark or similar
        if text_lower in ["x", "✓", "✔"]:
            return "Required"
        
        return None

    def _calculate_confidence(
        self,
        row: ExtractedRow,
        in_parsed: ParsedValue,
        out_parsed: ParsedValue,
    ) -> float:
        """Calculate overall confidence for a record."""
        # Start with row's extraction confidence
        confidence = row.confidence
        
        # Adjust based on parsing confidence
        confidence = confidence * 0.5 + in_parsed.confidence * 0.3 + out_parsed.confidence * 0.2
        
        # Boost for complete data
        if in_parsed.coinsurance or in_parsed.copay:
            confidence += 0.05
        if out_parsed.coinsurance or out_parsed.copay:
            confidence += 0.05
        
        # Penalize missing values
        if not row.in_network_value and not row.in_network_copay:
            confidence -= 0.1
        
        return max(0.0, min(1.0, confidence))

    def _convert_to_benefit_record(
        self,
        raw: RawExtractionRecord,
    ) -> Optional[BenefitRecord]:
        """Convert RawExtractionRecord to BenefitRecord with full normalization."""
        try:
            # Parse the text values
            in_parsed = self.value_parser.parse(raw.in_network_text)
            out_parsed = self.value_parser.parse(raw.out_of_network_text)
            
            # Truncate service name if too long (max 500 chars per schema)
            service_name = raw.service_name
            if len(service_name) > 480:
                service_name = service_name[:477] + "..."
            
            # Truncate header/category if too long
            header = raw.service_category or "General Services"
            if len(header) > 200:
                header = header[:197] + "..."
            
            return BenefitRecord(
                header=header,
                service=service_name,
                in_network_coinsurance=self._format_coinsurance(in_parsed),
                out_of_network_coinsurance=self._format_coinsurance(out_parsed),
                in_network_after_deductible="Yes" if in_parsed.after_deductible else "No",
                out_of_network_after_deductible="Yes" if out_parsed.after_deductible else "No",
                in_network_copay=in_parsed.copay,
                out_of_network_copay=out_parsed.copay,
                preauth_required=raw.preauth_text,
                confidence_score=raw.raw_confidence,
            )
        except Exception as e:
            logger.debug(f"Could not convert to BenefitRecord: {e}")
            return None

    def _format_coinsurance(self, parsed: ParsedValue) -> Optional[str]:
        """Format coinsurance value for output."""
        if parsed.not_covered:
            return "NOT COVERED"
        if parsed.no_charge:
            return "0%"
        return parsed.coinsurance


class RecordDeduplicator:
    """
    Removes duplicate benefit records while keeping the most complete version.
    """
    
    def __init__(self, similarity_threshold: float = 0.85):
        """
        Initialize deduplicator.
        
        Args:
            similarity_threshold: Minimum similarity to consider as duplicate
        """
        self.similarity_threshold = similarity_threshold

    def deduplicate(
        self,
        records: List[RawExtractionRecord],
    ) -> List[RawExtractionRecord]:
        """
        Remove duplicate records.
        
        Strategy:
        1. Group by normalized service name
        2. Keep the most complete record from each group
        """
        seen: Dict[str, RawExtractionRecord] = {}
        
        for record in records:
            # Create composite key from category + service name
            key = self._normalize_key(record.service_name, record.service_category)
            
            if key in seen:
                # Keep the more complete record
                existing = seen[key]
                if self._completeness_score(record) > self._completeness_score(existing):
                    seen[key] = record
            else:
                seen[key] = record
        
        result = list(seen.values())
        
        if len(result) < len(records):
            logger.info(f"Deduplicated {len(records)} -> {len(result)} records")
        
        return result

    def _normalize_key(self, service_name: str, category: Optional[str] = None) -> str:
        """
        Create a normalized key for grouping.
        
        Uses both category and service name to avoid false deduplication of
        services with similar names in different categories.
        
        Examples:
            "Office Visit for Injury / Illness - Primary Care" + category "Physician Services"
            "Office Visit for Injury / Illness - Specialist" + category "Physician Services"
            These should NOT be deduplicated as they are different services.
        """
        if not service_name:
            return ""
        
        # Include category in the key to prevent cross-category deduplication
        category_prefix = ""
        if category:
            cat_lower = category.lower().strip()
            # Take first 30 chars of category for the key
            category_prefix = re.sub(r"[^\w\s]", "", cat_lower)[:30] + "::"
        
        # Normalize the service name
        key = service_name.lower().strip()
        key = re.sub(r"[^\w\s-]", "", key)  # Keep hyphens for hierarchical names
        key = re.sub(r"\s+", " ", key)  # Normalize whitespace
        
        # Singularize common plural endings for deduplication
        # This handles cases like "Visit" vs "Visits", "Service" vs "Services"
        key = re.sub(r"\b(\w+)(s)\b(?!.*\1)", lambda m: m.group(1) if m.group(1).endswith(('it', 'ce', 'ice', 'ure', 'ase', 'ine', 'ure', 'ery', 'ity')) else m.group(0), key)
        # Simpler approach: strip trailing 's' from last word if it makes sense
        words = key.split()
        if words and words[-1].endswith('s') and len(words[-1]) > 4:
            # Don't strip 's' from words like "services" that are always plural
            if not words[-1].endswith('ices'):
                words[-1] = words[-1].rstrip('s')
        key = ' '.join(words)
        
        # DO NOT truncate too aggressively - use 100 characters instead of 40
        full_key = category_prefix + key[:100]
        
        return full_key

    def _completeness_score(self, record: RawExtractionRecord) -> int:
        """Score how complete a record is."""
        score = 0
        
        if record.service_name:
            score += 2
        if record.in_network_text:
            score += 3
        if record.out_of_network_text:
            score += 3
        if record.preauth_text:
            score += 1
        if record.limit_text:
            score += 1
        
        # Boost for higher confidence
        score += int(record.raw_confidence * 2)
        
        return score


# Convenience function for direct usage
def build_records_from_tables(
    tables: List[Dict[str, Any]],
    document_type: str = "SPD",
) -> List[RawExtractionRecord]:
    """
    High-level function to extract and build records from tables.
    
    Args:
        tables: List of table dicts from Azure Document Intelligence
        document_type: Type of document
        
    Returns:
        List of RawExtractionRecord objects
    """
    from src.parsers.table_extractor import StructuredTableExtractor
    
    # Extract rows from tables
    extractor = StructuredTableExtractor()
    extracted_rows = extractor.extract_from_tables(tables)
    
    # Build records
    builder = SchemaRecordBuilder()
    records = builder.build_from_extracted_rows(extracted_rows, document_type)
    
    # Deduplicate
    deduplicator = RecordDeduplicator()
    records = deduplicator.deduplicate(records)
    
    return records
