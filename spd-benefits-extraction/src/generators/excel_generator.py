"""
Excel Generator for SPD Benefits Extraction.

Generates standardized 15-column Excel output files from
normalized BenefitRecord data.
"""

import os
from datetime import datetime
from typing import Any, Dict, List, Optional

import pandas as pd
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side

from src.models.benefit_record import BenefitRecord, ExtractionResult


class ExcelGenerator:
    """
    Generates Excel files following the 15-column benefit schema.
    
    Output columns:
    1. Header (Service Category)
    2. Service
    3. In-Network Coinsurance
    4. In-Network After Deductible Flag
    5. In-Network Copay
    6. Out-Of-Network Coinsurance
    7. Out-Of-Network After Deductible Flag
    8. Out-Of-Network Copay
    9. Individual In-Network
    10. Family In-Network
    11. Individual Out-Of-Network
    12. Family Out-Of-Network
    13. Limit Type
    14. Limit Period
    15. Pre-Authorization Required
    """

    # Column headers matching the expected output format
    COLUMN_HEADERS = [
        "Header",
        "Service",
        "In-Network Coinsurance",
        "In-Network After Deductible Flag",
        "In-Network Copay",
        "Out-Of-Network Coinsurance",
        "Out-Of-Network After Deductible Flag",
        "Out-Of-Network Copay",
        "Individual In-Network",
        "Family In-Network",
        "Individual Out-Of-Network",
        "Family Out-Of-Network",
        "Limit Type",
        "Limit Period",
        "Pre-Authorization Required",
    ]

    # Styling
    HEADER_FILL = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
    HEADER_FONT = Font(bold=True, color="FFFFFF", size=11)
    CATEGORY_FILL = PatternFill(start_color="D9E2F3", end_color="D9E2F3", fill_type="solid")
    BORDER = Border(
        left=Side(style="thin"),
        right=Side(style="thin"),
        top=Side(style="thin"),
        bottom=Side(style="thin"),
    )

    def __init__(self, output_path: str):
        """
        Initialize the Excel generator.
        
        Args:
            output_path: Path to the output Excel file
        """
        self.output_path = output_path
        self.workbook: Optional[Workbook] = None

    def generate_excel(self, data: List[Dict[str, Any]]) -> str:
        """
        Generate Excel file from list of dictionaries.
        
        Args:
            data: List of dictionaries with benefit data
            
        Returns:
            Path to the generated Excel file
        """
        df = pd.DataFrame(data)
        
        # Ensure columns are in correct order
        ordered_columns = []
        for col in self.COLUMN_HEADERS:
            if col in df.columns:
                ordered_columns.append(col)
            else:
                # Try to find matching column with different case
                for df_col in df.columns:
                    if df_col.lower().replace("_", " ") == col.lower().replace("_", " "):
                        df = df.rename(columns={df_col: col})
                        ordered_columns.append(col)
                        break
                else:
                    df[col] = None
                    ordered_columns.append(col)
        
        df = df[ordered_columns]
        df.to_excel(self.output_path, index=False, sheet_name="Benefits")
        
        # Apply formatting
        self._apply_formatting()
        
        return self.output_path

    def generate_from_records(
        self,
        records: List[BenefitRecord],
        include_metadata: bool = True,
    ) -> str:
        """
        Generate Excel file from BenefitRecord objects.
        
        Args:
            records: List of BenefitRecord objects
            include_metadata: Whether to add a metadata sheet
            
        Returns:
            Path to the generated Excel file
        """
        # Convert records to rows
        rows = [self._record_to_row(record) for record in records]
        
        # Create DataFrame
        df = pd.DataFrame(rows, columns=self.COLUMN_HEADERS)
        
        # Write to Excel
        with pd.ExcelWriter(self.output_path, engine="openpyxl") as writer:
            df.to_excel(writer, index=False, sheet_name="Benefits")
            
            if include_metadata:
                self._add_metadata_sheet(writer, records)
        
        # Apply formatting
        self._apply_formatting()
        
        return self.output_path

    def generate_from_extraction_result(
        self,
        result: ExtractionResult,
        include_metadata: bool = True,
        include_confidence: bool = False,
    ) -> str:
        """
        Generate Excel file from ExtractionResult.
        
        Args:
            result: ExtractionResult containing benefit records
            include_metadata: Whether to add a metadata sheet
            include_confidence: Whether to add confidence scores column
            
        Returns:
            Path to the generated Excel file
        """
        records = result.benefit_records
        
        # Convert records to rows
        rows = []
        for record in records:
            row = self._record_to_row(record)
            if include_confidence:
                row.append(record.confidence_score)
            rows.append(row)
        
        # Column headers
        headers = self.COLUMN_HEADERS.copy()
        if include_confidence:
            headers.append("Confidence Score")
        
        # Create DataFrame
        df = pd.DataFrame(rows, columns=headers)
        
        # Write to Excel
        with pd.ExcelWriter(self.output_path, engine="openpyxl") as writer:
            df.to_excel(writer, index=False, sheet_name="Benefits")
            
            if include_metadata:
                self._add_extraction_metadata_sheet(writer, result)
        
        # Apply formatting
        self._apply_formatting()
        
        return self.output_path

    def _record_to_row(self, record: BenefitRecord) -> List[Any]:
        """Convert a BenefitRecord to an Excel row."""
        return [
            record.header,
            record.service,
            record.in_network_coinsurance,
            record.in_network_after_deductible,
            record.in_network_copay,
            record.out_of_network_coinsurance,
            record.out_of_network_after_deductible,
            record.out_of_network_copay,
            record.individual_in_network,
            record.family_in_network,
            record.individual_out_of_network,
            record.family_out_of_network,
            record.limit_type,
            record.limit_period,
            record.preauth_required,
        ]

    def _apply_formatting(self) -> None:
        """Apply professional formatting to the Excel file."""
        wb = load_workbook(self.output_path)
        ws = wb.active
        
        # Format header row
        for cell in ws[1]:
            cell.fill = self.HEADER_FILL
            cell.font = self.HEADER_FONT
            cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
            cell.border = self.BORDER
        
        # Format data rows
        current_header = None
        for row_idx in range(2, ws.max_row + 1):
            header_cell = ws.cell(row=row_idx, column=1)
            
            # Apply category highlighting when header changes
            if header_cell.value and header_cell.value != current_header:
                current_header = header_cell.value
                header_cell.fill = self.CATEGORY_FILL
                header_cell.font = Font(bold=True)
            
            # Apply borders and alignment to all cells
            for col_idx in range(1, ws.max_column + 1):
                cell = ws.cell(row=row_idx, column=col_idx)
                cell.border = self.BORDER
                cell.alignment = Alignment(vertical="center", wrap_text=True)
        
        # Auto-fit column widths
        for column in ws.columns:
            max_length = 0
            column_letter = column[0].column_letter
            for cell in column:
                try:
                    if cell.value:
                        max_length = max(max_length, len(str(cell.value)))
                except:
                    pass
            adjusted_width = min(max_length + 2, 40)
            ws.column_dimensions[column_letter].width = adjusted_width
        
        # Freeze header row
        ws.freeze_panes = "A2"
        
        wb.save(self.output_path)

    def _add_metadata_sheet(
        self,
        writer: pd.ExcelWriter,
        records: List[BenefitRecord],
    ) -> None:
        """Add a metadata sheet with processing information."""
        avg_confidence = sum(r.confidence_score for r in records) / len(records) if records else 0
        below_threshold = sum(1 for r in records if r.confidence_score < 0.70)
        
        # Calculate confidence reduction reasons
        confidence_reasons = self._analyze_confidence_reasons(records, avg_confidence)
        
        metadata = {
            "Property": [
                "Generation Date",
                "Total Records",
                "Unique Service Categories",
                "Average Confidence Score",
                "Records Below Threshold",
                "Confidence Notes",
            ],
            "Value": [
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                len(records),
                len(set(r.header for r in records)),
                f"{avg_confidence:.2%}" if records else "N/A",
                below_threshold,
                confidence_reasons,
            ],
        }
        
        df_metadata = pd.DataFrame(metadata)
        df_metadata.to_excel(writer, index=False, sheet_name="Metadata")
    
    def _analyze_confidence_reasons(
        self,
        records: List[BenefitRecord],
        avg_confidence: float,
    ) -> str:
        """
        Analyze why confidence is below 100% and return a one-liner explanation.
        
        Returns:
            Human-readable explanation for confidence reduction
        """
        if not records:
            return "No records extracted"
        
        if avg_confidence >= 0.99:
            return "High confidence - all fields extracted successfully"
        
        reasons = []
        
        # Count missing fields across all records
        total_fields = len(records) * 6  # 6 main value fields per record
        missing_in_network = sum(1 for r in records if r.in_network_coinsurance is None and r.in_network_copay is None)
        missing_out_network = sum(1 for r in records if r.out_of_network_coinsurance is None and r.out_of_network_copay is None)
        missing_limits = sum(1 for r in records if r.limit_type is None)
        
        total_missing = missing_in_network + missing_out_network + missing_limits
        missing_pct = (total_missing / total_fields) * 100 if total_fields > 0 else 0
        
        if missing_pct > 20:
            reasons.append(f"Missing values in {missing_pct:.0f}% of fields")
        elif missing_pct > 5:
            reasons.append(f"Some fields not found ({missing_pct:.0f}%)")
        
        # Check for low confidence records
        low_conf_records = sum(1 for r in records if r.confidence_score < 0.70)
        if low_conf_records > 0:
            reasons.append(f"{low_conf_records} records need review")
        
        # Check for non-standard service names (fuzzy matches)
        fuzzy_services = sum(1 for r in records if r.confidence_score < 0.90 and r.confidence_score >= 0.70)
        if fuzzy_services > len(records) * 0.3:
            reasons.append("Some service names required fuzzy matching")
        
        # Check for missing deductible info
        missing_ded = sum(1 for r in records if r.in_network_after_deductible is None)
        if missing_ded > len(records) * 0.5:
            reasons.append("After-deductible flags not consistently extracted")
        
        if not reasons:
            if avg_confidence >= 0.90:
                return "Minor parsing variations - confidence is acceptable"
            elif avg_confidence >= 0.80:
                return "Some fields have ambiguous source text"
            else:
                return "Document format differs from standard SPD/SBC layout"
        
        return "; ".join(reasons[:3])  # Limit to 3 reasons

    def _add_extraction_metadata_sheet(
        self,
        writer: pd.ExcelWriter,
        result: ExtractionResult,
    ) -> None:
        """Add detailed extraction metadata sheet."""
        # Calculate confidence reasons
        confidence_notes = self._analyze_confidence_reasons(
            result.benefit_records, 
            result.overall_confidence
        )
        
        metadata = {
            "Property": [
                "Document ID",
                "Source Filename",
                "Document Type",
                "Plan Name",
                "Extraction Timestamp",
                "Total Records",
                "Overall Confidence",
                "Confidence Notes",
                "Requires Human Review",
                "Validation Issues",
            ],
            "Value": [
                result.document_id,
                result.source_filename,
                result.classification.document_type.value if result.classification else "N/A",
                result.classification.plan_name if result.classification else "N/A",
                result.metadata.extraction_timestamp.strftime("%Y-%m-%d %H:%M:%S"),
                len(result.benefit_records),
                f"{result.overall_confidence:.2%}",
                confidence_notes,
                "Yes" if result.requires_human_review else "No",
                len(result.validation_issues),
            ],
        }
        
        df_metadata = pd.DataFrame(metadata)
        df_metadata.to_excel(writer, index=False, sheet_name="Metadata")
        
        # Add validation issues sheet if any
        if result.validation_issues:
            issues_data = [
                {
                    "Record Index": issue.record_index,
                    "Field": issue.field_name,
                    "Issue Type": issue.issue_type,
                    "Message": issue.message,
                    "Severity": issue.severity,
                }
                for issue in result.validation_issues
            ]
            df_issues = pd.DataFrame(issues_data)
            df_issues.to_excel(writer, index=False, sheet_name="Validation Issues")

    def add_sheet(self, sheet_name: str, data: List[Dict[str, Any]]) -> None:
        """
        Add a new sheet to existing workbook.
        
        Args:
            sheet_name: Name of the new sheet
            data: Data to write to the sheet
        """
        df = pd.DataFrame(data)
        
        with pd.ExcelWriter(
            self.output_path, engine="openpyxl", mode="a", if_sheet_exists="replace"
        ) as writer:
            df.to_excel(writer, sheet_name=sheet_name, index=False)

    def save(self) -> None:
        """Finalize and save the Excel file."""
        if self.workbook:
            self.workbook.save(self.output_path)