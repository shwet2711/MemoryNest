from __future__ import annotations

from typing import Any


def evaluate_retrieval_results(
    results: list[dict[str, Any]],
    *,
    max_distance: float,
) -> dict[str, Any]:
    """
    Evaluate the quality of retrieved RAG results.

    This function does not call an LLM. It provides lightweight,
    deterministic diagnostics based on retrieval distance and
    available source information.
    """

    if not isinstance(results, list):
        raise ValueError("results must be a list.")

    if not isinstance(max_distance, (int, float)):
        raise ValueError(
            "max_distance must be a number."
        )

    if max_distance < 0:
        raise ValueError(
            "max_distance must be non-negative."
        )

    distances: list[float] = []
    sources: list[str] = []

    for result in results:
        if not isinstance(result, dict):
            continue

        distance = result.get("distance")

        if isinstance(distance, (int, float)):
            distances.append(float(distance))

        metadata = result.get("metadata") or {}

        if isinstance(metadata, dict):
            source = metadata.get("source_filename")

            if source:
                source_name = str(source)

                if source_name not in sources:
                    sources.append(source_name)

    result_count = len(results)

    if not distances:
        return {
            "status": "no_results",
            "result_count": result_count,
            "average_distance": None,
            "best_distance": None,
            "worst_distance": None,
            "source_count": len(sources),
            "sources": sources,
            "confidence": 0.0,
        }

    best_distance = min(distances)
    worst_distance = max(distances)
    average_distance = sum(distances) / len(distances)

    if best_distance <= max_distance * 0.50:
        status = "strong"
        confidence = 1.0
    elif best_distance <= max_distance * 0.75:
        status = "good"
        confidence = 0.75
    elif best_distance <= max_distance:
        status = "moderate"
        confidence = 0.50
    else:
        status = "weak"
        confidence = 0.25

    return {
        "status": status,
        "result_count": result_count,
        "average_distance": average_distance,
        "best_distance": best_distance,
        "worst_distance": worst_distance,
        "source_count": len(sources),
        "sources": sources,
        "confidence": confidence,
    }


def evaluate_rag_context(
    *,
    results: list[dict[str, Any]],
    context: str,
    max_distance: float,
    grounding_distance: float | None = None,
) -> dict[str, Any]:
    """
    Evaluate both retrieved results and the final RAG context.

    Retrieval distance determines whether the chunks are worth
    considering. A separate grounding distance determines whether
    the strongest retrieved evidence is strong enough for grounded
    answer generation.

    This evaluation is query-agnostic and does not depend on any
    specific question type.
    """

    if not isinstance(context, str):
        raise ValueError(
            "context must be a string."
        )

    if grounding_distance is None:
        grounding_distance = max_distance

    if not isinstance(
        grounding_distance,
        (int, float),
    ):
        raise ValueError(
            "grounding_distance must be a number."
        )

    if grounding_distance < 0:
        raise ValueError(
            "grounding_distance must be non-negative."
        )

    evaluation = evaluate_retrieval_results(
        results,
        max_distance=max_distance,
    )

    context_length = len(context.strip())

    evaluation.update(
        {
            "context_available": bool(context.strip()),
            "context_length": context_length,
        }
    )

    best_distance = evaluation.get("best_distance")

    grounding_ready = (
        bool(results)
        and bool(context.strip())
        and isinstance(best_distance, (int, float))
        and best_distance <= grounding_distance
    )

    evaluation["grounding_distance"] = grounding_distance
    evaluation["grounding_ready"] = grounding_ready

    return evaluation
