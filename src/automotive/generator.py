"""Compatibility import. Production code uses automotive_quality sources."""

from automotive_quality.infrastructure.sources.synthetic import WorkOrderDataset, generate_dataset, write_raw_data

GeneratedData = WorkOrderDataset

__all__ = ["GeneratedData", "WorkOrderDataset", "generate_dataset", "write_raw_data"]
