"""
Orchestrator for SPD Benefits Extraction Pipeline.

Coordinates the full extraction workflow:
1. PDF Processing (Document Intelligence)
2. Classification (Document Type, Network Tiers)
3. Extraction (Benefits Data)
4. Normalization (Standardization)
5. Validation (Quality Checks)
6. Excel Generation (Output)
"""

import logging
import os
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from src.agents.classifier_agent import ClassifierAgent
from src.agents.extractor_agent import ExtractorAgent
from src.agents.normalizer_agent import NormalizerAgent
from src.document_intelligence.pdf_processor import PDFProcessor
from src.generators.excel_generator import ExcelGenerator
from src.models.benefit_record import (
    BenefitRecord,
    DocumentClassification,
    DocumentType,
    ExtractionMetadata,
    ExtractionResult,
    RawExtractionRecord,
    ValidationIssue,
)
from src.validators.confidence_scorer import ConfidenceScorer
from src.validators.deterministic_validator import DeterministicValidator

logger = logging.getLogger(__name__)


@dataclass
class ProcessingResult:
    """Result of processing a single document."""
    
    source_file: str
    output_file: Optional[str]
    success: bool
    records_extracted: int
    overall_confidence: float
    requires_review: bool
    error_message: Optional[str] = None
    validation_issues: int = 0


class Orchestrator:
    """
    Main orchestrator for SPD Benefits extraction pipeline.
    
    Coordinates all agents and services to process PDF documents
    and generate standardized Excel output.
    """

    def __init__(
        self,
        output_dir: str = "OutputExcel",
        confidence_threshold: float = 0.70,
        enable_validation: bool = True,
    ):
        """
        Initialize the orchestrator.
        
        Args:
            output_dir: Directory for Excel output files
            confidence_threshold: Minimum confidence for auto-approval
            enable_validation: Whether to run validation checks
        """
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        self.confidence_threshold = confidence_threshold
        self.enable_validation = enable_validation
        
        # Initialize agents
        self.pdf_processor = PDFProcessor()
        self.classifier_agent = ClassifierAgent()
        self.extractor_agent = ExtractorAgent()
        self.normalizer_agent = NormalizerAgent()
        
        # Initialize validators
        self.validator = DeterministicValidator()
        self.confidence_scorer = ConfidenceScorer()
        
        logger.info(
            f"Orchestrator initialized. Output dir: {self.output_dir}, "
            f"Confidence threshold: {self.confidence_threshold:.0%}"
        )

    def process_document(
        self,
        pdf_path: str,
        output_filename: Optional[str] = None,
    ) -> ProcessingResult:
        """
        Process a single PDF document through the full pipeline.
        
        Args:
            pdf_path: Path to the input PDF file
            output_filename: Optional custom output filename
            
        Returns:
            ProcessingResult with status and details
        """
        pdf_path = Path(pdf_path)
        source_name = pdf_path.stem
        document_id = str(uuid.uuid4())
        
        logger.info(f"Processing document: {pdf_path.name}")
        
        try:
            # Step 1: Extract content from PDF
            logger.info("Step 1: Extracting PDF content...")
            pdf_content = self.pdf_processor.extract_content(str(pdf_path))
            
            if not pdf_content:
                return ProcessingResult(
                    source_file=str(pdf_path),
                    output_file=None,
                    success=False,
                    records_extracted=0,
                    overall_confidence=0.0,
                    requires_review=True,
                    error_message="Failed to extract content from PDF",
                )
            
            text_content = pdf_content.get("text", "")
            tables = pdf_content.get("tables", [])
            page_count = pdf_content.get("page_count", 1)
            
            # Step 2: Classify document
            logger.info("Step 2: Classifying document...")
            classification = self.classifier_agent.classify_document(
                document_id=document_id,
                document_content=text_content,
                total_pages=page_count,
                table_data=tables,
            )
            
            # Step 3: Extract raw benefit data
            logger.info("Step 3: Extracting benefit data...")
            raw_records = self.extractor_agent.extract_from_content(
                document_content=text_content,
                tables=tables,
                classification=classification,
            )
            
            if not raw_records:
                logger.warning(f"No benefits extracted from {pdf_path.name}")
                return ProcessingResult(
                    source_file=str(pdf_path),
                    output_file=None,
                    success=False,
                    records_extracted=0,
                    overall_confidence=0.0,
                    requires_review=True,
                    error_message="No benefit records found in document",
                )
            
            # Step 4: Normalize to standard format
            logger.info("Step 4: Normalizing extracted data...")
            normalized_records = self.normalizer_agent.normalize_batch(raw_records)
            
            # Step 5: Validate and score confidence
            logger.info("Step 5: Validating and scoring...")
            validation_issues: List[ValidationIssue] = []
            
            if self.enable_validation:
                for idx, record in enumerate(normalized_records):
                    issues = self.validator.validate_benefit_record(record)
                    for issue in issues:
                        issue.record_index = idx
                        validation_issues.append(issue)
                    
                    # Score confidence
                    confidence = self.confidence_scorer.score_benefit_record(record)
                    record.confidence_score = confidence
            
            # Calculate overall confidence
            overall_confidence = (
                sum(r.confidence_score for r in normalized_records) / len(normalized_records)
                if normalized_records
                else 0.0
            )
            
            requires_review = overall_confidence < self.confidence_threshold
            
            # Step 6: Generate Excel output
            logger.info("Step 6: Generating Excel output...")
            output_name = output_filename or f"{source_name}.xlsx"
            output_path = self.output_dir / output_name
            
            # Create extraction result
            extraction_result = ExtractionResult(
                document_id=str(uuid.uuid4()),
                source_filename=pdf_path.name,
                classification=classification,
                benefit_records=normalized_records,
                validation_issues=validation_issues,
                overall_confidence=overall_confidence,
                requires_human_review=requires_review,
                metadata=ExtractionMetadata(
                    extraction_timestamp=datetime.now(),
                    processing_time_seconds=0,  # Would track actual time
                    pages_processed=pdf_content.get("page_count", 0),
                    confidence_threshold=self.confidence_threshold,
                ),
            )
            
            # Generate Excel
            excel_generator = ExcelGenerator(str(output_path))
            excel_generator.generate_from_extraction_result(
                extraction_result,
                include_metadata=True,
                include_confidence=True,
            )
            
            logger.info(
                f"Successfully processed {pdf_path.name}: "
                f"{len(normalized_records)} records, "
                f"confidence: {overall_confidence:.0%}"
            )
            
            return ProcessingResult(
                source_file=str(pdf_path),
                output_file=str(output_path),
                success=True,
                records_extracted=len(normalized_records),
                overall_confidence=overall_confidence,
                requires_review=requires_review,
                validation_issues=len(validation_issues),
            )
            
        except Exception as e:
            logger.error(f"Error processing {pdf_path.name}: {str(e)}")
            return ProcessingResult(
                source_file=str(pdf_path),
                output_file=None,
                success=False,
                records_extracted=0,
                overall_confidence=0.0,
                requires_review=True,
                error_message=str(e),
            )

    def process_directory(
        self,
        input_dir: str,
        file_pattern: str = "*.pdf",
    ) -> List[ProcessingResult]:
        """
        Process all PDF files in a directory.
        
        Args:
            input_dir: Directory containing PDF files
            file_pattern: Glob pattern for PDF files
            
        Returns:
            List of ProcessingResult for each file
        """
        input_path = Path(input_dir)
        pdf_files = list(input_path.glob(file_pattern))
        
        logger.info(f"Found {len(pdf_files)} PDF files in {input_dir}")
        
        results = []
        for pdf_file in pdf_files:
            result = self.process_document(str(pdf_file))
            results.append(result)
        
        # Summary
        successful = sum(1 for r in results if r.success)
        total_records = sum(r.records_extracted for r in results)
        
        logger.info(
            f"Processing complete: {successful}/{len(results)} successful, "
            f"{total_records} total records extracted"
        )
        
        return results

    def orchestrate(
        self,
        documents: List[str],
    ) -> List[ProcessingResult]:
        """
        Process multiple documents.
        
        Args:
            documents: List of PDF file paths
            
        Returns:
            List of ProcessingResult for each document
        """
        results = []
        for doc_path in documents:
            result = self.process_document(doc_path)
            results.append(result)
        return results