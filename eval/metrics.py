"""Eval metrics: one binary question - did the pipeline flag a fail that was really a fail.

SPEC.md section 7 gates on fail-flag precision and recall. A flag is a `status == "fail"` on one
check of one application, so the unit is (application, check) and the ground truth comes from
`ground_truth.json`, which only ever says pass or fail. `info` and `warn` are not flags.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass


@dataclass(frozen=True)
class Tally:
    """A 2x2 confusion count. `support` is how many real positives existed."""

    true_positive: int = 0
    false_positive: int = 0
    false_negative: int = 0
    true_negative: int = 0

    def __add__(self, other: Tally) -> Tally:
        return Tally(
            self.true_positive + other.true_positive,
            self.false_positive + other.false_positive,
            self.false_negative + other.false_negative,
            self.true_negative + other.true_negative,
        )

    @property
    def support(self) -> int:
        return self.true_positive + self.false_negative

    @property
    def predicted(self) -> int:
        return self.true_positive + self.false_positive

    @property
    def precision(self) -> float:
        return self.true_positive / self.predicted if self.predicted else 1.0

    @property
    def recall(self) -> float:
        return self.true_positive / self.support if self.support else 1.0

    @property
    def f1(self) -> float:
        precision, recall = self.precision, self.recall
        return 2 * precision * recall / (precision + recall) if precision + recall else 0.0

    @property
    def accuracy(self) -> float:
        total = (
            self.true_positive + self.false_positive + self.false_negative + self.true_negative
        )
        return (self.true_positive + self.true_negative) / total if total else 1.0

    def as_dict(self) -> dict[str, float | int]:
        return {
            "truePositive": self.true_positive,
            "falsePositive": self.false_positive,
            "falseNegative": self.false_negative,
            "trueNegative": self.true_negative,
            "support": self.support,
            "predicted": self.predicted,
            "precision": round(self.precision, 4),
            "recall": round(self.recall, 4),
            "f1": round(self.f1, 4),
            "accuracy": round(self.accuracy, 4),
        }


def tally(predicted: Iterable[str], actual: Iterable[str], universe: Iterable[str]) -> Tally:
    """Score one set of ids against another, over the ids that were evaluated at all."""
    predicted_set, actual_set = set(predicted), set(actual)
    items = set(universe)
    return Tally(
        true_positive=len(predicted_set & actual_set & items),
        false_positive=len((predicted_set - actual_set) & items),
        false_negative=len((actual_set - predicted_set) & items),
        true_negative=len(items - predicted_set - actual_set),
    )


def total(tallies: Iterable[Tally]) -> Tally:
    """Micro average: pooling the counts weights each application equally, not each check."""
    combined = Tally()
    for tally_row in tallies:
        combined = combined + tally_row
    return combined
