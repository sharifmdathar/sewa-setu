"""Deterministic synthetic corpus generator for Sewa Setu (SPEC.md section 6)."""

from __future__ import annotations

from generator.build import build_dataset, ground_truth
from generator.writer import write_dataset

__all__ = ["build_dataset", "ground_truth", "write_dataset"]
