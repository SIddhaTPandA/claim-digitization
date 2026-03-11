"""
Production-grade text parser for SPD/SBC benefit extraction.

This module provides robust parsing of benefit text from PDF documents,
handling various document formats and nomenclatures.

Design Principles:
- Pattern-based extraction with configurable patterns
- Multi-pass parsing for different document formats
- Robust handling of OCR artifacts and spacing issues
- No hardcoded service names - pattern-based detection
"""

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass
class ParsedBenefit:
    """Represents a parsed benefit row."""
    service_name: str
    in_network_value: Optional[str] = None
    out_of_network_value: Optional[str] = None
    in_network_copay: Optional[str] = None
    out_of_network_copay: Optional[str] = None
    after_deductible_in: bool = False
    after_deductible_out: bool = False
    category: str = "General Services"
    limitations: Optional[str] = None
    preauth_required: bool = False
    confidence: float = 0.8


@dataclass
class BenefitPatterns:
    """Compiled regex patterns for benefit extraction."""
    
    # Value patterns
    coinsurance: re.Pattern = field(default_factory=lambda: re.compile(
        r'(\d{1,3})\s*%\s*(?:coinsurance|coins?\.?)?',
        re.IGNORECASE
    ))
    
    copay: re.Pattern = field(default_factory=lambda: re.compile(
        r'\$\s*([\d,]+(?:\.\d{2})?)\s*(?:copay(?:ment)?|co-?pay)?',
        re.IGNORECASE
    ))
    
    no_charge: re.Pattern = field(default_factory=lambda: re.compile(
        r'(?:no\s+charge|covered\s+in\s+full|\$?\s*0\s*(?:copay)?|100\s*%\s*covered)',
        re.IGNORECASE
    ))
    
    not_covered: re.Pattern = field(default_factory=lambda: re.compile(
        r'(?:not\s+covered|no\s+(?:coverage|benefit)|excluded|n/?a(?:\s|$)|does\s+not\s+apply)',
        re.IGNORECASE
    ))
    
    after_deductible: re.Pattern = field(default_factory=lambda: re.compile(
        r'(?:after|subject\s+to)\s+(?:the\s+)?(?:plan\s+)?deductible',
        re.IGNORECASE
    ))
    
    deductible_waived: re.Pattern = field(default_factory=lambda: re.compile(
        r'(?:deductible\s+(?:does\s+not|doesn\'t)\s+apply|no\s+deductible|deductible\s+waived)',
        re.IGNORECASE
    ))
    
    preauth: re.Pattern = field(default_factory=lambda: re.compile(
        r'(?:pre-?(?:certification|authorization)|prior\s+auth(?:orization)?)\s*(?:required|may\s+be\s+required|needed)?',
        re.IGNORECASE
    ))
    
    # Service patterns - common healthcare services
    service_indicators: re.Pattern = field(default_factory=lambda: re.compile(
        r'(?:visit|care|service|treatment|surgery|hospital|admission|'
        r'emergency|urgent|specialist|physician|office|clinic|'
        r'lab(?:oratory)?|imaging|x-?ray|mri|ct|scan|'
        r'therapy|rehabilitation|physical|occupational|speech|'
        r'mental\s+health|behavioral|substance|'
        r'prescription|drug|medication|pharmacy|'
        r'maternity|prenatal|postnatal|delivery|'
        r'preventive|screening|immunization|wellness|'
        r'ambulance|transportation|'
        r'skilled\s+nursing|home\s+health|hospice|'
        r'durable\s+medical|equipment|prosthetic|'
        r'dialysis|chemotherapy|radiation|transplant)',
        re.IGNORECASE
    ))
    
    # Category headers
    category_header: re.Pattern = field(default_factory=lambda: re.compile(
        r'^(?:if\s+you\s+(?:visit|need|have|are)|'
        r'common\s+medical\s+event|'
        r'medical\s+services|'
        r'(?:inpatient|outpatient)\s+(?:hospital|care|services)|'
        r'emergency\s+(?:services|care|room)|'
        r'mental\s+health\s+(?:and|&)\s+substance|'
        r'prescription\s+drugs?|'
        r'preventive\s+care|'
        r'pregnancy\s+(?:and|&)\s+maternity|'
        r'recovery\s+(?:and|&)\s+rehabilitation)',
        re.IGNORECASE
    ))


class BenefitTextParser:
    """
    Production-grade parser for extracting benefits from SPD/SBC text.
    
    Handles multiple document formats and provides robust extraction
    even with OCR artifacts and spacing issues.
    """
    
    def __init__(self, patterns: Optional[BenefitPatterns] = None):
        """
        Initialize parser with optional custom patterns.
        
        Args:
            patterns: Custom patterns for extraction (uses defaults if None)
        """
        self.patterns = patterns or BenefitPatterns()
        
        # Compiled pattern for splitting benefit lines
        self._benefit_line_pattern = re.compile(
            # Service name followed by percentage or dollar values
            r'([A-Za-z][A-Za-z\s\-/,()]+?)'  # Service name (letters, spaces, some punctuation)
            r'\s+'  # Whitespace separator
            r'('  # Start capturing benefit values
            r'(?:'  # Non-capturing group for value options
            r'\d{1,3}\s*%\s*(?:coinsurance)?|'  # Percentage
            r'\$\s*[\d,]+(?:\.\d{2})?(?:\s*(?:copay|per\s+\w+))?|'  # Dollar amount
            r'no\s+charge|'  # No charge
            r'not\s+covered|'  # Not covered
            r'covered\s+in\s+full|'  # Covered in full
            r'included'  # Included
            r')'
            r'(?:\s*(?:after|&)?\s*(?:deductible|balance\s+bill))?'  # Optional deductible mention
            r')',
            re.IGNORECASE
        )
    
    def parse_document(self, text: str) -> List[ParsedBenefit]:
        """
        Parse entire document text and extract all benefits.
        
        Args:
            text: Full document text
            
        Returns:
            List of ParsedBenefit objects
        """
        if not text:
            return []
        
        benefits = []
        current_category = "General Services"
        
        # Split into logical sections
        lines = self._split_into_lines(text)
        
        i = 0
        while i < len(lines):
            line = lines[i].strip()
            
            if not line:
                i += 1
                continue
            
            # Check for category header
            if self._is_category_header(line):
                current_category = self._extract_category_name(line)
                i += 1
                continue
            
            # Try to parse as benefit line
            parsed = self._parse_benefit_line(line, current_category)
            if parsed:
                # Check next lines for additional info (OON value, limitations)
                if i + 1 < len(lines):
                    next_line = lines[i + 1].strip()
                    parsed = self._merge_continuation(parsed, next_line)
                
                benefits.append(parsed)
            
            i += 1
        
        # Deduplicate and clean
        benefits = self._deduplicate_benefits(benefits)
        
        logger.info(f"Parsed {len(benefits)} benefits from text")
        return benefits
    
    def _split_into_lines(self, text: str) -> List[str]:
        """Split text into logical lines for processing."""
        # Normalize whitespace
        text = re.sub(r'\r\n|\r', '\n', text)
        
        # Split on newlines
        lines = text.split('\n')
        
        # Also split on patterns that indicate new benefit entries
        expanded_lines = []
        for line in lines:
            # Split if we see a service indicator followed by a percentage
            parts = re.split(
                r'(?<=[a-z])\s+(?=(?:Primary|Specialist|Emergency|Urgent|'
                r'Preventive|Mental|Prescription|Inpatient|Outpatient|'
                r'Lab|Imaging|Surgery))',
                line,
                flags=re.IGNORECASE
            )
            expanded_lines.extend(parts)
        
        return expanded_lines
    
    def _is_category_header(self, line: str) -> bool:
        """Check if line is a category header."""
        if len(line) > 150:
            return False
        
        # Must not contain benefit values
        if self.patterns.coinsurance.search(line):
            if self.patterns.service_indicators.search(line):
                return False  # This is a benefit line, not a header
        
        return bool(self.patterns.category_header.search(line))
    
    def _extract_category_name(self, line: str) -> str:
        """Extract clean category name from header line."""
        # Clean common prefixes
        cleaned = re.sub(r'^(?:if\s+you\s+\w+\s+)', '', line, flags=re.IGNORECASE)
        cleaned = re.sub(r'\s+', ' ', cleaned).strip()
        
        # Truncate if too long
        if len(cleaned) > 50:
            cleaned = cleaned[:50]
        
        return cleaned or "General Services"
    
    def _parse_benefit_line(
        self, line: str, category: str
    ) -> Optional[ParsedBenefit]:
        """
        Parse a single line to extract benefit information.
        
        Args:
            line: Text line to parse
            category: Current category context
            
        Returns:
            ParsedBenefit if successful, None otherwise
        """
        if not line or len(line) < 5:
            return None
        
        # Must contain either a percentage or dollar amount
        has_coinsurance = self.patterns.coinsurance.search(line)
        has_copay = self.patterns.copay.search(line)
        has_no_charge = self.patterns.no_charge.search(line)
        has_not_covered = self.patterns.not_covered.search(line)
        
        if not (has_coinsurance or has_copay or has_no_charge or has_not_covered):
            return None
        
        # Extract service name (text before first value)
        service_name = self._extract_service_name(line)
        if not service_name or len(service_name) < 3:
            return None
        
        # Extract benefit values
        in_network, out_network = self._extract_network_values(line)
        
        # Extract copay values
        copays = self._extract_copays(line)
        
        # Check for deductible flags
        after_ded_in = bool(self.patterns.after_deductible.search(line))
        ded_waived = bool(self.patterns.deductible_waived.search(line))
        
        # Check for preauth
        preauth = bool(self.patterns.preauth.search(line))
        
        # Calculate confidence
        confidence = self._calculate_confidence(
            service_name, in_network, out_network, copays
        )
        
        return ParsedBenefit(
            service_name=service_name,
            in_network_value=in_network,
            out_of_network_value=out_network,
            in_network_copay=copays[0] if copays else None,
            out_of_network_copay=copays[1] if len(copays) > 1 else None,
            after_deductible_in=after_ded_in and not ded_waived,
            after_deductible_out=after_ded_in,
            category=category,
            preauth_required=preauth,
            confidence=confidence,
        )
    
    def _extract_service_name(self, line: str) -> Optional[str]:
        """Extract service name from benefit line."""
        # Find the position of the first benefit value
        first_value_pos = len(line)
        
        # Check for percentage
        match = re.search(r'\d{1,3}\s*%', line)
        if match:
            first_value_pos = min(first_value_pos, match.start())
        
        # Check for dollar amount
        match = re.search(r'\$\s*[\d,]+', line)
        if match:
            first_value_pos = min(first_value_pos, match.start())
        
        # Check for "No charge"
        match = re.search(r'no\s+charge', line, re.IGNORECASE)
        if match:
            first_value_pos = min(first_value_pos, match.start())
        
        # Check for "Not covered"
        match = re.search(r'not\s+covered', line, re.IGNORECASE)
        if match:
            first_value_pos = min(first_value_pos, match.start())
        
        if first_value_pos == 0 or first_value_pos == len(line):
            return None
        
        service_name = line[:first_value_pos].strip()
        
        # Clean up the service name
        service_name = re.sub(r'\s+', ' ', service_name)
        service_name = re.sub(r'^[\*\-•]+\s*', '', service_name)
        service_name = re.sub(r'[\s,;:]+$', '', service_name)
        
        # Skip if this is a header term (misclassified column header)
        if self._is_header_term(service_name):
            return None
        
        # Truncate long service names to 80 chars
        if len(service_name) > 80:
            service_name = service_name[:77] + "..."
        
        # Validate - should be primarily alphabetic
        alpha_chars = sum(1 for c in service_name if c.isalpha())
        if alpha_chars < len(service_name) * 0.5:
            return None
        
        return service_name if len(service_name) >= 3 else None
    
    def _is_header_term(self, service_name: str) -> bool:
        """Check if service name is actually a misclassified header term."""
        name_lower = service_name.lower().strip()
        
        # Header terms that should NOT be service names
        header_terms = {
            "in-network", "in network", "innetwork", "in",
            "out-of-network", "out of network", "outofnetwork", "out",
            "oon", "non-par", "non-participating", "participating", "par",
            "network", "network provider", "preferred provider",
            "what you pay", "what you will pay", "you pay", "member pays",
            "plan pays", "we pay", "your cost", "copay", "coinsurance",
            "service", "services", "benefit", "benefits", "covered service",
            "coverage", "description", "limit", "limitation", "limitations",
            "required", "not required",
        }
        
        if name_lower in header_terms:
            return True
        
        # Check for network indicators
        if re.match(r'^(in|out)[- ]?(of[- ]?)?network\s*(provider)?s?$', name_lower):
            return True
        
        return False

    def _extract_network_values(self, line: str) -> Tuple[Optional[str], Optional[str]]:
        """
        Extract in-network and out-of-network values.
        
        For SBC/SPD documents, typically:
        - First percentage = In-Network
        - Second percentage = Out-of-Network
        """
        in_network = None
        out_network = None
        
        # Check for "Not covered" first
        not_covered_matches = list(self.patterns.not_covered.finditer(line))
        no_charge_matches = list(self.patterns.no_charge.finditer(line))
        coinsurance_matches = list(self.patterns.coinsurance.finditer(line))
        
        # Combine all value-like matches with their positions
        values = []
        
        for m in coinsurance_matches:
            pct = int(m.group(1))
            # Convert to "you pay" format if > 50% (likely plan pays)
            if pct > 50:
                values.append((m.start(), f"{100 - pct}%"))
            else:
                values.append((m.start(), f"{pct}%"))
        
        for m in no_charge_matches:
            values.append((m.start(), "No charge"))
        
        for m in not_covered_matches:
            values.append((m.start(), "Not covered"))
        
        # Sort by position
        values.sort(key=lambda x: x[0])
        
        if len(values) >= 1:
            in_network = values[0][1]
        if len(values) >= 2:
            out_network = values[1][1]
        
        return in_network, out_network
    
    def _extract_copays(self, line: str) -> List[str]:
        """Extract copay amounts from line."""
        copays = []
        
        for match in self.patterns.copay.finditer(line):
            amount = match.group(1).replace(',', '')
            try:
                formatted = f"${int(float(amount)):,}"
                copays.append(formatted)
            except ValueError:
                copays.append(f"${amount}")
        
        return copays
    
    def _merge_continuation(
        self, benefit: ParsedBenefit, next_line: str
    ) -> ParsedBenefit:
        """Merge information from continuation line."""
        # If we don't have OON value and next line has one
        if not benefit.out_of_network_value:
            match = self.patterns.coinsurance.search(next_line)
            if match:
                benefit.out_of_network_value = f"{match.group(1)}%"
        
        # Check for limitations
        if 'limit' in next_line.lower() or 'day' in next_line.lower():
            benefit.limitations = next_line.strip()[:100]
        
        # Check for preauth
        if self.patterns.preauth.search(next_line):
            benefit.preauth_required = True
        
        return benefit
    
    def _calculate_confidence(
        self,
        service_name: Optional[str],
        in_network: Optional[str],
        out_network: Optional[str],
        copays: List[str],
    ) -> float:
        """Calculate extraction confidence score."""
        confidence = 0.7
        
        if service_name and len(service_name) > 5:
            confidence += 0.05
        
        if in_network:
            confidence += 0.1
        
        if out_network:
            confidence += 0.05
        
        if copays:
            confidence += 0.05
        
        return min(1.0, confidence)
    
    def _deduplicate_benefits(
        self, benefits: List[ParsedBenefit]
    ) -> List[ParsedBenefit]:
        """Remove duplicate benefits, keeping the most complete."""
        seen = {}
        
        for benefit in benefits:
            key = benefit.service_name.lower()[:30]
            
            if key in seen:
                # Keep the one with more data
                existing = seen[key]
                if self._completeness_score(benefit) > self._completeness_score(existing):
                    seen[key] = benefit
            else:
                seen[key] = benefit
        
        return list(seen.values())
    
    def _completeness_score(self, benefit: ParsedBenefit) -> int:
        """Score how complete a benefit record is."""
        score = 0
        if benefit.service_name:
            score += 1
        if benefit.in_network_value:
            score += 2
        if benefit.out_of_network_value:
            score += 2
        if benefit.in_network_copay:
            score += 1
        if benefit.out_of_network_copay:
            score += 1
        return score


def parse_benefit_value(text: str) -> Dict[str, Any]:
    """
    Parse a single benefit value string into structured components.
    
    Args:
        text: Benefit value text like "80% after deductible" or "$20 copay"
        
    Returns:
        Dictionary with parsed components
    """
    if not text:
        return {}
    
    result = {}
    patterns = BenefitPatterns()
    
    # Check for not covered
    if patterns.not_covered.search(text):
        result['value'] = 'Not covered'
        result['type'] = 'exclusion'
        return result
    
    # Check for no charge
    if patterns.no_charge.search(text):
        result['value'] = 'No charge'
        result['coinsurance'] = '0%'
        result['type'] = 'no_cost'
        return result
    
    # Extract coinsurance
    match = patterns.coinsurance.search(text)
    if match:
        result['coinsurance'] = f"{match.group(1)}%"
        result['type'] = 'coinsurance'
    
    # Extract copay
    match = patterns.copay.search(text)
    if match:
        amount = match.group(1).replace(',', '')
        result['copay'] = f"${int(float(amount)):,}"
        result['type'] = result.get('type', 'copay')
    
    # Check for deductible
    if patterns.after_deductible.search(text):
        result['after_deductible'] = True
    elif patterns.deductible_waived.search(text):
        result['after_deductible'] = False
    
    return result
