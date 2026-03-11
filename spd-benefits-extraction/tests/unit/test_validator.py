"""
Unit tests for deterministic validator and confidence scorer.
"""

import unittest
import sys
import os

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from src.validators.deterministic_validator import DeterministicValidator
from src.validators.confidence_scorer import ConfidenceScorer
from src.models.benefit_record import BenefitRecord, RawExtractionRecord


class TestDeterministicValidator(unittest.TestCase):
    """Tests for DeterministicValidator class."""

    def setUp(self):
        self.validator = DeterministicValidator()

    def test_validation_success_with_valid_record(self):
        """Test validation passes for a valid BenefitRecord."""
        record = BenefitRecord(
            header="Inpatient Hospital Services",
            service="Room and Board",
            in_network_coinsurance="80%",
            in_network_after_deductible="Yes",
            out_of_network_coinsurance="60%",
            out_of_network_after_deductible="Yes",
        )
        issues = self.validator.validate_benefit_record(record)
        error_issues = [i for i in issues if i.severity == "error"]
        self.assertEqual(len(error_issues), 0)

    def test_validation_failure_missing_header(self):
        """Test validation fails when header is missing."""
        # This should raise validation error during construction
        with self.assertRaises(Exception):
            BenefitRecord(
                header="",  # Empty header
                service="Room and Board",
            )

    def test_validation_coinsurance_format(self):
        """Test coinsurance format validation."""
        # Valid coinsurance
        record = BenefitRecord(
            header="Test",
            service="Test Service",
            in_network_coinsurance="80%",
        )
        issues = self.validator.validate_benefit_record(record)
        coinsurance_errors = [i for i in issues if i.field_name == "in_network_coinsurance" and i.severity == "error"]
        self.assertEqual(len(coinsurance_errors), 0)

    def test_validation_copay_format(self):
        """Test copay format validation."""
        record = BenefitRecord(
            header="Test",
            service="Test Service",
            in_network_copay="$20",
        )
        issues = self.validator.validate_benefit_record(record)
        copay_errors = [i for i in issues if i.field_name == "in_network_copay" and i.severity == "error"]
        self.assertEqual(len(copay_errors), 0)

    def test_validation_deductible_consistency(self):
        """Test family >= individual deductible validation."""
        record = BenefitRecord(
            header="Deductible",
            service="Annual Deductible",
            individual_in_network="$500",
            family_in_network="$1,000",  # Family > Individual (valid)
        )
        issues = self.validator.validate_benefit_record(record)
        # Should not have logical errors
        logical_errors = [i for i in issues if i.issue_type == "logical_error"]
        self.assertEqual(len(logical_errors), 0)

    def test_validation_batch(self):
        """Test batch validation of multiple records."""
        records = [
            BenefitRecord(
                header="Inpatient Services",
                service="Room and Board",
                in_network_coinsurance="80%",
            ),
            BenefitRecord(
                header="Outpatient Services",
                service="Office Visit",
                in_network_copay="$20",
            ),
        ]
        is_valid, issues = self.validator.validate_batch(records)
        self.assertTrue(is_valid)

    def test_add_custom_rule(self):
        """Test adding custom validation rules."""
        def custom_rule(data):
            return True
        
        self.validator.add_rule(custom_rule)
        self.assertIn(custom_rule, self.validator.rules)

    def test_validate_dict_format(self):
        """Test validation of dictionary data."""
        data = {"header": "Test", "service": "Test Service"}
        is_valid, errors = self.validator.validate(data)
        self.assertTrue(is_valid)

    def test_validate_dict_missing_required(self):
        """Test validation fails for dict missing required fields."""
        data = {"some_field": "value"}  # Missing header/service_category
        is_valid, errors = self.validator.validate(data)
        self.assertFalse(is_valid)


class TestConfidenceScorer(unittest.TestCase):
    """Tests for ConfidenceScorer class."""

    def setUp(self):
        self.scorer = ConfidenceScorer()

    def test_score_calculation_basic(self):
        """Test basic confidence score calculation."""
        extracted_data = {
            "header": "Inpatient Services",
            "service": "Room and Board",
            "in_network_coinsurance": "80%",
            "in_network_text": "80% after deductible",
        }
        score = self.scorer.calculate_score(extracted_data)
        self.assertGreaterEqual(score, 0)
        self.assertLessEqual(score, 1)

    def test_score_calculation_with_ground_truth(self):
        """Test confidence score against ground truth."""
        extracted_data = {
            "header": "Inpatient Services",
            "service": "Room and Board",
            "in_network_coinsurance": "80%",
        }
        ground_truth = {
            "header": "Inpatient Services",
            "service": "Room and Board",
            "in_network_coinsurance": "80%",
        }
        score = self.scorer.calculate_score(extracted_data, ground_truth)
        self.assertEqual(score, 1.0)  # Perfect match

    def test_score_calculation_partial_match(self):
        """Test confidence score with partial match."""
        extracted_data = {
            "header": "Inpatient Services",
            "service": "Room and Board",
            "in_network_coinsurance": "70%",  # Wrong
        }
        ground_truth = {
            "header": "Inpatient Services",
            "service": "Room and Board",
            "in_network_coinsurance": "80%",
        }
        score = self.scorer.calculate_score(extracted_data, ground_truth)
        self.assertLess(score, 1.0)  # Not perfect
        self.assertGreater(score, 0.0)  # Some match

    def test_score_empty_data(self):
        """Test score calculation with empty data."""
        score = self.scorer.calculate_score({})
        self.assertEqual(score, 0.0)

    def test_score_benefit_record(self):
        """Test scoring a BenefitRecord."""
        record = BenefitRecord(
            header="Inpatient Services",
            service="Room and Board",
            in_network_coinsurance="80%",
            in_network_after_deductible="Yes",
            in_network_copay="$20",
            confidence_score=0.9,
            raw_in_network_text="80% after deductible; $20 copay",
        )
        score = self.scorer.score_benefit_record(record)
        self.assertGreaterEqual(score, 0.5)  # Should be reasonably high
        self.assertLessEqual(score, 1.0)

    def test_score_batch(self):
        """Test batch scoring of records."""
        records = [
            BenefitRecord(
                header="Inpatient Services",
                service="Room and Board",
                in_network_coinsurance="80%",
                confidence_score=0.85,
            ),
            BenefitRecord(
                header="Outpatient Services",
                service="Office Visit",
                in_network_copay="$20",
                confidence_score=0.90,
            ),
        ]
        result = self.scorer.score_batch(records)
        self.assertIn("average_score", result)
        self.assertIn("min_score", result)
        self.assertIn("max_score", result)
        self.assertGreater(result["average_score"], 0)

    def test_requires_human_review_low_confidence(self):
        """Test human review required for low confidence."""
        requires_review, reasons = self.scorer.requires_human_review(
            overall_confidence=0.5,  # Below threshold
        )
        self.assertTrue(requires_review)
        self.assertTrue(len(reasons) > 0)

    def test_requires_human_review_high_confidence(self):
        """Test human review not required for high confidence."""
        requires_review, reasons = self.scorer.requires_human_review(
            overall_confidence=0.85,  # Above threshold
        )
        self.assertFalse(requires_review)

    def test_custom_threshold(self):
        """Test custom confidence threshold."""
        custom_scorer = ConfidenceScorer(threshold=0.80)
        self.assertEqual(custom_scorer.threshold, 0.80)
        
        requires_review, _ = custom_scorer.requires_human_review(
            overall_confidence=0.75,  # Below custom threshold
        )
        self.assertTrue(requires_review)


if __name__ == '__main__':
    unittest.main()