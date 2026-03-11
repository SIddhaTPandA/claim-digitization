"""
Unit tests for benefit record models.
"""

import unittest
import sys
import os

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from src.models.benefit_record import (
    BenefitRecord,
    RawExtractionRecord,
    DocumentClassification,
    DocumentType,
    NetworkTier,
    validate_coinsurance,
    validate_copay,
    validate_monetary_amount,
    validate_limit,
)


class TestValidationUtilities(unittest.TestCase):
    """Tests for validation utility functions."""

    def test_validate_coinsurance_percentage(self):
        """Test coinsurance percentage validation."""
        self.assertEqual(validate_coinsurance("80%"), "80%")
        self.assertEqual(validate_coinsurance("100%"), "100%")
        self.assertEqual(validate_coinsurance("0%"), "0%")
        self.assertEqual(validate_coinsurance("80"), "80%")

    def test_validate_coinsurance_not_covered(self):
        """Test NOT COVERED coinsurance value."""
        self.assertEqual(validate_coinsurance("NOT COVERED"), "NOT COVERED")
        self.assertEqual(validate_coinsurance("not covered"), "NOT COVERED")

    def test_validate_coinsurance_na(self):
        """Test N/A coinsurance value."""
        self.assertEqual(validate_coinsurance("N/A"), "N/A")
        self.assertEqual(validate_coinsurance("NA"), "N/A")

    def test_validate_coinsurance_none(self):
        """Test None coinsurance value."""
        self.assertIsNone(validate_coinsurance(None))
        self.assertIsNone(validate_coinsurance(""))

    def test_validate_coinsurance_invalid(self):
        """Test invalid coinsurance raises error."""
        with self.assertRaises(ValueError):
            validate_coinsurance("150%")

    def test_validate_copay_valid(self):
        """Test valid copay formats."""
        self.assertEqual(validate_copay("$20"), "$20")
        self.assertEqual(validate_copay("$350"), "$350")
        self.assertEqual(validate_copay("$1,500"), "$1,500")
        self.assertEqual(validate_copay("$20.00"), "$20.00")

    def test_validate_copay_none(self):
        """Test None copay value."""
        self.assertIsNone(validate_copay(None))
        self.assertIsNone(validate_copay("N/A"))
        self.assertIsNone(validate_copay("None"))

    def test_validate_copay_per_suffix(self):
        """Test copay with per suffix."""
        result = validate_copay("$50 per visit")
        self.assertIn("$50", result)
        self.assertIn("per visit", result)

    def test_validate_monetary_amount_valid(self):
        """Test valid monetary amounts."""
        self.assertEqual(validate_monetary_amount("$500"), "$500")
        self.assertEqual(validate_monetary_amount("$1,500"), "$1,500")
        self.assertEqual(validate_monetary_amount("$6,000"), "$6,000")

    def test_validate_monetary_amount_unlimited(self):
        """Test unlimited monetary amount."""
        self.assertEqual(validate_monetary_amount("Unlimited"), "Unlimited")

    def test_validate_limit_visits(self):
        """Test visit limit validation."""
        self.assertEqual(validate_limit("90 visits"), "90 visits")
        self.assertEqual(validate_limit("1 visit"), "1 visit")
        self.assertEqual(validate_limit("25 days"), "25 days")

    def test_validate_limit_dollar(self):
        """Test dollar limit validation."""
        self.assertEqual(validate_limit("$3,000"), "$3,000")

    def test_validate_limit_unlimited(self):
        """Test unlimited limit."""
        self.assertEqual(validate_limit("Unlimited"), "Unlimited")
        self.assertEqual(validate_limit("No Limit"), "Unlimited")


class TestBenefitRecord(unittest.TestCase):
    """Tests for BenefitRecord model."""

    def test_create_basic_record(self):
        """Test creating a basic benefit record."""
        record = BenefitRecord(
            header="Inpatient Hospital Services",
            service="Room and Board",
        )
        self.assertEqual(record.header, "Inpatient Hospital Services")
        self.assertEqual(record.service, "Room and Board")

    def test_create_full_record(self):
        """Test creating a fully populated record."""
        record = BenefitRecord(
            header="Inpatient Hospital Services",
            service="Room and Board",
            in_network_coinsurance="80%",
            in_network_after_deductible="Yes",
            in_network_copay="$50",
            out_of_network_coinsurance="60%",
            out_of_network_after_deductible="Yes",
            out_of_network_copay="$100",
            limit_type="25 days",
            limit_period="Benefit Year",
            preauth_required="Yes",
            confidence_score=0.92,
            source_page=5,
        )
        self.assertEqual(record.in_network_coinsurance, "80%")
        self.assertEqual(record.out_of_network_coinsurance, "60%")
        self.assertEqual(record.limit_type, "25 days")
        self.assertEqual(record.limit_period, "Benefit Year")

    def test_coinsurance_auto_normalization(self):
        """Test automatic coinsurance normalization."""
        record = BenefitRecord(
            header="Test",
            service="Test Service",
            in_network_coinsurance="80",  # Without %
        )
        self.assertEqual(record.in_network_coinsurance, "80%")

    def test_after_deductible_normalization(self):
        """Test after deductible flag normalization."""
        record = BenefitRecord(
            header="Test",
            service="Test Service",
            in_network_after_deductible="y",  # lowercase y
        )
        self.assertEqual(record.in_network_after_deductible, "Yes")

    def test_preauth_normalization(self):
        """Test preauth required normalization."""
        record = BenefitRecord(
            header="Test",
            service="Test Service",
            preauth_required="required",
        )
        self.assertEqual(record.preauth_required, "Yes")

    def test_to_excel_row(self):
        """Test conversion to Excel row."""
        record = BenefitRecord(
            header="Inpatient Services",
            service="Room and Board",
            in_network_coinsurance="80%",
            in_network_after_deductible="Yes",
        )
        row = record.to_excel_row()
        self.assertEqual(len(row), 15)  # 15-column schema
        self.assertEqual(row[0], "Inpatient Services")
        self.assertEqual(row[1], "Room and Board")
        self.assertEqual(row[2], "80%")
        self.assertEqual(row[3], "Yes")

    def test_get_excel_headers(self):
        """Test getting Excel column headers."""
        headers = BenefitRecord.get_excel_headers()
        self.assertEqual(len(headers), 15)
        self.assertEqual(headers[0], "Header")
        self.assertEqual(headers[1], "Service")
        self.assertIn("In-Network Coinsurance", headers)
        self.assertIn("Pre-Authorization Required", headers)

    def test_confidence_score_bounds(self):
        """Test confidence score must be 0-1."""
        record = BenefitRecord(
            header="Test",
            service="Test Service",
            confidence_score=0.5,
        )
        self.assertEqual(record.confidence_score, 0.5)

    def test_deductible_amounts(self):
        """Test deductible amount fields."""
        record = BenefitRecord(
            header="Deductible",
            service="Annual Deductible",
            individual_in_network="$500",
            family_in_network="1000",  # Without $
        )
        self.assertEqual(record.individual_in_network, "$500")
        self.assertEqual(record.family_in_network, "$1,000")


class TestRawExtractionRecord(unittest.TestCase):
    """Tests for RawExtractionRecord model."""

    def test_create_raw_record(self):
        """Test creating a raw extraction record."""
        record = RawExtractionRecord(
            service_category="Inpatient Hospital Services",
            service_name="Room and Board",
            in_network_text="80% after deductible",
            out_of_network_text="60% after deductible",
            page_number=5,
            raw_confidence=0.92,
        )
        self.assertEqual(record.service_category, "Inpatient Hospital Services")
        self.assertEqual(record.in_network_text, "80% after deductible")

    def test_raw_record_requires_service_category(self):
        """Test that service_category is required."""
        with self.assertRaises(ValueError):
            RawExtractionRecord(
                service_category="",  # Empty
                in_network_text="80%",
            )

    def test_raw_record_with_location_info(self):
        """Test raw record with location metadata."""
        record = RawExtractionRecord(
            service_category="Test",
            page_number=10,
            table_index=2,
            row_index=5,
        )
        self.assertEqual(record.page_number, 10)
        self.assertEqual(record.table_index, 2)
        self.assertEqual(record.row_index, 5)


class TestDocumentClassification(unittest.TestCase):
    """Tests for DocumentClassification model."""

    def test_create_classification(self):
        """Test creating a document classification."""
        classification = DocumentClassification(
            document_id="test-doc-001",
            document_type=DocumentType.SPD,
            total_pages=25,
            plan_name="Test Health Plan",
        )
        self.assertEqual(classification.document_id, "test-doc-001")
        self.assertEqual(classification.document_type, DocumentType.SPD)
        self.assertEqual(classification.total_pages, 25)

    def test_classification_defaults(self):
        """Test default values in classification."""
        classification = DocumentClassification(
            document_id="test-doc",
            document_type=DocumentType.SBC,
            total_pages=10,
        )
        self.assertTrue(classification.is_two_tier)
        self.assertEqual(classification.detected_tiers, ["In-Network", "Out-of-Network"])
        self.assertFalse(classification.requires_ocr)
        self.assertEqual(classification.language, "en")


class TestEnums(unittest.TestCase):
    """Tests for enum types."""

    def test_document_type_values(self):
        """Test DocumentType enum values."""
        self.assertEqual(DocumentType.SPD.value, "SPD")
        self.assertEqual(DocumentType.SBC.value, "SBC")
        self.assertEqual(DocumentType.UNKNOWN.value, "UNKNOWN")

    def test_network_tier_values(self):
        """Test NetworkTier enum values."""
        self.assertEqual(NetworkTier.IN_NETWORK.value, "In-Network")
        self.assertEqual(NetworkTier.OUT_OF_NETWORK.value, "Out-of-Network")


if __name__ == '__main__':
    unittest.main()
