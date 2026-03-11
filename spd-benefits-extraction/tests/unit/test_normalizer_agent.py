"""
Unit tests for the Normalizer Agent.
"""

import unittest
import sys
import os

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from src.agents.normalizer_agent import NormalizerAgent
from src.models.benefit_record import BenefitRecord, RawExtractionRecord


class TestNormalizerAgent(unittest.TestCase):
    """Tests for NormalizerAgent class."""

    def setUp(self):
        self.normalizer = NormalizerAgent()

    def test_normalize_basic_data(self):
        """Test basic normalization of extracted data."""
        input_data = {
            "service_category": "Inpatient Hospital Services",
            "service_name": "Room and Board",
            "in_network_text": "80% after deductible",
            "out_of_network_text": "60% after deductible",
        }
        
        normalized = self.normalizer.normalize(input_data)
        
        self.assertEqual(normalized["header"], "Inpatient Hospital Services")
        # Semantic matching may normalize "Room and Board" to its category
        # The service should be one of these valid values
        self.assertIn(normalized["service"], ["Room And Board", "Inpatient Hospital Services"])
        self.assertEqual(normalized["in_network_coinsurance"], "80%")
        self.assertEqual(normalized["in_network_after_deductible"], "Yes")

    def test_normalize_copay(self):
        """Test copay extraction from benefit text."""
        input_data = {
            "service_category": "Office Visit",
            "in_network_text": "$20 copay",
        }
        
        normalized = self.normalizer.normalize(input_data)
        self.assertEqual(normalized["in_network_copay"], "$20")

    def test_normalize_not_covered(self):
        """Test 'Not Covered' detection."""
        input_data = {
            "service_category": "Cosmetic Surgery",
            "in_network_text": "Not Covered",
        }
        
        normalized = self.normalizer.normalize(input_data)
        self.assertEqual(normalized["in_network_coinsurance"], "NOT COVERED")

    def test_normalize_complex_benefit_text(self):
        """Test parsing complex benefit text with multiple components."""
        input_data = {
            "service_category": "Emergency Room",
            "in_network_text": "80% after deductible; $150 copay per visit",
        }
        
        normalized = self.normalizer.normalize(input_data)
        self.assertEqual(normalized["in_network_coinsurance"], "80%")
        self.assertEqual(normalized["in_network_after_deductible"], "Yes")
        self.assertIn("$150", normalized["in_network_copay"])

    def test_normalize_deductible_waived(self):
        """Test deductible waived detection."""
        input_data = {
            "service_category": "Preventive Care",
            "in_network_text": "100% covered, deductible waived",
        }
        
        normalized = self.normalizer.normalize(input_data)
        self.assertEqual(normalized["in_network_coinsurance"], "100%")
        self.assertEqual(normalized["in_network_after_deductible"], "No")

    def test_normalize_invalid_data_raises(self):
        """Test that invalid data raises ValueError."""
        with self.assertRaises(ValueError):
            self.normalizer.normalize({})

    def test_normalize_missing_service_category_raises(self):
        """Test that missing service category raises ValueError."""
        with self.assertRaises(ValueError):
            self.normalizer.normalize({"in_network_text": "80%"})

    def test_parse_benefit_text_coinsurance_only(self):
        """Test parsing coinsurance-only text."""
        result = self.normalizer.parse_benefit_text("80%")
        self.assertEqual(result["coinsurance"], "80%")
        self.assertIsNone(result["copay"])

    def test_parse_benefit_text_copay_only(self):
        """Test parsing copay-only text."""
        result = self.normalizer.parse_benefit_text("$25 copay")
        self.assertEqual(result["copay"], "$25")
        self.assertIsNone(result["coinsurance"])

    def test_parse_benefit_text_combined(self):
        """Test parsing combined coinsurance and after deductible."""
        result = self.normalizer.parse_benefit_text("80% after deductible")
        self.assertEqual(result["coinsurance"], "80%")
        self.assertEqual(result["after_deductible"], "Yes")

    def test_parse_limit_text(self):
        """Test limit text parsing."""
        limit_type, limit_period = self.normalizer.parse_limit_text(
            "90 visits per calendar year"
        )
        self.assertEqual(limit_type, "90 visits")
        self.assertEqual(limit_period, "Calendar Year")

    def test_parse_limit_text_dollar_amount(self):
        """Test dollar limit parsing."""
        limit_type, limit_period = self.normalizer.parse_limit_text(
            "$3,000 lifetime maximum"
        )
        self.assertEqual(limit_type, "$3,000")
        self.assertEqual(limit_period, "Lifetime")

    def test_parse_preauth_text_required(self):
        """Test pre-authorization required detection."""
        result = self.normalizer.parse_preauth_text("Pre-authorization required")
        self.assertEqual(result, "Yes")

    def test_parse_preauth_text_not_required(self):
        """Test pre-authorization not required detection."""
        result = self.normalizer.parse_preauth_text("Not required")
        self.assertEqual(result, "No")

    def test_normalize_raw_record(self):
        """Test normalizing a RawExtractionRecord to BenefitRecord."""
        raw_record = RawExtractionRecord(
            service_category="Inpatient Hospital Services",
            service_name="Room and Board",
            in_network_text="80% after deductible",
            out_of_network_text="60% after deductible",
            page_number=5,
            raw_confidence=0.92,
        )
        
        benefit_record = self.normalizer.normalize_raw_record(raw_record)
        
        self.assertIsInstance(benefit_record, BenefitRecord)
        self.assertEqual(benefit_record.header, "Inpatient Hospital Services")
        self.assertEqual(benefit_record.in_network_coinsurance, "80%")
        self.assertEqual(benefit_record.in_network_after_deductible, "Yes")
        self.assertEqual(benefit_record.source_page, 5)

    def test_normalize_batch(self):
        """Test batch normalization of multiple records."""
        raw_records = [
            RawExtractionRecord(
                service_category="Inpatient Services",
                in_network_text="80%",
                raw_confidence=0.9,
            ),
            RawExtractionRecord(
                service_category="Outpatient Services",
                in_network_text="$20 copay",
                raw_confidence=0.85,
            ),
        ]
        
        benefit_records = self.normalizer.normalize_batch(raw_records)
        
        self.assertEqual(len(benefit_records), 2)
        self.assertIsInstance(benefit_records[0], BenefitRecord)
        self.assertIsInstance(benefit_records[1], BenefitRecord)

    def test_network_mapping_non_network(self):
        """Test network terminology mapping."""
        # Test the internal method
        result = self.normalizer._normalize_network("Non-Network")
        self.assertEqual(result, "Out-of-Network")

    def test_network_mapping_preferred(self):
        """Test preferred network mapping."""
        result = self.normalizer._normalize_network("Preferred")
        self.assertEqual(result, "In-Network")

    def test_legacy_format_support(self):
        """Test legacy format with benefit_name key."""
        input_data = {
            "benefit_name": "Health Insurance",
            "coverage_amount": "$1000",
            "network": "Tier 1"
        }
        
        normalized = self.normalizer.normalize(input_data)
        
        self.assertEqual(normalized["header"], "Health Insurance")
        self.assertEqual(normalized["coverage_amount"], 1000.0)
        self.assertEqual(normalized["network"], "In-Network")


if __name__ == '__main__':
    unittest.main()