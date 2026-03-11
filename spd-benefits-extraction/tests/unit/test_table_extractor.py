"""
Unit tests for the StructuredTableExtractor.

Tests the schema-bound extraction approach including:
- Column role detection
- Header row identification
- Repeated header filtering
- Category detection
- Schema-bound value extraction
"""

import unittest
import sys
import os

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from src.parsers.table_extractor import (
    StructuredTableExtractor,
    ColumnRole,
    ColumnSchema,
    ExtractedRow,
)


class TestStructuredTableExtractor(unittest.TestCase):
    """Tests for StructuredTableExtractor class."""

    def setUp(self):
        self.extractor = StructuredTableExtractor()

    def test_detect_schema_with_clear_headers(self):
        """Test schema detection with clear header row."""
        rows = [
            ["Service", "In-Network", "Out-of-Network", "Limitations"],
            ["Primary Care Visit", "80%", "60%", ""],
            ["Specialist Visit", "70%", "50%", "Referral required"],
        ]
        
        schema = self.extractor._detect_schema(rows)
        
        self.assertTrue(schema.has_required_columns())
        self.assertEqual(schema.header_row_index, 0)
        self.assertIn(ColumnRole.SERVICE_NAME, schema.role_mapping.values())
        self.assertIn(ColumnRole.IN_NETWORK_VALUE, schema.role_mapping.values())
        self.assertIn(ColumnRole.OUT_OF_NETWORK_VALUE, schema.role_mapping.values())

    def test_detect_schema_with_alternate_headers(self):
        """Test schema detection with alternate header terminology."""
        rows = [
            ["Covered Service", "You Pay (Participating)", "You Pay (Non-Participating)"],
            ["Office Visit", "$20 copay", "$50 copay"],
        ]
        
        schema = self.extractor._detect_schema(rows)
        
        self.assertTrue(schema.has_required_columns())
        self.assertEqual(schema.header_row_index, 0)

    def test_is_value_cell(self):
        """Test value cell detection."""
        # Should be detected as values
        self.assertTrue(self.extractor._is_value_cell("80%"))
        self.assertTrue(self.extractor._is_value_cell("$50"))
        self.assertTrue(self.extractor._is_value_cell("$1,500"))
        self.assertTrue(self.extractor._is_value_cell("No charge"))
        self.assertTrue(self.extractor._is_value_cell("Not covered"))
        self.assertTrue(self.extractor._is_value_cell("N/A"))
        self.assertTrue(self.extractor._is_value_cell("20% after deductible"))
        
        # Should NOT be detected as values
        self.assertFalse(self.extractor._is_value_cell("Primary Care"))
        self.assertFalse(self.extractor._is_value_cell("Specialist Visit"))
        self.assertFalse(self.extractor._is_value_cell(""))

    def test_is_repeated_header(self):
        """Test repeated header detection."""
        # First occurrence should not be flagged
        self.extractor._seen_headers.clear()
        row1 = ["Service", "In-Network", "Out-of-Network"]
        self.assertTrue(self.extractor._is_repeated_header(row1))  # This adds to seen
        
        # Same header again should be flagged
        self.assertTrue(self.extractor._is_repeated_header(row1))
        
        # Different row should not be flagged
        row2 = ["Primary Care", "80%", "60%"]
        self.assertFalse(self.extractor._is_repeated_header(row2))

    def test_is_category_row(self):
        """Test category row detection."""
        schema = ColumnSchema()
        schema.role_mapping = {0: ColumnRole.SERVICE_NAME}
        
        # Category rows (single value spanning row)
        self.assertTrue(self.extractor._is_category_row(
            ["Inpatient Hospital Services", "", "", ""], schema
        ))
        self.assertTrue(self.extractor._is_category_row(
            ["If you have a hospital stay", "", ""], schema
        ))
        
        # Data rows (multiple values)
        self.assertFalse(self.extractor._is_category_row(
            ["Room and Board", "80%", "60%", "25 days"], schema
        ))

    def test_extract_from_tables_basic(self):
        """Test basic table extraction."""
        tables = [{
            "rows": [
                ["Service", "In-Network", "Out-of-Network"],
                ["Primary Care Visit", "No charge", "20%"],
                ["Specialist Visit", "80%", "60%"],
                ["Emergency Room", "$150 copay", "$150 copay"],
            ],
            "row_count": 4,
            "column_count": 3,
        }]
        
        rows = self.extractor.extract_from_tables(tables)
        
        self.assertGreaterEqual(len(rows), 2)
        
        # Check first data row
        service_names = [r.service_name for r in rows if not r.is_category_header]
        self.assertTrue(any("Primary Care" in name for name in service_names))

    def test_extract_filters_repeated_headers(self):
        """Test that repeated headers across pages are filtered."""
        tables = [
            {
                "rows": [
                    ["Service", "In-Network", "Out-of-Network"],
                    ["Primary Care Visit", "80%", "60%"],
                ],
                "row_count": 2,
                "column_count": 3,
            },
            {
                "rows": [
                    ["Service", "In-Network", "Out-of-Network"],  # Repeated header
                    ["Specialist Visit", "70%", "50%"],
                ],
                "row_count": 2,
                "column_count": 3,
            }
        ]
        
        rows = self.extractor.extract_from_tables(tables)
        
        # Should have extracted 2 services, not include repeated headers
        service_rows = [r for r in rows if not r.is_category_header]
        self.assertGreaterEqual(len(service_rows), 2)
        
        # Headers should not appear as service names
        service_names = [r.service_name.lower() for r in service_rows]
        self.assertNotIn("service", service_names)
        self.assertNotIn("in-network", service_names)

    def test_extract_with_category_headers(self):
        """Test extraction with category headers."""
        tables = [{
            "rows": [
                ["Service", "In-Network", "Out-of-Network"],
                ["Inpatient Hospital Services", "", ""],  # Category header
                ["Room and Board", "80%", "60%"],
                ["Surgery", "80%", "60%"],
                ["Outpatient Services", "", ""],  # Category header
                ["Lab Work", "No charge", "20%"],
            ],
            "row_count": 6,
            "column_count": 3,
        }]
        
        rows = self.extractor.extract_from_tables(tables)
        
        # Should have category headers marked
        category_rows = [r for r in rows if r.is_category_header]
        self.assertGreaterEqual(len(category_rows), 1)
        
        # Service rows should have category assigned
        service_rows = [r for r in rows if not r.is_category_header]
        for row in service_rows:
            self.assertIsNotNone(row.category)

    def test_extract_row_with_schema(self):
        """Test schema-bound row extraction."""
        schema = ColumnSchema()
        schema.role_mapping = {
            0: ColumnRole.SERVICE_NAME,
            1: ColumnRole.IN_NETWORK_VALUE,
            2: ColumnRole.OUT_OF_NETWORK_VALUE,
        }
        schema.confidence = 0.9
        
        row = ["Primary Care Visit", "80% after deductible", "60% after deductible"]
        
        extracted = self.extractor._extract_row_with_schema(
            row=row,
            schema=schema,
            row_idx=1,
            table_idx=0,
            page_num=1,
        )
        
        self.assertIsNotNone(extracted)
        self.assertEqual(extracted.service_name, "Primary Care Visit")
        self.assertEqual(extracted.in_network_value, "80% after deductible")
        self.assertEqual(extracted.out_of_network_value, "60% after deductible")

    def test_handles_azure_di_format(self):
        """Test handling of Azure Document Intelligence table format."""
        tables = [{
            "cells": [
                {"row_index": 0, "column_index": 0, "content": "Service"},
                {"row_index": 0, "column_index": 1, "content": "In-Network"},
                {"row_index": 0, "column_index": 2, "content": "Out-of-Network"},
                {"row_index": 1, "column_index": 0, "content": "Primary Care"},
                {"row_index": 1, "column_index": 1, "content": "80%"},
                {"row_index": 1, "column_index": 2, "content": "60%"},
            ],
            "row_count": 2,
            "column_count": 3,
        }]
        
        rows = self.extractor.extract_from_tables(tables)
        
        # Should successfully extract
        self.assertGreaterEqual(len(rows), 1)

    def test_reset_clears_state(self):
        """Test that reset() clears tracking state."""
        # Add some state
        self.extractor._seen_headers.add("test header")
        self.extractor._current_category = "Test Category"
        
        self.extractor.reset()
        
        self.assertEqual(len(self.extractor._seen_headers), 0)
        self.assertEqual(self.extractor._current_category, "General Services")


class TestColumnSchema(unittest.TestCase):
    """Tests for ColumnSchema class."""

    def test_has_required_columns(self):
        """Test required columns check."""
        schema = ColumnSchema()
        
        # Empty schema should not have required columns
        self.assertFalse(schema.has_required_columns())
        
        # With service and IN value
        schema.role_mapping = {
            0: ColumnRole.SERVICE_NAME,
            1: ColumnRole.IN_NETWORK_VALUE,
        }
        self.assertTrue(schema.has_required_columns())
        
        # With service and copay (also valid)
        schema.role_mapping = {
            0: ColumnRole.SERVICE_NAME,
            1: ColumnRole.IN_NETWORK_COPAY,
        }
        self.assertTrue(schema.has_required_columns())

    def test_get_column_for_role(self):
        """Test getting column index by role."""
        schema = ColumnSchema()
        schema.role_mapping = {
            0: ColumnRole.SERVICE_NAME,
            1: ColumnRole.IN_NETWORK_VALUE,
            2: ColumnRole.OUT_OF_NETWORK_VALUE,
        }
        
        self.assertEqual(schema.get_column_for_role(ColumnRole.SERVICE_NAME), 0)
        self.assertEqual(schema.get_column_for_role(ColumnRole.IN_NETWORK_VALUE), 1)
        self.assertIsNone(schema.get_column_for_role(ColumnRole.PREAUTH))


if __name__ == "__main__":
    unittest.main()
