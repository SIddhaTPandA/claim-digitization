"""
Structured Table Extractor for SPD/SBC Benefit Documents.

This module provides robust, schema-bound extraction of benefit tables
from PDF documents processed by Azure Document Intelligence.

Design Principles:
- Schema-first: Column roles are detected and bound before extraction
- Header-aware: Repeated headers across pages are filtered
- Position-independent: Values are mapped by column role, not position
- Configurable: All patterns and thresholds come from ExtractionConfig
- Multi-row header support: Handles complex headers spanning multiple rows
"""

import logging
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple, Pattern

from src.config.extraction_config import (
    ExtractionConfig,
    DEFAULT_CONFIG,
    CompiledPatterns,
)

logger = logging.getLogger(__name__)


class ColumnRole(Enum):
    """Semantic roles for table columns."""
    SERVICE_NAME = "service_name"
    IN_NETWORK_VALUE = "in_network_value"
    OUT_OF_NETWORK_VALUE = "out_of_network_value"
    IN_NETWORK_COPAY = "in_network_copay"
    OUT_OF_NETWORK_COPAY = "out_of_network_copay"
    LIMITATIONS = "limitations"
    PREAUTH = "preauth"
    NOTES = "notes"
    UNKNOWN = "unknown"


@dataclass
class ColumnSchema:
    """
    Schema definition for a detected table structure.
    Maps column indices to semantic roles.
    """
    column_count: int = 0
    role_mapping: Dict[int, ColumnRole] = field(default_factory=dict)
    header_row_indices: List[int] = field(default_factory=list)  # Support multi-row headers
    header_texts: List[str] = field(default_factory=list)  # Merged header texts for each column
    confidence: float = 0.0
    
    @property
    def header_row_index(self) -> int:
        """Get the last header row index (for backward compatibility)."""
        return self.header_row_indices[-1] if self.header_row_indices else -1
    
    @header_row_index.setter
    def header_row_index(self, value: int) -> None:
        """Set header row index (updates header_row_indices)."""
        if value >= 0:
            if not self.header_row_indices:
                self.header_row_indices = [value]
            else:
                # Replace last index or add if empty
                self.header_row_indices[-1] = value
    
    def get_column_for_role(self, role: ColumnRole) -> Optional[int]:
        """Get column index for a given role."""
        for col_idx, col_role in self.role_mapping.items():
            if col_role == role:
                return col_idx
        return None
    
    def get_columns_for_role(self, role: ColumnRole) -> List[int]:
        """Get all column indices for a given role."""
        return [col_idx for col_idx, col_role in self.role_mapping.items() if col_role == role]
    
    def has_required_columns(self) -> bool:
        """Check if schema has minimum required columns."""
        roles = set(self.role_mapping.values())
        return (
            ColumnRole.SERVICE_NAME in roles and
            (ColumnRole.IN_NETWORK_VALUE in roles or ColumnRole.IN_NETWORK_COPAY in roles)
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for logging/debugging."""
        return {
            "column_count": self.column_count,
            "role_mapping": {k: v.value for k, v in self.role_mapping.items()},
            "header_row_indices": self.header_row_indices,
            "header_texts": self.header_texts,
            "confidence": self.confidence,
        }


@dataclass
class ExtractedRow:
    """A single row extracted from a benefit table."""
    service_name: str
    in_network_value: Optional[str] = None
    out_of_network_value: Optional[str] = None
    in_network_copay: Optional[str] = None
    out_of_network_copay: Optional[str] = None
    limitations: Optional[str] = None
    preauth: Optional[str] = None
    notes: Optional[str] = None
    
    # Metadata
    is_category_header: bool = False
    is_parent_service: bool = False  # NEW: Intermediate service header (e.g., "Office Visit for Injury/Illness")
    parent_service_name: Optional[str] = None  # NEW: Parent service if this is a child row
    category: str = "General Services"
    row_index: int = -1
    table_index: int = -1
    page_number: int = -1
    confidence: float = 0.8
    extraction_notes: List[str] = field(default_factory=list)
    
    @property
    def full_service_name(self) -> str:
        """
        Get the complete service name including parent context.
        
        For hierarchical tables like:
            "Office Visit for Injury / Illness"
                "Primary Care"           <- full name: "Office Visit for Injury / Illness - Primary Care"
                "Specialist"             <- full name: "Office Visit for Injury / Illness - Specialist"
        """
        if self.parent_service_name and self.service_name:
            # Avoid duplication if parent is already in service name
            parent_lower = self.parent_service_name.lower().strip()
            service_lower = self.service_name.lower().strip()
            if service_lower.startswith(parent_lower) or parent_lower in service_lower:
                return self.service_name
            return f"{self.parent_service_name} - {self.service_name}"
        return self.service_name


@dataclass
class HierarchicalContext:
    """
    Tracks hierarchical context during table extraction.
    
    Handles document structures like:
        CATEGORY HEADER: "Physician Services"
            PARENT SERVICE: "Office Visit for Injury / Illness"
                CHILD: "Primary Care"     -> values
                CHILD: "Specialist"       -> values
            PARENT SERVICE: "Preventive Care"
                CHILD: "Annual Exam"      -> values
    """
    current_category: str = "General Services"
    current_parent_service: Optional[str] = None
    parent_row_index: int = -1
    parent_table_index: int = -1
    
    # Tracking for smart parent detection
    last_service_had_values: bool = False
    consecutive_child_rows: int = 0
    
    def update_category(self, category_name: str, row_idx: int, table_idx: int) -> None:
        """Update category and reset parent context."""
        self.current_category = category_name
        self.current_parent_service = None
        self.parent_row_index = -1
        self.parent_table_index = -1
        self.consecutive_child_rows = 0
    
    def update_parent_service(self, parent_name: str, row_idx: int, table_idx: int) -> None:
        """Set a new parent service context."""
        self.current_parent_service = parent_name
        self.parent_row_index = row_idx
        self.parent_table_index = table_idx
        self.last_service_had_values = False
        self.consecutive_child_rows = 0
    
    def record_child_row(self, has_values: bool) -> None:
        """Record that we processed a child row."""
        self.last_service_had_values = has_values
        if has_values:
            self.consecutive_child_rows += 1
    
    def should_clear_parent(self, row_idx: int, table_idx: int) -> bool:
        """
        Determine if we should clear parent context.
        
        Clear parent when:
        - Moving to a new table
        - Large gap in row indices (more than 10 rows since parent)
        - After processing several child rows and hitting a new non-value row
        """
        if table_idx != self.parent_table_index:
            return True
        if self.parent_row_index >= 0 and row_idx - self.parent_row_index > 15:
            return True
        return False
    
    def clear_parent(self) -> None:
        """Clear the current parent service context."""
        self.current_parent_service = None
        self.parent_row_index = -1
        self.consecutive_child_rows = 0


class StructuredTableExtractor:
    """
    Extracts benefit data from tables using schema-bound approach.
    
    Key features:
    - Detects table structure and column roles from headers
    - Filters repeated headers across pages
    - Maps values to columns by semantic role, not position
    - Handles multi-row entries and merged cells
    - Tracks extraction confidence at row level
    - All patterns loaded from centralized ExtractionConfig
    """
    
    # Role name to enum mapping
    ROLE_NAME_MAP = {
        "service_name": ColumnRole.SERVICE_NAME,
        "in_network_value": ColumnRole.IN_NETWORK_VALUE,
        "out_of_network_value": ColumnRole.OUT_OF_NETWORK_VALUE,
        "in_network_copay": ColumnRole.IN_NETWORK_COPAY,
        "out_of_network_copay": ColumnRole.OUT_OF_NETWORK_COPAY,
        "limitations": ColumnRole.LIMITATIONS,
        "preauth": ColumnRole.PREAUTH,
        "notes": ColumnRole.NOTES,
    }

    def __init__(
        self,
        config: Optional[ExtractionConfig] = None,
        min_columns: int = 2,
        min_rows: int = 2,
        confidence_threshold: float = 0.6,
    ):
        """
        Initialize the table extractor.
        
        Args:
            config: ExtractionConfig instance (uses DEFAULT_CONFIG if None)
            min_columns: Minimum columns for a valid benefit table
            min_rows: Minimum rows for a valid benefit table
            confidence_threshold: Minimum confidence for schema detection
        """
        self.config = config or DEFAULT_CONFIG
        self.min_columns = min_columns
        self.min_rows = min_rows
        self.confidence_threshold = confidence_threshold
        
        # Compile patterns from config
        self._compiled = self.config.compile_patterns()
        
        # Track seen headers to filter duplicates
        self._seen_headers: Set[str] = set()
        self._current_category: str = "General Services"
        
        # Hierarchical context for tracking parent service relationships
        self._hierarchical_context: HierarchicalContext = HierarchicalContext()
        
        # Patterns for detecting parent service rows (intermediate headers)
        self._parent_service_indicators = re.compile(
            r'\b(?:visit|care|treatment|service|therapy|procedure|exam|test|'
            r'surgery|admission|stay|consultation|screening|injection|infusion|'
            r'supply|equipment|aid|device|benefit|coverage)\b',
            re.IGNORECASE
        )
        
        logger.info(
            f"StructuredTableExtractor initialized with config-based patterns "
            f"(multi-row headers: {self.config.enable_multi_row_headers})"
        )

    def extract_from_tables(
        self,
        tables: List[Dict[str, Any]],
        page_info: Optional[Dict[int, int]] = None,
    ) -> List[ExtractedRow]:
        """
        Extract benefit rows from a list of tables.
        
        Args:
            tables: List of table dicts with 'rows' and optional 'cells' from Azure DI
            page_info: Optional mapping of table index to page number
            
        Returns:
            List of ExtractedRow objects
        """
        all_rows: List[ExtractedRow] = []
        self._seen_headers.clear()
        self._current_category = "General Services"
        
        # Reset hierarchical context for new document
        self._hierarchical_context = HierarchicalContext()
        
        for table_idx, table in enumerate(tables):
            page_num = page_info.get(table_idx, -1) if page_info else -1
            
            # Get rows from table
            rows = self._get_table_rows(table)
            
            if len(rows) < self.min_rows:
                logger.debug(f"Table {table_idx}: Skipping, only {len(rows)} rows")
                continue
            
            # Detect schema for this table
            schema = self._detect_schema(rows)
            
            if not schema.has_required_columns():
                logger.debug(f"Table {table_idx}: No valid schema detected")
                continue
            
            logger.info(
                f"Table {table_idx}: Detected schema with {schema.column_count} columns, "
                f"confidence {schema.confidence:.0%}"
            )
            
            # Extract rows using schema
            table_rows = self._extract_rows_with_schema(
                rows=rows,
                schema=schema,
                table_idx=table_idx,
                page_num=page_num,
            )
            
            all_rows.extend(table_rows)
        
        logger.info(f"Extracted {len(all_rows)} total rows from {len(tables)} tables")
        return all_rows

    def _get_table_rows(self, table: Dict[str, Any]) -> List[List[str]]:
        """Extract row data from table dict (supports multiple formats)."""
        # Azure Document Intelligence format with cells
        if "cells" in table:
            return self._cells_to_rows(table["cells"], table.get("row_count", 0), table.get("column_count", 0))
        
        # Simple rows format
        if "rows" in table:
            return [[str(cell) if cell else "" for cell in row] for row in table["rows"]]
        
        return []

    def _cells_to_rows(
        self,
        cells: List[Dict[str, Any]],
        row_count: int,
        column_count: int,
    ) -> List[List[str]]:
        """Convert Azure DI cells format to row-based format."""
        # Initialize empty grid
        rows: List[List[str]] = [["" for _ in range(column_count)] for _ in range(row_count)]
        
        for cell in cells:
            row_idx = cell.get("row_index", cell.get("rowIndex", 0))
            col_idx = cell.get("column_index", cell.get("columnIndex", 0))
            content = cell.get("content", cell.get("text", ""))
            
            if 0 <= row_idx < row_count and 0 <= col_idx < column_count:
                rows[row_idx][col_idx] = str(content).strip() if content else ""
        
        return rows

    def _detect_schema(self, rows: List[List[str]]) -> ColumnSchema:
        """
        Detect table schema by analyzing header row and content patterns.
        
        Strategy:
        1. Look for header row(s) (contains header keywords)
        2. Map each column to a semantic role
        3. Validate with content patterns
        """
        schema = ColumnSchema()
        
        if not rows:
            return schema
        
        schema.column_count = max(len(row) for row in rows)
        
        # Find header row(s) - use multi-row detection if enabled
        if self.config.enable_multi_row_headers:
            header_row_indices, header_confidence = self._find_multi_row_headers(rows)
            schema.header_row_indices = header_row_indices
            
            if header_row_indices:
                schema.header_row_index = header_row_indices[-1]  # Last header row for data start
                
                # Merge headers from all rows for column classification
                merged_headers = self._merge_multi_row_headers(rows, header_row_indices)
                schema.header_texts = merged_headers
                
                # Map columns based on merged header text
                for col_idx, header_text in enumerate(merged_headers):
                    role = self._classify_column_header(header_text)
                    if role != ColumnRole.UNKNOWN:
                        schema.role_mapping[col_idx] = role
                
                schema.confidence = header_confidence
        else:
            header_row_idx, header_confidence = self._find_header_row(rows)
            
            if header_row_idx >= 0:
                schema.header_row_index = header_row_idx
                schema.header_row_indices = [header_row_idx]
                schema.header_texts = rows[header_row_idx]
                
                # Map columns based on header text
                for col_idx, header_text in enumerate(rows[header_row_idx]):
                    role = self._classify_column_header(header_text)
                    if role != ColumnRole.UNKNOWN:
                        schema.role_mapping[col_idx] = role
                
                schema.confidence = header_confidence
        
        # If no header found, low confidence, OR missing required columns, use content analysis
        if schema.confidence < self.confidence_threshold or not schema.has_required_columns():
            content_schema = self._detect_schema_from_content(rows)
            # Use content schema if it has required columns OR higher confidence
            if content_schema.has_required_columns() and not schema.has_required_columns():
                logger.debug("Using content-based schema: header-based missing required columns")
                schema = content_schema
            elif content_schema.confidence > schema.confidence:
                schema = content_schema
        
        # Ensure we have a service column (usually first non-value column)
        if ColumnRole.SERVICE_NAME not in schema.role_mapping.values():
            service_col = self._find_service_column(rows, schema)
            if service_col >= 0:
                schema.role_mapping[service_col] = ColumnRole.SERVICE_NAME
        
        # Ensure we have at least IN_NETWORK_VALUE if we have value columns
        value_roles = [ColumnRole.IN_NETWORK_VALUE, ColumnRole.OUT_OF_NETWORK_VALUE]
        has_value_role = any(r in schema.role_mapping.values() for r in value_roles)
        
        if not has_value_role:
            value_cols = self._find_value_columns(rows, schema)
            if len(value_cols) >= 1:
                schema.role_mapping[value_cols[0]] = ColumnRole.IN_NETWORK_VALUE
            if len(value_cols) >= 2:
                schema.role_mapping[value_cols[1]] = ColumnRole.OUT_OF_NETWORK_VALUE
        
        return schema

    def _find_header_row(self, rows: List[List[str]]) -> Tuple[int, float]:
        """
        Find the most likely header row.
        
        Returns:
            Tuple of (row_index, confidence)
        """
        best_row = -1
        best_score = 0.0
        
        # Check first few rows for header patterns
        for row_idx in range(min(5, len(rows))):
            row = rows[row_idx]
            score = self._score_as_header_row(row)
            
            if score > best_score:
                best_score = score
                best_row = row_idx
        
        return best_row, best_score

    def _find_multi_row_headers(self, rows: List[List[str]]) -> Tuple[List[int], float]:
        """
        Find multi-row header structure when headers span multiple rows.
        
        This handles complex table layouts like:
        Row 0: | Service | In-Network        | Out-of-Network    |
        Row 1: |         | Copay | Coins.    | Copay | Coins.    |
        
        Returns:
            Tuple of (list_of_header_row_indices, confidence)
        """
        if len(rows) < 2:
            # Single row - fall back to standard detection
            single_row, confidence = self._find_header_row(rows)
            return [single_row] if single_row >= 0 else [], confidence
        
        # Track header-like rows in sequence at the start
        header_rows: List[int] = []
        combined_score = 0.0
        
        for row_idx in range(min(5, len(rows))):
            row = rows[row_idx]
            
            # Skip rows that are clearly notes/disclaimers (very long first cell)
            first_cell = row[0].strip() if row else ""
            if len(first_cell) > 150:
                logger.debug(f"Skipping row {row_idx}: first cell too long ({len(first_cell)} chars) - likely disclaimer")
                continue
            
            score = self._score_as_header_row(row)
            
            # Row is header-like if it has header patterns and low value patterns
            if score > 0.3:
                # Check if values are sparse (suggesting continuation of headers)
                value_count = sum(1 for cell in row if self._is_value_cell(cell.strip()))
                non_empty = sum(1 for cell in row if cell.strip())
                
                if non_empty > 0:
                    value_ratio = value_count / non_empty
                    # If less than 30% values, likely still in header region
                    if value_ratio < 0.3:
                        header_rows.append(row_idx)
                        combined_score = max(combined_score, score)
                    else:
                        # Data rows started
                        break
            elif header_rows:
                # Non-header row after header rows = end of headers
                break
        
        # Validate: must have at least one header row
        if not header_rows:
            single_row, confidence = self._find_header_row(rows)
            return [single_row] if single_row >= 0 else [], confidence
        
        # If multiple consecutive header rows, merge their column info
        if len(header_rows) > 1:
            logger.debug(f"Detected multi-row headers: rows {header_rows}")
        
        return header_rows, combined_score

    def _merge_multi_row_headers(
        self,
        rows: List[List[str]],
        header_row_indices: List[int],
    ) -> List[str]:
        """
        Merge headers from multiple rows into a single header list.
        
        For multi-row headers like:
        Row 0: | Service | In-Network        | Out-of-Network    |
        Row 1: |         | Copay | Coins.    | Copay | Coins.    |
        
        Produces: ["Service", "In-Network Copay", "In-Network Coins.", 
                   "Out-of-Network Copay", "Out-of-Network Coins."]
        
        Args:
            rows: All table rows
            header_row_indices: Indices of rows that form the header
            
        Returns:
            List of merged header strings for each column
        """
        if not header_row_indices:
            return []
        
        if len(header_row_indices) == 1:
            row_idx = header_row_indices[0]
            return rows[row_idx] if row_idx < len(rows) else []
        
        # Get max columns across header rows
        max_cols = max(
            len(rows[idx]) for idx in header_row_indices if idx < len(rows)
        )
        
        merged: List[str] = [""] * max_cols
        
        # Track parent header for each column (for hierarchical headers)
        parent_headers: List[str] = [""] * max_cols
        
        for row_idx in header_row_indices:
            if row_idx >= len(rows):
                continue
            
            row = rows[row_idx]
            current_parent = ""
            
            for col_idx in range(min(len(row), max_cols)):
                cell = row[col_idx].strip()
                
                if cell:
                    if row_idx == header_row_indices[0]:
                        # First header row - set parent headers
                        parent_headers[col_idx] = cell
                        merged[col_idx] = cell
                        current_parent = cell
                    else:
                        # Subsequent rows - concatenate with parent if exists
                        parent = parent_headers[col_idx] or current_parent
                        if parent and parent.lower() != cell.lower():
                            merged[col_idx] = f"{parent} {cell}"
                        else:
                            merged[col_idx] = cell
                else:
                    # Empty cell - inherit from previous non-empty cell in same row
                    if row_idx == header_row_indices[0]:
                        # First row - propagate parent from left
                        parent_headers[col_idx] = current_parent
        
        return merged

    def _score_as_header_row(self, row: List[str]) -> float:
        """Score how likely a row is to be a header row using config patterns."""
        if not row:
            return 0.0
        
        matches = 0
        total_cells = len([c for c in row if c.strip()])
        
        if total_cells == 0:
            return 0.0
        
        for cell in row:
            if not cell.strip():
                continue
            
            cell_lower = cell.lower().strip()
            
            # Check if cell matches any header pattern from config
            matched = False
            for role, patterns in self._compiled.table_headers.items():
                for pattern in patterns:
                    if pattern.search(cell_lower):
                        matches += 1
                        matched = True
                        break
                if matched:
                    break
            
            # Penalize if cell looks like a value
            if self._is_value_cell(cell):
                matches -= 0.5
        
        return matches / total_cells if total_cells > 0 else 0.0

    def _classify_column_header(self, header_text: str) -> ColumnRole:
        """Classify a column header text to a semantic role using config patterns."""
        if not header_text or not header_text.strip():
            return ColumnRole.UNKNOWN
        
        header_lower = header_text.lower().strip()
        
        # Check each role's patterns (ordered by priority in config)
        # Priority order: SERVICE_NAME, IN_NETWORK, OUT_OF_NETWORK, etc.
        priority_order = [
            ColumnRole.SERVICE_NAME,
            ColumnRole.IN_NETWORK_VALUE,
            ColumnRole.OUT_OF_NETWORK_VALUE,
            ColumnRole.IN_NETWORK_COPAY,
            ColumnRole.OUT_OF_NETWORK_COPAY,
            ColumnRole.LIMITATIONS,
            ColumnRole.PREAUTH,
            ColumnRole.NOTES,
        ]
        
        for role in priority_order:
            role_key = role.value
            if role_key in self._compiled.table_headers:
                for pattern in self._compiled.table_headers[role_key]:
                    if pattern.search(header_lower):
                        return role
        
        return ColumnRole.UNKNOWN

    def _detect_schema_from_content(self, rows: List[List[str]]) -> ColumnSchema:
        """Detect schema by analyzing content patterns (fallback method)."""
        schema = ColumnSchema()
        schema.column_count = max(len(row) for row in rows) if rows else 0
        
        if schema.column_count < self.min_columns:
            return schema
        
        # Analyze content of each column
        col_scores: Dict[int, Dict[str, int]] = {}
        
        for col_idx in range(schema.column_count):
            col_scores[col_idx] = {"text": 0, "value": 0, "empty": 0}
            
            for row in rows:
                if col_idx >= len(row):
                    col_scores[col_idx]["empty"] += 1
                    continue
                
                cell = row[col_idx]
                if not cell.strip():
                    col_scores[col_idx]["empty"] += 1
                elif self._is_value_cell(cell):
                    col_scores[col_idx]["value"] += 1
                else:
                    col_scores[col_idx]["text"] += 1
        
        # Assign roles based on content analysis
        # First column with mostly text is likely service name
        for col_idx in range(schema.column_count):
            scores = col_scores[col_idx]
            total = scores["text"] + scores["value"]
            if total > 0 and scores["text"] / total > 0.5:
                schema.role_mapping[col_idx] = ColumnRole.SERVICE_NAME
                break
        
        # Columns with mostly values are benefit columns
        value_cols = []
        for col_idx in range(schema.column_count):
            if col_idx in schema.role_mapping:
                continue
            scores = col_scores[col_idx]
            total = scores["text"] + scores["value"]
            if total > 0 and scores["value"] / total > 0.3:
                value_cols.append((col_idx, scores["value"]))
        
        # Sort by value count descending
        value_cols.sort(key=lambda x: -x[1])
        
        if len(value_cols) >= 1:
            schema.role_mapping[value_cols[0][0]] = ColumnRole.IN_NETWORK_VALUE
        if len(value_cols) >= 2:
            schema.role_mapping[value_cols[1][0]] = ColumnRole.OUT_OF_NETWORK_VALUE
        
        schema.confidence = 0.5  # Lower confidence for content-based detection
        return schema

    def _find_service_column(self, rows: List[List[str]], schema: ColumnSchema) -> int:
        """Find the service name column."""
        assigned_cols = set(schema.role_mapping.keys())
        
        for col_idx in range(schema.column_count):
            if col_idx in assigned_cols:
                continue
            
            text_count = 0
            value_count = 0
            
            for row in rows:
                if col_idx >= len(row):
                    continue
                cell = row[col_idx]
                if self._is_value_cell(cell):
                    value_count += 1
                elif cell.strip():
                    text_count += 1
            
            # First column that's mostly text
            if text_count > value_count:
                return col_idx
        
        return 0  # Default to first column

    def _find_value_columns(self, rows: List[List[str]], schema: ColumnSchema) -> List[int]:
        """Find columns that contain benefit values."""
        assigned_cols = set(schema.role_mapping.keys())
        value_cols = []
        
        for col_idx in range(schema.column_count):
            if col_idx in assigned_cols:
                continue
            
            value_count = 0
            total_count = 0
            
            for row in rows:
                if col_idx >= len(row):
                    continue
                cell = row[col_idx]
                if cell.strip():
                    total_count += 1
                    if self._is_value_cell(cell):
                        value_count += 1
            
            if total_count > 0 and value_count / total_count > 0.2:
                value_cols.append(col_idx)
        
        return value_cols

    def _is_value_cell(self, cell: str) -> bool:
        """Check if a cell contains a benefit value using config patterns."""
        if not cell:
            return False
        
        cell = cell.strip()
        
        for pattern in self._compiled.value_cell_patterns:
            if pattern.search(cell):
                return True
        
        return False

    def _is_parent_service_row(
        self,
        row: List[str],
        schema: ColumnSchema,
        row_idx: int,
    ) -> Tuple[bool, Optional[str]]:
        """
        Detect if a row is a parent/intermediate service header.
        
        Parent service rows are rows that:
        - Have text content in service column
        - Have EMPTY or minimal value columns (no coinsurance/copay values)
        - Are NOT category headers (shorter, more specific)
        - Contain service-related keywords like "visit", "care", "treatment"
        
        Examples:
            "Office Visit for Injury / Illness"  (parent, no values)
                "Primary Care"                    (child, has values)
                "Specialist"                      (child, has values)
            
        Returns:
            Tuple of (is_parent_service, parent_name)
        """
        # Get cells with content
        non_empty = [(idx, cell.strip()) for idx, cell in enumerate(row) if cell.strip()]
        
        if not non_empty:
            return False, None
        
        # Get service column
        service_col = schema.get_column_for_role(ColumnRole.SERVICE_NAME)
        
        # Must have exactly one non-empty cell (the service name)
        # OR have service name but empty/non-value content in value columns
        if len(non_empty) == 1:
            cell_idx, cell_text = non_empty[0]
            
            # Must be in service column (or first column as fallback)
            if service_col is not None and cell_idx != service_col:
                if cell_idx != 0:  # Allow first column as fallback
                    return False, None
            
            # Should not be a value
            if self._is_value_cell(cell_text):
                return False, None
            
            # Should NOT match category patterns (categories are different)
            # UNLESS it has specific service keywords and doesn't end with "services"
            is_category_match = False
            for pattern in self._compiled.category_patterns_list:
                if pattern.search(cell_text):
                    is_category_match = True
                    break
            
            if is_category_match:
                # Check if it's actually a specific service (not a broad category)
                # Broad categories typically end with "services" or "care"
                if cell_text.lower().strip().endswith(('services', 'service')):
                    return False, None  # It's a category, not parent service
                # If it has specific service keywords, treat as parent service
                if not self._parent_service_indicators.search(cell_text):
                    return False, None  # Matched category pattern but no service keywords
            
            # Must be reasonable length (not too short, not too long)
            if len(cell_text) < 5 or len(cell_text) > 100:
                return False, None
            
            # Should contain service-related keywords to be a parent service
            if self._parent_service_indicators.search(cell_text):
                logger.debug(f"Detected parent service row: '{cell_text}'")
                return True, cell_text
            
            # Also consider rows that end with common service suffixes
            if re.search(r'(?:illness|injury|sickness|condition|need|services?)\s*$', 
                        cell_text, re.IGNORECASE):
                logger.debug(f"Detected parent service row (suffix match): '{cell_text}'")
                return True, cell_text
        
        # Handle rows with service name + some non-value text (like notes)
        elif len(non_empty) <= 3:
            service_text = None
            has_value = False
            
            for cell_idx, cell_text in non_empty:
                if service_col is not None and cell_idx == service_col:
                    service_text = cell_text
                elif cell_idx == 0 and service_col is None:
                    service_text = cell_text
                elif self._is_value_cell(cell_text):
                    has_value = True
                    break
            
            # If we have service text but NO value cells
            if service_text and not has_value:
                if self._parent_service_indicators.search(service_text):
                    if len(service_text) >= 5 and len(service_text) <= 100:
                        # Check if matches category pattern
                        is_category_match = False
                        for pattern in self._compiled.category_patterns_list:
                            if pattern.search(service_text):
                                is_category_match = True
                                break
                        
                        if is_category_match:
                            # Only reject if it ends with "services" (broad category)
                            if service_text.lower().strip().endswith(('services', 'service')):
                                return False, None
                        
                        logger.debug(f"Detected parent service row (multi-cell): '{service_text}'")
                        return True, service_text
        
        return False, None

    def _extract_rows_with_schema(
        self,
        rows: List[List[str]],
        schema: ColumnSchema,
        table_idx: int,
        page_num: int,
    ) -> List[ExtractedRow]:
        """
        Extract benefit rows using the detected schema.
        
        Handles hierarchical document structures:
        - Category headers (e.g., "Physician Services") 
        - Parent service rows (e.g., "Office Visit for Injury / Illness")
        - Child rows with values (e.g., "Primary Care" with 80%, 60%)
        
        Args:
            rows: Table rows
            schema: Detected column schema
            table_idx: Index of this table
            page_num: Page number
            
        Returns:
            List of ExtractedRow objects
        """
        extracted: List[ExtractedRow] = []
        start_row = schema.header_row_index + 1 if schema.header_row_index >= 0 else 0
        
        # Check if we should clear parent context when moving to new table
        if self._hierarchical_context.should_clear_parent(start_row, table_idx):
            self._hierarchical_context.clear_parent()
        
        for row_idx in range(start_row, len(rows)):
            row = rows[row_idx]
            
            # Skip empty rows
            if not any(cell.strip() for cell in row):
                continue
            
            # Skip repeated header rows
            if self._is_repeated_header(row):
                logger.debug(f"Skipping repeated header at row {row_idx}")
                continue
            
            # STEP 1: Check if this is a category header
            if self._is_category_row(row, schema):
                new_category = self._extract_category_name(row)
                if new_category:
                    self._current_category = new_category
                    self._hierarchical_context.update_category(new_category, row_idx, table_idx)
                    
                    extracted.append(ExtractedRow(
                        service_name=new_category,
                        is_category_header=True,
                        category=new_category,
                        row_index=row_idx,
                        table_index=table_idx,
                        page_number=page_num,
                    ))
                continue
            
            # STEP 2: Check if this is a parent service row
            is_parent, parent_name = self._is_parent_service_row(row, schema, row_idx)
            if is_parent and parent_name:
                self._hierarchical_context.update_parent_service(parent_name, row_idx, table_idx)
                
                # Add parent service row marker
                extracted.append(ExtractedRow(
                    service_name=parent_name,
                    is_parent_service=True,
                    is_category_header=False,
                    category=self._current_category,
                    row_index=row_idx,
                    table_index=table_idx,
                    page_number=page_num,
                    extraction_notes=["Detected as parent service row"],
                ))
                continue
            
            # STEP 3: Extract data row using schema binding
            extracted_row = self._extract_row_with_schema(row, schema, row_idx, table_idx, page_num)
            
            if extracted_row:
                extracted_row.category = self._current_category
                
                # Apply parent context if available
                if self._hierarchical_context.current_parent_service:
                    extracted_row.parent_service_name = self._hierarchical_context.current_parent_service
                    extracted_row.extraction_notes.append(
                        f"Parent: {self._hierarchical_context.current_parent_service}"
                    )
                
                # Track that we got a row with values
                has_values = bool(extracted_row.in_network_value or extracted_row.out_of_network_value or
                                 extracted_row.in_network_copay or extracted_row.out_of_network_copay)
                self._hierarchical_context.record_child_row(has_values)
                
                extracted.append(extracted_row)
        
        return extracted

    def _is_repeated_header(self, row: List[str]) -> bool:
        """Check if a row is a repeated header that should be skipped."""
        # Create a signature from non-empty cells
        non_empty = [cell.strip().lower() for cell in row if cell.strip()]
        
        if not non_empty:
            return False
        
        signature = " | ".join(sorted(non_empty))
        
        # Check if we've seen this exact combination before
        if signature in self._seen_headers:
            return True
        
        # Check if any cell matches repeated header patterns from config
        for cell in non_empty:
            for pattern in self._compiled.repeated_header_patterns:
                if pattern.match(cell):
                    # This looks like a header - track it
                    self._seen_headers.add(signature)
                    return True
        
        # Check if row looks like a header row (multiple header-like cells)
        # But skip cells that contain value indicators (%, $) - those are data, not headers
        header_cell_count = 0
        value_indicator_pattern = re.compile(r'[\d%$]')
        
        for cell in non_empty:
            # Skip cells with numeric/value indicators - these are data cells
            if value_indicator_pattern.search(cell):
                continue
            
            for role, patterns in self._compiled.table_headers.items():
                matched = False
                for pattern in patterns:
                    if pattern.search(cell):
                        header_cell_count += 1
                        matched = True
                        break
                if matched:
                    break
        
        # Only flag as repeated header if majority of NON-VALUE cells match header patterns
        non_value_cells = [c for c in non_empty if not value_indicator_pattern.search(c)]
        if len(non_value_cells) >= 2 and header_cell_count >= len(non_value_cells) * 0.5:
            self._seen_headers.add(signature)
            return True
        
        return False

    def _is_category_row(self, row: List[str], schema: ColumnSchema) -> bool:
        """Check if a row is a category header using config patterns."""
        # Count non-empty cells
        non_empty = [(idx, cell.strip()) for idx, cell in enumerate(row) if cell.strip()]
        
        if len(non_empty) != 1:
            return False
        
        cell_idx, cell_text = non_empty[0]
        
        # Should not be a value
        if self._is_value_cell(cell_text):
            return False
        
        # Check against category patterns from config ONLY
        # DO NOT fallback to "long text = category" - that catches parent services
        for pattern in self._compiled.category_patterns_list:
            if pattern.search(cell_text):
                # But verify it's NOT a parent service row (has service keywords)
                parent_indicators = re.compile(
                    r'\b(visit|care|service|exam|treatment|therapy|screening|test|procedure|surgery|office)\b',
                    re.IGNORECASE
                )
                # If it matches a category pattern AND doesn't have specific service keywords
                # (other than generic "services" at end), treat as category
                service_specific_match = parent_indicators.search(cell_text)
                # "Physician Services" should be category, "Office Visit" should be parent
                if not service_specific_match or cell_text.lower().strip().endswith('services'):
                    return True
                # Otherwise it's a specific service row, don't treat as category
                return False
        
        return False

    def _extract_category_name(self, row: List[str]) -> Optional[str]:
        """Extract clean category name from row."""
        for cell in row:
            if cell.strip():
                # Clean up common prefixes
                name = cell.strip()
                name = re.sub(r"^if\s+you\s+\w+\s+", "", name, flags=re.IGNORECASE)
                name = re.sub(r"\s+", " ", name).strip()
                
                # Truncate if too long
                if len(name) > 60:
                    name = name[:60].rsplit(" ", 1)[0] + "..."
                
                return name
        
        return None

    def _extract_row_with_schema(
        self,
        row: List[str],
        schema: ColumnSchema,
        row_idx: int,
        table_idx: int,
        page_num: int,
    ) -> Optional[ExtractedRow]:
        """
        Extract a single data row using schema-bound mapping.
        
        This is the key method that ensures values go to correct columns.
        """
        extraction_notes: List[str] = []
        
        # Get service name
        service_col = schema.get_column_for_role(ColumnRole.SERVICE_NAME)
        service_name = ""
        
        if service_col is not None and service_col < len(row):
            service_name = self._clean_cell_text(row[service_col])
        
        # If no service column found, try first non-empty non-value cell
        if not service_name:
            for idx, cell in enumerate(row):
                cell_text = cell.strip()
                if cell_text and not self._is_value_cell(cell_text):
                    service_name = self._clean_cell_text(cell_text)
                    extraction_notes.append(f"Service from col {idx} (fallback)")
                    break
        
        # Must have a service name
        if not service_name:
            return None
        
        # Skip if service name looks like a value
        if self._is_value_cell(service_name):
            extraction_notes.append("Skipped: service looks like value")
            return None
        
        # Extract values by role
        in_network_value = None
        out_network_value = None
        in_network_copay = None
        out_network_copay = None
        limitations = None
        preauth = None
        notes = None
        
        # Get IN_NETWORK_VALUE
        in_col = schema.get_column_for_role(ColumnRole.IN_NETWORK_VALUE)
        if in_col is not None and in_col < len(row):
            in_network_value = self._clean_cell_text(row[in_col])
        
        # Get OUT_OF_NETWORK_VALUE
        out_col = schema.get_column_for_role(ColumnRole.OUT_OF_NETWORK_VALUE)
        if out_col is not None and out_col < len(row):
            out_network_value = self._clean_cell_text(row[out_col])
        
        # Get IN_NETWORK_COPAY
        in_copay_col = schema.get_column_for_role(ColumnRole.IN_NETWORK_COPAY)
        if in_copay_col is not None and in_copay_col < len(row):
            in_network_copay = self._clean_cell_text(row[in_copay_col])
        
        # Get OUT_OF_NETWORK_COPAY
        out_copay_col = schema.get_column_for_role(ColumnRole.OUT_OF_NETWORK_COPAY)
        if out_copay_col is not None and out_copay_col < len(row):
            out_network_copay = self._clean_cell_text(row[out_copay_col])
        
        # Get LIMITATIONS
        lim_col = schema.get_column_for_role(ColumnRole.LIMITATIONS)
        if lim_col is not None and lim_col < len(row):
            limitations = self._clean_cell_text(row[lim_col])
        
        # Get PREAUTH
        preauth_col = schema.get_column_for_role(ColumnRole.PREAUTH)
        if preauth_col is not None and preauth_col < len(row):
            preauth = self._clean_cell_text(row[preauth_col])
        
        # Get NOTES
        notes_col = schema.get_column_for_role(ColumnRole.NOTES)
        if notes_col is not None and notes_col < len(row):
            notes = self._clean_cell_text(row[notes_col])
        
        # If no explicit value columns mapped, try unassigned columns
        if not in_network_value and not out_network_value:
            unassigned_values = self._extract_unassigned_values(row, schema)
            if len(unassigned_values) >= 1:
                in_network_value = unassigned_values[0]
                extraction_notes.append("IN value from unassigned column")
            if len(unassigned_values) >= 2:
                out_network_value = unassigned_values[1]
                extraction_notes.append("OON value from unassigned column")
        
        # Calculate row confidence
        confidence = self._calculate_row_confidence(
            service_name=service_name,
            in_network=in_network_value,
            out_network=out_network_value,
            schema_confidence=schema.confidence,
        )
        
        return ExtractedRow(
            service_name=service_name,
            in_network_value=in_network_value,
            out_of_network_value=out_network_value,
            in_network_copay=in_network_copay,
            out_of_network_copay=out_network_copay,
            limitations=limitations,
            preauth=preauth,
            notes=notes,
            row_index=row_idx,
            table_index=table_idx,
            page_number=page_num,
            confidence=confidence,
            extraction_notes=extraction_notes,
        )

    def _extract_unassigned_values(
        self,
        row: List[str],
        schema: ColumnSchema,
    ) -> List[str]:
        """Extract values from columns not assigned to a role."""
        assigned_cols = set(schema.role_mapping.keys())
        values = []
        
        for col_idx, cell in enumerate(row):
            if col_idx in assigned_cols:
                continue
            
            cell_text = self._clean_cell_text(cell)
            if cell_text and self._is_value_cell(cell_text):
                values.append(cell_text)
        
        return values

    def _clean_cell_text(self, text: str) -> Optional[str]:
        """Clean and normalize cell text."""
        if not text:
            return None
        
        text = str(text).strip()
        
        # Remove excessive whitespace
        text = re.sub(r"\s+", " ", text)
        
        # Remove leading/trailing punctuation
        text = re.sub(r"^[\*\-•\s]+|[\s,;:]+$", "", text)
        
        if not text:
            return None
        
        return text

    def _calculate_row_confidence(
        self,
        service_name: str,
        in_network: Optional[str],
        out_network: Optional[str],
        schema_confidence: float,
    ) -> float:
        """Calculate confidence score for an extracted row."""
        confidence = schema_confidence * 0.5  # Schema contributes 50%
        
        # Service name quality
        if service_name:
            confidence += 0.2
            if len(service_name) > 5:
                confidence += 0.05
        
        # Value completeness
        if in_network:
            confidence += 0.15
        if out_network:
            confidence += 0.1
        
        return min(1.0, max(0.0, confidence))

    def reset(self) -> None:
        """Reset extractor state for a new document."""
        self._seen_headers.clear()
        self._current_category = "General Services"
        self._hierarchical_context = HierarchicalContext()
