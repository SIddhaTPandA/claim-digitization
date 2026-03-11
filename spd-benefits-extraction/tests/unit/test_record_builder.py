"""
Unit tests for the SchemaRecordBuilder.

Tests the schema-bound record building including:
- Value parsing
- Record building
- Deduplication
"""

import unittest
import sys
import os

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from src.parsers.record_builder import (
    SchemaRecordBuilder,
    ValueParser,
    RecordDeduplicator,
    ParsedValue,
)
from src.parsers.table_extractor import ExtractedRow


class TestValueParser(unittest.TestCase):
    """Tests for ValueParser class."""

    def test_parse_percentage(self):
        """Test parsing percentage values."""
        result = ValueParser.parse("80%")
        self.assertEqual(result.coinsurance, "80%")
        self.assertFalse(result.after_deductible)

    def test_parse_percentage_with_deductible(self):
        """Test parsing percentage with deductible."""
        result = ValueParser.parse("80% after deductible")
        self.assertEqual(result.coinsurance, "80%")
        self.assertTrue(result.after_deductible)

    def test_parse_copay(self):
        """Test parsing copay values."""
        result = ValueParser.parse("$50 copay")
        self.assertEqual(result.copay, "$50")

    def test_parse_copay_with_unit(self):
        """Test parsing copay with per-unit suffix."""
        result = ValueParser.parse("$250 per day")
        self.assertIn("$250", result.copay)
        self.assertIn("per day", result.copay)

    def test_parse_no_charge(self):
        """Test parsing 'no charge' values."""
        result = ValueParser.parse("No charge")
        self.assertTrue(result.no_charge)
        self.assertEqual(result.coinsurance, "0%")

    def test_parse_not_covered(self):
        """Test parsing 'not covered' values."""
        result = ValueParser.parse("Not covered")
        self.assertTrue(result.not_covered)

    def test_parse_covered_in_full(self):
        """Test parsing 'covered in full'."""
        result = ValueParser.parse("Covered in full")
        self.assertTrue(result.no_charge)

    def test_parse_plan_pays(self):
        """Test parsing 'plan pays' format (should convert)."""
        result = ValueParser.parse("Plan pays 80%")
        # Should convert to patient pays 20%
        self.assertEqual(result.coinsurance, "20%")

    def test_parse_combined_values(self):
        """Test parsing combined copay and coinsurance."""
        result = ValueParser.parse("$20 copay; 80% coinsurance after deductible")
        self.assertEqual(result.copay, "$20")
        self.assertEqual(result.coinsurance, "80%")
        self.assertTrue(result.after_deductible)

    def test_parse_empty_value(self):
        """Test parsing empty/None values."""
        result = ValueParser.parse(None)
        self.assertIsNone(result.coinsurance)
        self.assertIsNone(result.copay)
        self.assertFalse(result.not_covered)

    def test_parse_na(self):
        """Test parsing N/A values."""
        result = ValueParser.parse("N/A")
        self.assertTrue(result.not_covered)


class TestSchemaRecordBuilder(unittest.TestCase):
    """Tests for SchemaRecordBuilder class."""

    def setUp(self):
        self.builder = SchemaRecordBuilder()

    def test_build_from_extracted_rows_basic(self):
        """Test basic record building."""
        rows = [
            ExtractedRow(
                service_name="Primary Care Visit",
                in_network_value="80%",
                out_of_network_value="60%",
                category="Primary Care",
            ),
            ExtractedRow(
                service_name="Specialist Visit",
                in_network_value="70%",
                out_of_network_value="50%",
                category="Specialist Services",
            ),
        ]
        
        records = self.builder.build_from_extracted_rows(rows)
        
        self.assertEqual(len(records), 2)
        self.assertEqual(records[0].service_name, "Primary Care Visit")
        self.assertEqual(records[0].service_category, "Primary Care")

    def test_build_handles_category_headers(self):
        """Test that category headers update context but don't create records."""
        rows = [
            ExtractedRow(
                service_name="Inpatient Services",
                is_category_header=True,
            ),
            ExtractedRow(
                service_name="Room and Board",
                in_network_value="80%",
            ),
        ]
        
        records = self.builder.build_from_extracted_rows(rows)
        
        # Should only have 1 record (not the category header)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].service_name, "Room and Board")
        self.assertEqual(records[0].service_category, "Inpatient Services")

    def test_build_with_copay_values(self):
        """Test building records with copay values."""
        rows = [
            ExtractedRow(
                service_name="Emergency Room",
                in_network_value="80% after deductible",
                in_network_copay="$150",
            ),
        ]
        
        records = self.builder.build_from_extracted_rows(rows)
        
        self.assertEqual(len(records), 1)
        # In-network text should include both copay and coinsurance
        self.assertIn("$150", records[0].in_network_text)

    def test_build_skips_empty_service(self):
        """Test that records with empty service names are skipped."""
        rows = [
            ExtractedRow(service_name="", in_network_value="80%"),
            ExtractedRow(service_name="Valid Service", in_network_value="80%"),
        ]
        
        records = self.builder.build_from_extracted_rows(rows)
        
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].service_name, "Valid Service")

    def test_normalize_preauth(self):
        """Test preauth normalization."""
        self.assertEqual(self.builder._normalize_preauth("Required"), "Required")
        self.assertEqual(self.builder._normalize_preauth("Yes"), "Required")
        self.assertEqual(self.builder._normalize_preauth("May be required"), "May Be Required")
        self.assertEqual(self.builder._normalize_preauth("Not required"), "Not Required")
        self.assertIsNone(self.builder._normalize_preauth(None))


class TestRecordDeduplicator(unittest.TestCase):
    """Tests for RecordDeduplicator class."""

    def setUp(self):
        self.deduplicator = RecordDeduplicator()

    def test_removes_duplicates(self):
        """Test that exact duplicates are removed."""
        from src.models.benefit_record import RawExtractionRecord
        
        records = [
            RawExtractionRecord(
                service_category="Primary Care",
                service_name="Primary Care Visit",
                in_network_text="80%",
            ),
            RawExtractionRecord(
                service_category="Primary Care",
                service_name="Primary Care Visit",  # Duplicate
                in_network_text="80%",
            ),
        ]
        
        result = self.deduplicator.deduplicate(records)
        
        self.assertEqual(len(result), 1)

    def test_keeps_most_complete(self):
        """Test that the most complete record is kept."""
        from src.models.benefit_record import RawExtractionRecord
        
        records = [
            RawExtractionRecord(
                service_category="Primary Care",
                service_name="Primary Care Visit",
                in_network_text="80%",
                # Less complete
            ),
            RawExtractionRecord(
                service_category="Primary Care",
                service_name="Primary Care Visit",
                in_network_text="80%",
                out_of_network_text="60%",  # More complete
                preauth_text="Required",
            ),
        ]
        
        result = self.deduplicator.deduplicate(records)
        
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].out_of_network_text, "60%")

    def test_handles_similar_names(self):
        """Test handling of similar service names with common variations."""
        from src.models.benefit_record import RawExtractionRecord
        
        records = [
            RawExtractionRecord(
                service_category="Primary Care",
                service_name="Primary Care Visit",
                in_network_text="80%",
            ),
            RawExtractionRecord(
                service_category="Primary Care",
                service_name="Primary Care Visits",  # Plural form
                in_network_text="80%",
            ),
        ]
        
        result = self.deduplicator.deduplicate(records)
        
        # Should be treated as duplicates due to normalization
        self.assertEqual(len(result), 1)


if __name__ == "__main__":
    unittest.main()
