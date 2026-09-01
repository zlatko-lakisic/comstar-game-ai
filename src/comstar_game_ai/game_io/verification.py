"""Tiered verification: structured check, vision, full re-observation."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable


class VerificationTier(str, Enum):
    STRUCTURED = "structured"
    VISION = "vision"
    FULL_REOBSERVE = "full_reobserve"


class VerificationResult(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    INCONCLUSIVE = "inconclusive"
    SKIPPED = "skipped"


@dataclass
class VerificationOutcome:
    tier: VerificationTier
    result: VerificationResult
    detail: str = ""
    payload: dict[str, Any] = field(default_factory=dict)


StructuredCheck = Callable[[dict[str, Any], dict[str, Any]], VerificationOutcome]
VisionCheck = Callable[[dict[str, Any], dict[str, Any]], VerificationOutcome]
ReobserveCheck = Callable[[dict[str, Any], dict[str, Any]], VerificationOutcome]


@dataclass
class VerificationPipeline:
    """Optimistic execution with escalation on disagreement."""

    structured_check: StructuredCheck | None = None
    vision_check: VisionCheck | None = None
    reobserve_check: ReobserveCheck | None = None
    max_retries: int = 1

    def verify(
        self,
        action: dict[str, Any],
        expected_effect: dict[str, Any],
        *,
        observed: dict[str, Any] | None = None,
    ) -> list[VerificationOutcome]:
        outcomes: list[VerificationOutcome] = []
        observed = observed or {}

        structured = self._run_structured(action, expected_effect, observed)
        outcomes.append(structured)
        if structured.result == VerificationResult.PASS:
            return outcomes

        if self.vision_check is not None:
            vision = self.vision_check(action, expected_effect)
            outcomes.append(vision)
            if vision.result == VerificationResult.PASS:
                return outcomes

        if self.reobserve_check is not None:
            for _ in range(self.max_retries):
                full = self.reobserve_check(action, expected_effect)
                outcomes.append(full)
                if full.result == VerificationResult.PASS:
                    break

        return outcomes

    def _run_structured(
        self,
        action: dict[str, Any],
        expected_effect: dict[str, Any],
        observed: dict[str, Any],
    ) -> VerificationOutcome:
        if self.structured_check is not None:
            return self.structured_check(action, expected_effect)

        if not expected_effect:
            return VerificationOutcome(
                tier=VerificationTier.STRUCTURED,
                result=VerificationResult.SKIPPED,
                detail="no expected_effect",
            )

        mismatches = [
            key for key, value in expected_effect.items() if observed.get(key) != value
        ]
        if not mismatches:
            return VerificationOutcome(
                tier=VerificationTier.STRUCTURED,
                result=VerificationResult.PASS,
                detail="observed matches expected",
            )
        return VerificationOutcome(
            tier=VerificationTier.STRUCTURED,
            result=VerificationResult.FAIL,
            detail=f"mismatch keys: {', '.join(mismatches)}",
            payload={"mismatches": mismatches},
        )
