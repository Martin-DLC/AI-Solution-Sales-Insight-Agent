from __future__ import annotations


class DatasetLoadError(Exception):
    """Raised when a dataset file cannot be loaded or validated."""


class DuplicateCaseIdError(DatasetLoadError):
    """Raised when a JSONL dataset contains duplicate case IDs."""

    def __init__(
        self,
        case_id: str,
        first_line_number: int,
        duplicate_line_number: int,
    ) -> None:
        super().__init__(
            "Duplicate case_id "
            f"{case_id!r}: first seen on line {first_line_number}, "
            f"again on line {duplicate_line_number}."
        )
        self.case_id = case_id
        self.first_line_number = first_line_number
        self.duplicate_line_number = duplicate_line_number


class DatasetBoundaryError(DatasetLoadError):
    """Raised when runtime code attempts to load hidden evaluation data."""

    def __init__(self, path: str) -> None:
        super().__init__(
            "Runtime modules are forbidden from loading Hidden Reference Pack files. "
            f"Path: {path}. Use dataio.evaluation_references for offline evaluation only."
        )
        self.path = path
