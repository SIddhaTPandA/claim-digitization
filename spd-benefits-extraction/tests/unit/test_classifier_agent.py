"""
Unit tests for the Classifier Agent.
"""

import unittest
import sys
import os

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from src.agents.classifier_agent import ClassifierAgent
from src.models.benefit_record import DocumentType


class TestClassifierAgent(unittest.TestCase):
    """Tests for ClassifierAgent class."""

    def setUp(self):
        self.classifier_agent = ClassifierAgent()

    def test_classify_document_valid(self):
        """Test with a valid document input."""
        document = "Sample document content for classification."
        result = self.classifier_agent.classify(document)
        self.assertIn(result, ["Type A", "Type B", "Type C"])

    def test_classify_document_empty(self):
        """Test with an empty document input."""
        document = ""
        with self.assertRaises(ValueError):
            self.classifier_agent.classify(document)

    def test_classify_document_invalid(self):
        """Test with an invalid (None) document input."""
        document = None
        with self.assertRaises(TypeError):
            self.classifier_agent.classify(document)

    def test_classify_spd_document(self):
        """Test classification of SPD document."""
        document = "This is a Summary Plan Description (SPD) for your health benefits."
        result = self.classifier_agent.classify(document)
        self.assertEqual(result, "Type A")  # SPD maps to Type A

    def test_classify_sbc_document(self):
        """Test classification of SBC document."""
        document = "Summary of Benefits and Coverage: What this Plan Covers"
        result = self.classifier_agent.classify(document)
        self.assertEqual(result, "Type B")  # SBC maps to Type B

    def test_classify_full_document(self):
        """Test full document classification with DocumentClassification result."""
        classification = self.classifier_agent.classify_document(
            document_id="test-001",
            document_content="Summary Plan Description for Health Benefits Plan",
            total_pages=25,
        )
        self.assertEqual(classification.document_id, "test-001")
        self.assertEqual(classification.document_type, DocumentType.SPD)
        self.assertEqual(classification.total_pages, 25)

    def test_detect_network_tiers(self):
        """Test network tier detection."""
        content = "Benefits are provided at In-Network and Out-of-Network levels."
        tiers = self.classifier_agent._detect_network_tiers(content)
        self.assertIn("In-Network", tiers)
        self.assertIn("Out-of-Network", tiers)

    def test_extract_plan_name(self):
        """Test plan name extraction."""
        content = "Plan Name: Acme Health Insurance Plan\nEffective Date: 2024"
        plan_name = self.classifier_agent._extract_plan_name(content)
        self.assertIsNotNone(plan_name)
        self.assertIn("Acme", plan_name)

    def test_preprocess_document(self):
        """Test document preprocessing."""
        raw = "  Multiple   Spaces   and\nNewlines  "
        processed = self.classifier_agent.preprocess_document(raw)
        self.assertNotIn("\n", processed)
        self.assertNotIn("  ", processed)


if __name__ == '__main__':
    unittest.main()