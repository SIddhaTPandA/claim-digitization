"""
Extraction Configuration - All patterns, thresholds, and mappings.

This file centralizes all configurable parameters for benefit extraction.
No hardcoded values should exist in extraction logic - everything comes from here.
"""

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Pattern, Optional, Any
import re

logger = logging.getLogger(__name__)


@dataclass
class ConfidenceThresholds:
    """Confidence score thresholds for extraction quality."""
    
    # Minimum confidence for auto-approval (no human review)
    auto_approve: float = 0.70
    
    # Confidence for table-based extraction (higher quality)
    table_extraction: float = 0.85
    
    # Confidence for text-based extraction (lower quality)
    text_extraction: float = 0.60
    
    # Confidence for pattern-matched extraction
    pattern_extraction: float = 0.75
    
    # Penalty for missing required fields
    missing_field_penalty: float = 0.10
    
    # Penalty for ambiguous values
    ambiguous_value_penalty: float = 0.05


@dataclass
class TableHeaderPatterns:
    """
    Patterns for detecting column headers in benefit tables.
    
    Each key is a semantic role, value is list of patterns to match.
    Patterns starting with ^ are treated as regex, others as substring matches.
    """
    
    # Service/Benefit name column headers
    service_name: List[str] = field(default_factory=lambda: [
        # Standard service headers
        "service", "benefit", "covered service", "medical service",
        "type of service", "services you may need", "description",
        # SBC-style headers
        "^what you", "if you", "common medical event", "health care",
        # Schedule of benefits style
        "category", "covered expense", "expense", "provision",
        # Column 1 indicators
        "^benefit type", "^coverage", "^item", "^procedure",
    ])
    
    # In-Network column headers
    in_network_value: List[str] = field(default_factory=lambda: [
        # Direct mentions
        "^in[- ]?network", "in-network", "in network", "innetwork",
        # Provider-based
        "participating", "preferred provider", "preferred", "par\\b",
        "ppo", "hmo", "epo", "tier\\s*1", "tier\\s*i\\b",
        # Cost-focused
        "what you will pay", "what you pay", "your cost", "member cost",
        "member pays", "you pay", "patient pays", "your share",
        # Coverage-focused
        "plan pays", "we pay", "coverage", "benefit amount",
        # Network-qualified
        "network benefit", "in[- ]?net\\b", "\\bin\\b.*benefit",
        # Abbreviated
        "\\bin\\b", "i/?n\\b",
    ])
    
    # Out-of-Network column headers
    out_of_network_value: List[str] = field(default_factory=lambda: [
        # Direct mentions
        "^out[- ]?of[- ]?network", "out-of-network", "out of network", "oon",
        # Provider-based
        "non[- ]?participating", "non[- ]?par\\b", "non[- ]?ppo",
        "non[- ]?preferred", "other provider", "tier\\s*2", "tier\\s*ii\\b",
        # Out-of-area
        "out[- ]?of[- ]?area", "out of area",
        # Cost-focused with out-of-network context
        "your cost.*out", "member pays.*out", "you pay.*out",
        # Abbreviated
        "\\bout\\b", "o/?o/?n\\b",
    ])
    
    # Copay-specific columns
    in_network_copay: List[str] = field(default_factory=lambda: [
        "copay.*in", "co-?pay.*in", "copayment.*in", "in.*copay",
        "network.*copay", "par.*copay",
    ])
    
    out_of_network_copay: List[str] = field(default_factory=lambda: [
        "copay.*out", "co-?pay.*out", "copayment.*out", "out.*copay",
        "non.*copay", "oon.*copay",
    ])
    
    # Limitations column
    limitations: List[str] = field(default_factory=lambda: [
        "limit", "limitation", "maximum", "max\\b", "restriction",
        "exclusion", "day limit", "visit limit", "annual limit",
        "lifetime", "benefit period", "quantity",
    ])
    
    # Pre-authorization column
    preauth: List[str] = field(default_factory=lambda: [
        "pre[- ]?auth", "preauth", "prior auth", "precert", "pre[- ]?cert",
        "authorization", "approval", "pre[- ]?approval", "referral",
        "prior authorization",
    ])
    
    # Notes column
    notes: List[str] = field(default_factory=lambda: [
        "note", "comment", "additional", "remark", "special",
        "explanation", "detail", "condition",
    ])


@dataclass
class CategoryDetectionPatterns:
    """
    Patterns for detecting category/section headers in tables.
    
    These are rows that indicate a new section (e.g., "If you visit a doctor...").
    All patterns are regex (case-insensitive).
    """
    
    patterns: List[str] = field(default_factory=lambda: [
        # SBC-style question headers
        r"^if you\s+(visit|need|have|are|get|receive|stay|go)",
        r"^if you\s+have\s+a\s+(test|hospital|baby|surgery|procedure)",
        r"^if you\s+are\s+(pregnant|hospitalized|injured)",
        r"^if you\s+need\s+(drugs|medication|help|immediate|surgery)",
        r"^if your\s+child\s+(needs|is)",
        r"^common medical event",
        r"^what happens if",
        # Service category headers
        r"^(inpatient|outpatient)\s+(hospital|care|services?)",
        r"^hospital\s+(inpatient|outpatient|services?)",
        r"^emergency\s+(services?|care|room)",
        r"^urgent\s+care\s*(services?)?$",
        # ADDED: Combined emergency/urgent patterns
        r"^emergency\s+(?:and|&)\s+urgent\s+care(?:\s+services?)?",
        r"^(?:emergency|urgent)\s+(?:and|&)\s+(?:emergency|urgent)\s+care",
        # ADDED: Physician services patterns
        r"^physician\s+(?:services?|care|visits?)",
        r"^(?:doctor|medical)\s+(?:services?|care|visits?)",
        r"^(?:primary|specialist)\s+(?:care|services?)",
        r"^office\s+(?:visits?|services?|care)",
        # Mental health / Substance
        r"^mental\s+health",
        r"^behavioral\s+health",
        r"^substance\s+(abuse|use|disorder)",
        # ADDED: Combined mental health patterns
        r"^mental\s+health\s+(?:and|&)\s+substance",
        r"^behavioral\s+health\s+(?:and|&)\s+substance",
        # Medications
        r"^prescription\s+(drugs?|medications?)",
        r"^pharmacy\s+(benefits?|services?)",
        r"^rx\s+benefit",
        r"^drugs?\s+you\s+take",
        # Preventive
        r"^preventive\s+(?:care|services?)",
        r"^wellness",
        r"^routine\s+care",
        # Maternity
        r"^maternity",
        r"^pregnancy",
        r"^prenatal",
        r"^childbirth",
        r"^if you\s+(?:are\s+)?(?:have\s+a\s+baby|pregnant)",
        # ADDED: Maternity and delivery patterns
        r"^maternity\s+(?:and|&)\s+(?:newborn|delivery)",
        r"^pregnancy\s+(?:and|&)\s+(?:maternity|delivery)",
        # Rehab / Recovery
        r"^rehabilitation",
        r"^recovery",
        r"^physical\s+therapy",
        r"^occupational\s+therapy",
        r"^if you\s+need\s+help\s+recovering",
        # ADDED: Therapy services patterns
        r"^(?:therapy|rehabilitation)\s+services?",
        r"^(?:physical|occupational|speech)\s+therapy\s+services?",
        # Long term care
        r"^skilled\s+nursing",
        r"^home\s+health",
        r"^hospice",
        r"^long[- ]?term\s+care",
        # Equipment / Supplies
        r"^durable\s+medical",
        r"^dme\b",
        r"^medical\s+equipment",
        r"^prosthetic",
        # Diagnostic
        r"^diagnostic",
        r"^lab(?:oratory)?",
        r"^imaging",
        r"^x-?ray",
        # ADDED: Diagnostic services combined patterns
        r"^(?:diagnostic|lab|imaging)\s+services?",
        r"^laboratory\s+(?:and|&)\s+(?:diagnostic|imaging)",
        # Other services
        r"^vision\s+(?:care|services?)",
        r"^dental\s+(?:care|services?)",
        r"^hearing\s+(?:care|services?)",
        r"^chiropractic",
        r"^acupuncture",
        r"^telehealth",
        r"^telemedicine",
        r"^virtual\s+(?:visit|care)",
        # Ambulance / Transport
        r"^ambulance",
        r"^emergency\s+transport",
        # Deductible / OOP sections
        r"^deductible",
        r"^out[- ]?of[- ]?pocket",
        r"^annual\s+(?:deductible|maximum|limit)",
        r"^lifetime\s+(?:maximum|limit)",
        # Special health needs
        r"^if you\s+have\s+(?:mental|behavioral)\s+health",
        r"^special\s+health\s+needs",
        # ADDED: Additional category patterns for SPD documents
        r"^covered\s+(?:services?|benefits?)",
        r"^(?:medical|health)\s+(?:services?|benefits?)",
        r"^summary\s+of\s+(?:benefits?|coverage)",
        r"^benefit\s+(?:schedule|summary)",
        r"^(?:your|plan)\s+(?:benefits?|coverage)",
    ])


@dataclass
class RepeatedHeaderPatterns:
    """Patterns for detecting repeated header rows that should be skipped."""
    
    patterns: List[str] = field(default_factory=lambda: [
        r"^in[- ]?network\s*$",
        r"^out[- ]?of[- ]?network\s*$",
        r"^service\s*$",
        r"^benefit\s*$",
        r"^what you (will )?pay\s*$",
        r"^you pay\s*$",
        r"^member pays\s*$",
        r"^plan pays\s*$",
        r"^covered service\s*$",
        r"^coverage\s*$",
        r"^description\s*$",
        r"^type\s+of\s+service\s*$",
        r"^limitation\s*$",
        r"^copay\s*$",
        r"^coinsurance\s*$",
        r"^services?\s*$",
        r"^benefits?\s*$",
        r"^your\s+cost\s*$",
        r"^cost\s+sharing\s*$",
    ])


@dataclass
class ValueCellPatterns:
    """Patterns for identifying cells that contain benefit values (not service names)."""
    
    patterns: List[str] = field(default_factory=lambda: [
        # Percentages
        r"\d{1,3}\s*%",
        # Dollar amounts
        r"\$\s*[\d,]+(?:\.\d{2})?",
        # Zero/No charge indicators
        r"no\s+charge",
        r"no\s+cost",
        r"covered\s+in\s+full",
        r"paid\s+in\s+full",
        r"\$\s*0(?:\.00)?(?:\s|$)",
        # Not covered indicators
        r"not\s+covered",
        r"excluded",
        r"^n/?a\s*$",
        r"not\s+applicable",
        r"does\s+not\s+apply",
        # Deductible mentions
        r"(?:after|subject\s+to)\s+(?:the\s+)?deductible",
        r"deductible\s+(?:waived|applies)",
        # Placeholders
        r"^\s*-\s*$",
        r"^\s*—\s*$",
        r"included",
        r"see\s+(?:plan|benefit|note)",
        # Copay with unit
        r"\$\s*\d+\s*/\s*(?:visit|day|admission|script|rx)",
        r"\$\s*\d+\s+per\s+(?:visit|day|admission)",
        # Combined values
        r"\d+%\s*(?:after|subject)\s+(?:to\s+)?ded",
        r"\$\d+\s*\+\s*\d+%",
        # Limits in value cells
        r"\d+\s+(?:visits?|days?)\s+(?:per|/)\s*year",
    ])


@dataclass
class BenefitValuePatterns:
    """Regex patterns for extracting benefit values from text."""
    
    # Coinsurance patterns (e.g., "80%", "80% after deductible")
    coinsurance: List[str] = field(default_factory=lambda: [
        r'(\d{1,3})\s*%\s*(?:after\s+(?:(?:in-?network|out-?of-?network)\s+)?deductible)?',
        r'plan\s+pays\s+(\d{1,3})\s*%',
        r'(\d{1,3})\s*%\s+co-?insurance',
        r'you\s+pay\s+(\d{1,3})\s*%',
    ])
    
    # Copay patterns (e.g., "$20", "$20 copay", "$20/visit")
    copay: List[str] = field(default_factory=lambda: [
        r'\$\s*(\d{1,4}(?:,\d{3})*(?:\.\d{2})?)\s*(?:co-?pay|per\s+visit|/\s*visit)?',
        r'(\d{1,4}(?:,\d{3})*(?:\.\d{2})?)\s*(?:dollar|usd)\s*co-?pay',
    ])
    
    # Deductible patterns (e.g., "$1,500", "$1,500/$3,000")
    deductible: List[str] = field(default_factory=lambda: [
        r'\$\s*(\d{1,6}(?:,\d{3})*(?:\.\d{2})?)',
        r'(\d{1,6}(?:,\d{3})*)\s*(?:individual|single|per\s+person)',
        r'(\d{1,6}(?:,\d{3})*)\s*/\s*(\d{1,6}(?:,\d{3})*)\s*(?:family)?',
    ])
    
    # Not covered patterns
    not_covered: List[str] = field(default_factory=lambda: [
        r'not?\s+covered',
        r'no\s+(?:benefit|coverage)',
        r'excluded',
        r'n/?a',
        r'does\s+not\s+apply',
    ])
    
    # Covered in full patterns  
    covered_in_full: List[str] = field(default_factory=lambda: [
        r'(?:covered\s+in\s+full|100\s*%|no\s+charge|no\s+cost)',
        r'fully\s+covered',
        r'\$\s*0',
    ])
    
    # After deductible indicators
    after_deductible: List[str] = field(default_factory=lambda: [
        r'after\s+(?:(?:in-?network|out-?of-?network|annual|plan)\s+)?deductible',
        r'subject\s+to\s+deductible',
        r'deductible\s+applies',
        r'ded(?:uctible)?\s+waived',  # Negative - means NOT after deductible
    ])
    
    # Pre-authorization patterns
    preauth: List[str] = field(default_factory=lambda: [
        r'pre-?(?:certification|authorization|auth)\s+required',
        r'prior\s+(?:authorization|approval)\s+required',
        r'requires?\s+pre-?(?:cert|auth)',
        r'\*+\s*(?:pre-?cert|prior\s+auth)',
    ])
    
    # Limit patterns (e.g., "60 visits per year", "$5,000 maximum")
    limits: List[str] = field(default_factory=lambda: [
        r'(\d+)\s+(?:visits?|days?|treatments?)\s+(?:per|each|/)\s*(?:year|calendar\s+year|benefit\s+year|lifetime)',
        r'\$\s*(\d{1,7}(?:,\d{3})*)\s+(?:maximum|max|limit)\s+(?:per|each|/)\s*(?:year|lifetime)',
        r'(?:maximum|max|limit(?:ed)?)\s+(?:of|to)?\s*(\d+)\s+(?:visits?|days?)',
        r'up\s+to\s+(\d+)\s+(?:visits?|days?|treatments?)',
    ])


@dataclass  
class ColumnDetectionPatterns:
    """Patterns for detecting column types in tables by content analysis."""
    
    # In-Network column indicators (check cell content)
    in_network_content: List[str] = field(default_factory=lambda: [
        r'in-?network',
        r'participating',
        r'preferred\s+provider',
        r'ppo',
        r'tier\s*1',
        r'in\s+network',
    ])
    
    # Out-of-Network column indicators
    out_network_content: List[str] = field(default_factory=lambda: [
        r'out-?of-?network',
        r'non-?participating',
        r'non-?preferred',
        r'non-?network',
        r'oon',
        r'tier\s*2',
        r'out\s+of\s+network',
    ])
    
    # Service/Benefit name column indicators
    service_content: List[str] = field(default_factory=lambda: [
        r'service|benefit|coverage|what\s+is\s+covered',
        r'covered\s+service',
        r'type\s+of\s+(?:service|benefit|care)',
        r'medical\s+service',
    ])
    
    # Header row indicators
    header_indicators: List[str] = field(default_factory=lambda: [
        r'you\s+pay',
        r'plan\s+pays',
        r'member\s+(?:cost|responsibility)',
        r'in-?network|out-?of-?network',
        r'what\s+you\s+(?:pay|owe)',
        r'your\s+cost',
        r'benefit\s+description',
    ])


@dataclass
class ServiceCategoryMappings:
    """Mappings for normalizing service categories."""
    
    # Map various terms to standardized categories
    category_mappings: Dict[str, List[str]] = field(default_factory=lambda: {
        "Deductibles & Out-of-Pocket": [
            r'deductible', r'out-?of-?pocket', r'oop', r'maximum',
        ],
        "Preventive Care": [
            r'preventive', r'wellness', r'routine\s+(?:physical|exam|checkup)',
            r'immunization', r'vaccination', r'screening',
        ],
        "Primary Care": [
            r'primary\s+care', r'pcp', r'office\s+visit', r'physician\s+visit',
            r'doctor\s+visit',
        ],
        "Specialist Services": [
            r'specialist', r'referral', r'consultation',
        ],
        "Emergency Services": [
            r'emergency', r'er\s+', r'urgent\s+care', r'ambulance',
        ],
        "Hospital - Inpatient": [
            r'inpatient', r'hospital\s+(?:stay|admission|room)',
            r'room\s+and\s+board',
        ],
        "Hospital - Outpatient": [
            r'outpatient', r'ambulatory', r'same\s*day\s+surgery',
            r'day\s+surgery',
        ],
        "Surgery": [
            r'surgery', r'surgical', r'operation', r'procedure',
        ],
        "Mental Health": [
            r'mental\s+health', r'behavioral\s+health', r'psychiatr',
            r'psycholog', r'counseling', r'therapy\s+(?:session)?',
        ],
        "Substance Abuse": [
            r'substance\s+(?:abuse|use)', r'chemical\s+dependency',
            r'addiction', r'detox',
        ],
        "Maternity": [
            r'maternity', r'pregnancy', r'prenatal', r'postnatal',
            r'delivery', r'childbirth', r'newborn',
        ],
        "Prescription Drugs": [
            r'prescription', r'pharmacy', r'drug', r'medication',
            r'generic', r'brand', r'formulary', r'rx',
        ],
        "Rehabilitation": [
            r'rehab', r'physical\s+therapy', r'occupational\s+therapy',
            r'speech\s+therapy', r'cardiac\s+rehab',
        ],
        "Lab & Diagnostics": [
            r'lab(?:oratory)?', r'diagnostic', r'blood\s+work', r'pathology',
        ],
        "Imaging": [
            r'imaging', r'x-?ray', r'mri', r'ct\s+scan', r'pet\s+scan',
            r'ultrasound', r'mammogram', r'radiology',
        ],
        "Skilled Nursing": [
            r'skilled\s+nursing', r'snf', r'extended\s+care',
        ],
        "Home Health": [
            r'home\s+health', r'home\s+care', r'visiting\s+nurse',
        ],
        "Hospice": [
            r'hospice', r'palliative',
        ],
        "Durable Medical Equipment": [
            r'durable\s+medical', r'dme', r'equipment', r'prosthetic',
            r'orthotics', r'wheelchair', r'oxygen',
        ],
        "Vision": [
            r'vision', r'eye\s+exam', r'glasses', r'contacts', r'optical',
        ],
        "Dental": [
            r'dental', r'oral', r'teeth', r'orthodontic',
        ],
        "Hearing": [
            r'hearing', r'audiolog', r'hearing\s+aid',
        ],
        "Chiropractic": [
            r'chiropractic', r'spinal\s+manipulation',
        ],
        "Acupuncture": [
            r'acupuncture', r'alternative\s+medicine',
        ],
        "Dialysis": [
            r'dialysis', r'renal', r'kidney',
        ],
        "Transplant": [
            r'transplant', r'organ',
        ],
        "Chemotherapy": [
            r'chemotherapy', r'chemo', r'oncolog', r'cancer\s+treatment',
        ],
        "Radiation": [
            r'radiation', r'radiotherapy',
        ],
        "Allergy": [
            r'allergy', r'allerg', r'immunotherapy',
        ],
    })


@dataclass
class ExtractionConfig:
    """Main configuration container for extraction settings."""
    
    thresholds: ConfidenceThresholds = field(default_factory=ConfidenceThresholds)
    value_patterns: BenefitValuePatterns = field(default_factory=BenefitValuePatterns)
    column_patterns: ColumnDetectionPatterns = field(default_factory=ColumnDetectionPatterns)
    category_mappings: ServiceCategoryMappings = field(default_factory=ServiceCategoryMappings)
    
    # Table structure detection patterns
    table_header_patterns: TableHeaderPatterns = field(default_factory=TableHeaderPatterns)
    category_detection_patterns: CategoryDetectionPatterns = field(default_factory=CategoryDetectionPatterns)
    repeated_header_patterns: RepeatedHeaderPatterns = field(default_factory=RepeatedHeaderPatterns)
    value_cell_patterns: ValueCellPatterns = field(default_factory=ValueCellPatterns)
    
    # Minimum cells in a row to be considered a benefit row
    min_cells_benefit_row: int = 2
    
    # Maximum cells in a row (beyond this, likely not a benefit table)
    max_cells_benefit_row: int = 10
    
    # Minimum rows in a table to process
    min_table_rows: int = 2
    
    # Minimum percentage of cells that must have values to be a benefit table
    min_value_density: float = 0.30
    
    # Maximum rows to check for header
    max_header_search_rows: int = 5
    
    # Enable multi-row header detection
    enable_multi_row_headers: bool = True
    
    def compile_patterns(self) -> 'CompiledPatterns':
        """Compile all regex patterns for efficient matching."""
        return CompiledPatterns(self)
    
    @classmethod
    def load_from_json(cls, json_path: str) -> 'ExtractionConfig':
        """
        Load configuration from JSON file.
        
        Allows overriding defaults with external configuration.
        """
        config = cls()
        
        try:
            path = Path(json_path)
            if not path.exists():
                logger.warning(f"Config file not found: {json_path}, using defaults")
                return config
            
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # Override patterns if present in JSON
            if 'table_header_patterns' in data:
                for key, patterns in data['table_header_patterns'].items():
                    if hasattr(config.table_header_patterns, key):
                        setattr(config.table_header_patterns, key, patterns)
            
            if 'category_detection_patterns' in data:
                config.category_detection_patterns.patterns = data['category_detection_patterns']
            
            if 'repeated_header_patterns' in data:
                config.repeated_header_patterns.patterns = data['repeated_header_patterns']
            
            if 'value_cell_patterns' in data:
                config.value_cell_patterns.patterns = data['value_cell_patterns']
            
            logger.info(f"Loaded extraction config from {json_path}")
            
        except Exception as e:
            logger.warning(f"Failed to load config from {json_path}: {e}, using defaults")
        
        return config


@dataclass
class CompiledPatterns:
    """Pre-compiled regex patterns for performance."""
    
    def __init__(self, config: ExtractionConfig):
        # Value extraction patterns
        self.coinsurance = [re.compile(p, re.IGNORECASE) for p in config.value_patterns.coinsurance]
        self.copay = [re.compile(p, re.IGNORECASE) for p in config.value_patterns.copay]
        self.deductible = [re.compile(p, re.IGNORECASE) for p in config.value_patterns.deductible]
        self.not_covered = [re.compile(p, re.IGNORECASE) for p in config.value_patterns.not_covered]
        self.covered_in_full = [re.compile(p, re.IGNORECASE) for p in config.value_patterns.covered_in_full]
        self.after_deductible = [re.compile(p, re.IGNORECASE) for p in config.value_patterns.after_deductible]
        self.preauth = [re.compile(p, re.IGNORECASE) for p in config.value_patterns.preauth]
        self.limits = [re.compile(p, re.IGNORECASE) for p in config.value_patterns.limits]
        
        # Column detection patterns
        self.in_network_content = [re.compile(p, re.IGNORECASE) for p in config.column_patterns.in_network_content]
        self.out_network_content = [re.compile(p, re.IGNORECASE) for p in config.column_patterns.out_network_content]
        self.service_content = [re.compile(p, re.IGNORECASE) for p in config.column_patterns.service_content]
        self.header_indicators = [re.compile(p, re.IGNORECASE) for p in config.column_patterns.header_indicators]
        
        # Table header patterns (by role)
        self.table_headers: Dict[str, List[Pattern]] = {}
        header_patterns = config.table_header_patterns
        for role in ['service_name', 'in_network_value', 'out_of_network_value', 
                     'in_network_copay', 'out_of_network_copay', 'limitations', 
                     'preauth', 'notes']:
            patterns = getattr(header_patterns, role, [])
            self.table_headers[role] = [
                re.compile(p, re.IGNORECASE) if p.startswith('^') or '\\' in p 
                else re.compile(re.escape(p), re.IGNORECASE)
                for p in patterns
            ]
        
        # Category detection patterns
        self.category_patterns_list = [
            re.compile(p, re.IGNORECASE) 
            for p in config.category_detection_patterns.patterns
        ]
        
        # Repeated header patterns
        self.repeated_header_patterns = [
            re.compile(p, re.IGNORECASE) 
            for p in config.repeated_header_patterns.patterns
        ]
        
        # Value cell patterns
        self.value_cell_patterns = [
            re.compile(p, re.IGNORECASE) 
            for p in config.value_cell_patterns.patterns
        ]
        
        # Compile category mappings
        self.category_mappings: Dict[str, List[Pattern]] = {}
        for category, patterns in config.category_mappings.category_mappings.items():
            self.category_mappings[category] = [re.compile(p, re.IGNORECASE) for p in patterns]
    
    @property
    def category_patterns(self) -> Dict[str, List[Pattern]]:
        """Alias for category_mappings for backward compatibility."""
        return self.category_mappings


# Default configuration instance
DEFAULT_CONFIG = ExtractionConfig()
