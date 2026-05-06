"""Prompts only after validated field families or validated claims."""

from __future__ import annotations

from typing import List

from src.models import IdentityStatus, PromptResult, SignalResult, UncertaintyType

SAME_OBJECT_IDENTITY_STATUSES = {
    IdentityStatus.USER_ASSERTED_SAME_OBJECT.value,
    IdentityStatus.SOURCE_ASSERTED_SAME_OBJECT.value,
}


def generate_prompts(
    signals: List[SignalResult],
    identity_status: str = IdentityStatus.NO_IDENTITY_CLAIM.value,
) -> List[PromptResult]:
    prompts: List[PromptResult] = []
    same_object = identity_status in SAME_OBJECT_IDENTITY_STATUSES
    for signal in signals:
        if signal.uncertainty_type == UncertaintyType.MISSINGNESS:
            coverage = signal.metric_value
            if coverage < 0.5:
                text = f"Low documentation coverage for '{signal.field}'. Inspect which selected witnesses lack this claim family."
            else:
                text = f"Documentation coverage for '{signal.field}' is broad within the selected research set."
        elif signal.uncertainty_type == UncertaintyType.TEXTUAL_DISAGREEMENT:
            if signal.details.get("reason") == "insufficient_values":
                text = f"Not enough validated values to summarize textual variation for '{signal.field}'."
            elif signal.metric_value < 0.7:
                if same_object:
                    text = f"Validated values for '{signal.field}' show possible disagreement about the asserted same object. Compare wording and granularity."
                else:
                    text = f"Validated values for '{signal.field}' show textual variation across selected witnesses. Do not treat this as evidence that one object has incompatible descriptions."
            else:
                text = f"Validated values for '{signal.field}' are textually similar within the selected research set."
        else:
            if signal.details.get("reason") == "field_not_image_relevant":
                text = f"Visual-text support is not applicable to '{signal.field}'."
            elif signal.metric_value < 0.6:
                text = f"Visual-text support is weak for '{signal.field}'. Check whether the text refers to visible form or historical/contextual facts."
            else:
                text = f"Visual-text support is present for '{signal.field}'."

        prompts.append(
            PromptResult(
                field=signal.field,
                uncertainty_type=signal.uncertainty_type,
                prompt=text,
                reasoning="Computed after claim review for the selected research set.",
            )
        )
    return prompts
