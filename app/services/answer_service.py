
from __future__ import annotations

import os
from typing import Any

import requests
from dotenv import load_dotenv

from app.core.config import RAG_GROUNDING_DISTANCE
from app.services.hybrid_retrieval_service import retrieve_hybrid_context
from app.services.prompt_service import build_chat_prompt
from app.services.rag_evaluation_service import evaluate_rag_context
from app.services.rag_service import get_rag_context
from app.services.retrieval_service import get_max_distance


load_dotenv()


DEFAULT_OLLAMA_URL = "http://localhost:11434"
DEFAULT_TIMEOUT = 180


class SourceInfo(dict):
    """
    Structured source information.

    Supports dictionary access and filename comparisons for
    compatibility with existing MemoryNest code and tests.
    """

    def __eq__(self, other: object) -> bool:
        if isinstance(other, str):
            return self.get("filename") == other

        return dict.__eq__(self, other)


def get_ollama_url() -> str:
    """Return the configured Ollama base URL."""
    return os.getenv("OLLAMA_BASE_URL", DEFAULT_OLLAMA_URL).rstrip("/")


def get_ollama_model() -> str:
    """Return the configured Ollama model name."""
    return os.getenv("OLLAMA_MODEL", "").strip()


def is_ollama_available() -> bool:
    """Check whether the local Ollama service is reachable."""
    try:
        response = requests.get(
            f"{get_ollama_url()}/api/tags",
            timeout=5,
        )
        return response.status_code == 200
    except requests.RequestException:
        return False


def generate_with_ollama(
    *,
    system_prompt: str,
    user_prompt: str,
    model: str | None = None,
    timeout: int = DEFAULT_TIMEOUT,
    num_predict: int | None = None,
) -> str:
    """Generate an answer using the local Ollama model."""
    selected_model = model.strip() if model else get_ollama_model()

    if not selected_model:
        raise ValueError("OLLAMA_MODEL is not configured.")

    payload = {
        "model": selected_model,
        "system": system_prompt,
        "prompt": user_prompt,
        "stream": False,
    }

    if num_predict is not None:
        payload["options"] = {
            "num_predict": num_predict,
        }

    response = requests.post(
        f"{get_ollama_url()}/api/generate",
        json=payload,
        timeout=timeout,
    )

    response.raise_for_status()

    data = response.json()
    answer = data.get("response", "").strip()

    if not answer:
        raise RuntimeError("Ollama returned an empty response.")

    return answer


def _extract_sources(
    results: list[dict[str, Any]],
) -> list[SourceInfo]:
    """Build unique structured sources from vector-retrieved results."""
    sources: list[SourceInfo] = []
    seen: set[tuple[Any, ...]] = set()

    for result in results:
        if not isinstance(result, dict):
            continue

        metadata = result.get("metadata") or {}

        if not isinstance(metadata, dict):
            continue

        filename = metadata.get("source_filename")

        if not filename:
            continue

        page_number = metadata.get("page_number")
        chunk_index = metadata.get("chunk_index")
        distance = result.get("distance")
        document_id = metadata.get("document_id")

        source_key = (
            str(filename),
            page_number,
            chunk_index,
            document_id,
        )

        if source_key in seen:
            continue

        seen.add(source_key)

        sources.append(
            SourceInfo(
                filename=str(filename),
                page_number=page_number,
                chunk_index=chunk_index,
                distance=distance,
                document_id=document_id,
                evidence_type="vector",
            )
        )

    return sources


def _include_hybrid_evidence(
    *,
    user_id: int,
    query: str,
    document_id: int | None,
    top_k: int,
    vector_results: list[dict[str, Any]],
    context: str,
    sources: list[SourceInfo],
) -> tuple[str, list[SourceInfo], list[dict[str, Any]]]:
    """
    Fuse previously retrieved vector results with graph evidence.

    Reuses vector results to avoid repeating vector retrieval.
    This function does not evaluate or change vector grounding.
    """
    try:
        hybrid_data = retrieve_hybrid_context(
            user_id=user_id,
            query=query,
            top_k=top_k,
            document_id=document_id,
            vector_results=vector_results,
        )
    except Exception:
        # Hybrid retrieval is supplementary. Preserve normal RAG behavior
        # if the hybrid service unexpectedly fails.
        return context, sources, []

    if not isinstance(hybrid_data, dict):
        return context, sources, []

    hybrid_context = hybrid_data.get("context")

    if isinstance(hybrid_context, str) and hybrid_context.strip():
        context = hybrid_context

    hybrid_results = hybrid_data.get("results", [])

    if not isinstance(hybrid_results, list):
        hybrid_results = []

    hybrid_sources = hybrid_data.get("sources", [])

    if not isinstance(hybrid_sources, list):
        hybrid_sources = []

    # Keep detailed vector sources, including page and distance metadata.
    # Add supplementary Knowledge Graph sources without duplicating them.
    existing_source_keys = {
        (
            source.get("filename"),
            source.get("page_number"),
            source.get("chunk_index"),
            source.get("document_id"),
            source.get("evidence_type", "vector"),
        )
        for source in sources
    }

    for hybrid_source in hybrid_sources:
        if not isinstance(hybrid_source, dict):
            continue

        evidence_type = hybrid_source.get("evidence_type")

        if evidence_type == "vector":
            # Vector sources were already extracted from the original
            # RAG results and retain their detailed metadata.
            continue

        if evidence_type != "knowledge_graph":
            continue

        filename = hybrid_source.get("filename")

        if not isinstance(filename, str) or not filename.strip():
            continue

        page_number = None
        chunk_index = hybrid_source.get("chunk_index")
        source_document_id = hybrid_source.get("document_id")

        source_key = (
            filename,
            page_number,
            chunk_index,
            source_document_id,
            "knowledge_graph",
        )

        if source_key in existing_source_keys:
            continue

        sources.append(
            SourceInfo(
                filename=filename,
                page_number=page_number,
                chunk_index=chunk_index,
                distance=None,
                document_id=source_document_id,
                evidence_type="knowledge_graph",
            )
        )

        existing_source_keys.add(source_key)

    return context, sources, hybrid_results


def answer_query(
    *,
    user_id: int,
    query: str,
    top_k: int = 5,
    document_id: int | None = None,
    use_ollama: bool = False,
) -> dict[str, Any]:
    """
    Retrieve relevant document context and optionally generate
    an answer using the local Ollama model.

    Grounding is evaluated against the original vector evidence before
    supplementary Knowledge Graph evidence is used for generation.
    """

    # ---------------------------------------------------------
    # Input validation
    # ---------------------------------------------------------

    if (
        isinstance(user_id, bool)
        or not isinstance(user_id, int)
        or user_id <= 0
    ):
        raise ValueError("user_id must be a positive integer.")

    if not isinstance(query, str) or not query.strip():
        raise ValueError("query must be a non-empty string.")

    if (
        isinstance(top_k, bool)
        or not isinstance(top_k, int)
        or top_k <= 0
    ):
        raise ValueError("top_k must be a positive integer.")

    if document_id is not None:
        if (
            isinstance(document_id, bool)
            or not isinstance(document_id, int)
            or document_id <= 0
        ):
            raise ValueError(
                "document_id must be a positive integer."
            )

    clean_query = query.strip()

    # ---------------------------------------------------------
    # Retrieve original RAG context
    # ---------------------------------------------------------

    rag_data = get_rag_context(
        user_id=user_id,
        query=clean_query,
        top_k=top_k,
        document_id=document_id,
    )

    if not isinstance(rag_data, dict):
        raise ValueError("RAG service returned an invalid response.")

    results = rag_data.get("results", [])
    context = rag_data.get("context", "")

    if not isinstance(results, list):
        results = []

    if not isinstance(context, str):
        context = ""

    # ---------------------------------------------------------
    # Preserve RAG metadata
    # ---------------------------------------------------------

    result_document_id = rag_data.get("document_id")

    if result_document_id is None:
        result_document_id = document_id

    result_top_k = rag_data.get("top_k")

    if result_top_k is None:
        result_top_k = top_k

    has_context_value = rag_data.get("has_context")

    if isinstance(has_context_value, bool):
        has_context = has_context_value
    else:
        has_context = bool(results) or bool(context.strip())

    # ---------------------------------------------------------
    # Build structured vector sources
    # ---------------------------------------------------------

    sources = _extract_sources(results)

    # ---------------------------------------------------------
    # Explicit no-context compatibility path
    # ---------------------------------------------------------

    if has_context_value is False:
        return {
            "answer": (
                "I couldn't find enough information in your documents."
            ),
            "mode": "retrieval_only",
            "sources": [],
            "results": [],
            "context": "",
            "document_id": result_document_id,
            "top_k": result_top_k,
            "ollama_available": False,
        }

    # ---------------------------------------------------------
    # No context inferred from response
    # ---------------------------------------------------------

    if not has_context:
        return {
            "answer": (
                "I couldn't find enough information in your documents."
            ),
            "mode": "fallback",
            "sources": [],
            "results": [],
            "context": "",
            "document_id": result_document_id,
            "top_k": result_top_k,
            "ollama_available": False,
        }

    # ---------------------------------------------------------
    # Context exists but Ollama is disabled
    # ---------------------------------------------------------

    if not use_ollama:
        mode = (
            "retrieval_only"
            if has_context_value is True
            else "retrieval"
        )

        hybrid_results: list[dict[str, Any]] = []

        # Preserve legacy behavior for responses that do not explicitly
        # declare has_context=True.
        if has_context_value is True:
            context, sources, hybrid_results = _include_hybrid_evidence(
                user_id=user_id,
                query=clean_query,
                document_id=result_document_id,
                top_k=top_k,
                vector_results=results,
                context=context,
                sources=sources,
            )

        return {
            "answer": (
                "I found relevant information in your documents. "
                "Ollama is not being used yet. The retrieved passages "
                "are available below as supporting context."
            ),
            "mode": mode,
            "sources": sources,
            "results": results,
            "hybrid_results": hybrid_results,
            "context": context,
            "document_id": result_document_id,
            "top_k": result_top_k,
            "ollama_available": is_ollama_available(),
        }

    # ---------------------------------------------------------
    # Context exists but Ollama is unavailable
    # ---------------------------------------------------------

    # Preserve retrieval-only behavior when the local model is offline.
    # No generated answer is produced in this branch.
    if not is_ollama_available():
        context, sources, hybrid_results = _include_hybrid_evidence(
            user_id=user_id,
            query=clean_query,
            document_id=result_document_id,
            top_k=top_k,
            vector_results=results,
            context=context,
            sources=sources,
        )

        return {
            "answer": (
                "I found relevant information in your documents, "
                "but the local Ollama service is currently unavailable."
            ),
            "mode": "retrieval_only",
            "sources": sources,
            "results": results,
            "hybrid_results": hybrid_results,
            "context": context,
            "document_id": result_document_id,
            "top_k": result_top_k,
            "ollama_available": False,
        }

    # ---------------------------------------------------------
    # Evaluate vector grounding before Ollama generation
    # ---------------------------------------------------------

    # Only the original vector results and vector context are evaluated.
    # Knowledge Graph evidence cannot make weak grounding pass.
    rag_evaluation = evaluate_rag_context(
        results=results,
        context=context,
        max_distance=get_max_distance(),
        grounding_distance=RAG_GROUNDING_DISTANCE,
    )

    if not rag_evaluation["grounding_ready"]:
        return {
            "answer": (
                "I couldn't find enough information in your documents."
            ),
            "mode": "fallback",
            "sources": [],
            "results": results,
            "context": context,
            "document_id": result_document_id,
            "top_k": result_top_k,
            "ollama_available": True,
            "rag_evaluation": rag_evaluation,
        }

    # ---------------------------------------------------------
    # Add hybrid evidence after grounding passes
    # ---------------------------------------------------------

    context, sources, hybrid_results = _include_hybrid_evidence(
        user_id=user_id,
        query=clean_query,
        document_id=result_document_id,
        top_k=top_k,
        vector_results=results,
        context=context,
        sources=sources,
    )

    # ---------------------------------------------------------
    # Build Ollama prompts
    # ---------------------------------------------------------

    prompts = build_chat_prompt(
        query=clean_query,
        context=context,
    )

    # ---------------------------------------------------------
    # Generate final answer
    # ---------------------------------------------------------

    try:
        answer = generate_with_ollama(
            system_prompt=prompts["system"],
            user_prompt=prompts["user"],
        )

        return {
            "answer": answer,
            "mode": "ollama",
            "sources": sources,
            "results": results,
            "hybrid_results": hybrid_results,
            "context": context,
            "document_id": result_document_id,
            "top_k": result_top_k,
            "ollama_available": True,
            "rag_evaluation": rag_evaluation,
        }

    except Exception as exc:
        return {
            "answer": (
                "I retrieved relevant information from your documents, "
                "but the local AI model could not generate the final answer."
            ),
            "mode": "retrieval_only",
            "sources": sources,
            "results": results,
            "hybrid_results": hybrid_results,
            "context": context,
            "document_id": result_document_id,
            "top_k": result_top_k,
            "ollama_available": True,
            "rag_evaluation": rag_evaluation,
            "error": str(exc),
        }
