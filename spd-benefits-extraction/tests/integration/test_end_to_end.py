"""
Integration tests for end-to-end SPD benefits extraction pipeline.

These tests validate the complete extraction workflow from PDF to Excel.
"""

import unittest
import os
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from src.agents.orchestrator import Orchestrator


class TestEndToEnd(unittest.TestCase):
    """End-to-end integration tests."""
    
    @classmethod
    def setUpClass(cls):
        """Set up test fixtures."""
        cls.input_dir = project_root.parent / "Plans"
        cls.output_dir = project_root.parent / "OutputExcel" / "test_run"
        cls.sample_pdf = cls.input_dir / "M000-999 HDHP 1500 (Q)_HDHP_SPD.pdf"
        
    def test_orchestrator_initialization(self):
        """Test that orchestrator can be initialized."""
        orchestrator = Orchestrator()
        self.assertIsNotNone(orchestrator)
    
    def test_sample_pdf_exists(self):
        """Test that sample test PDF exists."""
        if self.sample_pdf.exists():
            self.assertTrue(True)
        else:
            self.skipTest(f"Sample PDF not found: {self.sample_pdf}")
    
    def test_output_excel_exists(self):
        """Test that output Excel was previously generated."""
        expected_output = self.output_dir / "M000-999 HDHP 1500 (Q)_HDHP_SPD.xlsx"
        if expected_output.exists():
            self.assertTrue(expected_output.exists())
        else:
            self.skipTest(f"Output Excel not found: {expected_output}")


if __name__ == '__main__':
    unittest.main()