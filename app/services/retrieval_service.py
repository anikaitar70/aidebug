"""Session-scoped in-memory vector retrieval service."""

from __future__ import annotations

import hashlib
import logging
import re
import time
from typing import Any, Dict, List, Optional, Set, Tuple

import numpy as np

from app.services.query_classifier import (
    QueryIntent,
    assign_context_group,
    classify_query_intent,
    classify_top_k,
    extract_query_terms,
)
from app.services.session_store import SessionData, get_session_store

logger = logging.getLogger(__name__)

MAX_CHUNKS_PER_FILE = 2
MAX_CHUNKS_PER_SYMBOL = 1
MAX_CHUNKS_PER_CHUNK_TYPE = 1


class RetrievalService:
    """Handle session-scoped vector storage and retrieval."""

    def __init__(self) -> None:
        self._session_store = get_session_store()

    def _get_session(self, session_id: str) -> SessionData:
        return self._session_store.get_or_create(session_id)

    async def store_embedding(
        self,
        session_id: str,
        chunk_id: str,
        content: str,
        embedding: List[float],
        metadata: Dict[str, Any],
    ) -> bool:
        """Store embedding into the session's in-memory store."""
        try:
            fingerprint = self._content_fingerprint(content)
            metadata = {**metadata, "content_fingerprint": fingerprint}
            sanitized = self._sanitize_metadata(metadata)

            session = self._get_session(session_id)
            with self._session_store._lock:
                if fingerprint in session.fingerprints:
                    logger.debug("Skipping duplicate chunk fingerprint %s", fingerprint)
                    return True

                session.chunks[chunk_id] = {
                    "content": content,
                    "embedding": embedding,
                    "metadata": sanitized,
                }
                session.fingerprints.add(fingerprint)
                session.touch()

            logger.debug("Stored embedding for chunk %s in session %s", chunk_id, session_id)
            return True
        except Exception as exc:
            logger.error("Failed to store embedding for chunk %s: %s", chunk_id, exc)
            return False

    @staticmethod
    def _sanitize_metadata(metadata: Dict[str, Any]) -> Dict[str, Any]:
        """Ensure metadata values are JSON-serializable scalars."""
        sanitized: Dict[str, Any] = {}
        for key, value in metadata.items():
            if value is None:
                sanitized[key] = ""
            elif isinstance(value, (str, int, float, bool)):
                sanitized[key] = value
            else:
                sanitized[key] = str(value)
        return sanitized

    async def retrieve_similar(
        self,
        session_id: str,
        query_embedding: List[float],
        top_k: int = 5,
        filters: Optional[Dict[str, Any]] = None,
        query_text: Optional[str] = None,
        enhanced: bool = True,
    ) -> List[Dict[str, Any]]:
        """
        Retrieve top-k similar code chunks for a query embedding within a session.

        Pipeline: vector search → intent-aware rerank → flow reconstruction →
        targeted multi-hop → diversity filter → context grouping.
        """
        session = self._session_store.get(session_id)
        if session is None or not session.chunks:
            return []

        intent = classify_query_intent(query_text or "") if query_text else QueryIntent(
            primary="general", terms=()
        )
        effective_top_k = top_k
        query_terms: List[str] = []
        if enhanced and query_text:
            classified_k = classify_top_k(query_text, intent)
            effective_top_k = min(max(top_k, classified_k), 12 if intent.primary == "architecture" else 6)
            query_terms = extract_query_terms(query_text)

        fetch_k = min(max(effective_top_k * 3, effective_top_k + 10), 60)

        try:
            start = time.perf_counter()
            retrieved = self._retrieve_batch(query_embedding, session, fetch_k, filters)
            elapsed_ms = (time.perf_counter() - start) * 1000
            logger.debug(
                "Session retrieval session_id=%s intent=%s chunks=%d fetch_k=%d elapsed_ms=%.1f",
                session_id,
                intent.primary,
                session.chunk_count,
                fetch_k,
                elapsed_ms,
            )

            if enhanced and query_text:
                ranked = self._enhanced_rerank(retrieved, query_text, query_terms, intent, effective_top_k)
                flow = self._reconstruct_flow(session, intent, ranked, effective_top_k)
                merged = self._merge_unique(ranked, flow)
                expanded = await self._expand_neighbors(merged, session, intent, effective_top_k)
                with_hops = await self._multi_hop_expand(expanded, session, query_text, intent, effective_top_k)
                diverse = self._apply_diversity_filter(
                    with_hops, query_text, query_terms, intent, effective_top_k
                )
                return self._attach_context_groups(diverse, intent)

            return self._legacy_rerank_and_dedup(retrieved, effective_top_k)
        except Exception as exc:
            logger.error("Retrieval failed for session %s: %s", session_id, exc)
            return []

    def _retrieve_batch(
        self,
        query_embedding: List[float],
        session: SessionData,
        top_k: int,
        filters: Optional[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Batch cosine similarity search using numpy vector operations."""
        if not session.chunks:
            return []

        chunk_ids: List[str] = []
        embeddings: List[List[float]] = []
        contents: List[str] = []
        metadatas: List[Dict[str, Any]] = []

        for chunk_id, item in session.chunks.items():
            if filters and not all(item["metadata"].get(k) == v for k, v in filters.items()):
                continue
            chunk_ids.append(chunk_id)
            embeddings.append(item["embedding"])
            contents.append(item["content"])
            metadatas.append(item["metadata"])

        if not chunk_ids:
            return []

        query_vec = np.array(query_embedding, dtype=np.float32)
        matrix = np.array(embeddings, dtype=np.float32)

        query_norm = query_vec / (np.linalg.norm(query_vec) + 1e-8)
        norms = np.linalg.norm(matrix, axis=1, keepdims=True) + 1e-8
        normalized = matrix / norms

        similarities = normalized @ query_norm
        distances = 1.0 - similarities

        if top_k >= len(chunk_ids):
            top_indices = np.argsort(distances)
        else:
            top_indices = np.argpartition(distances, top_k)[:top_k]
            top_indices = top_indices[np.argsort(distances[top_indices])]

        results: List[Dict[str, Any]] = []
        for idx in top_indices:
            results.append({
                "chunk_id": chunk_ids[idx],
                "content": contents[idx],
                "distance": float(distances[idx]),
                "metadata": metadatas[idx],
            })
        return results

    def _merge_unique(
        self,
        primary: List[Dict[str, Any]],
        secondary: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Merge two result lists, preserving order and deduplicating by chunk_id."""
        seen: Set[str] = set()
        merged: List[Dict[str, Any]] = []
        for item in primary + secondary:
            cid = item["chunk_id"]
            if cid in seen:
                continue
            seen.add(cid)
            merged.append(item)
        return merged

    def _reconstruct_flow(
        self,
        session: SessionData,
        intent: QueryIntent,
        seeds: List[Dict[str, Any]],
        top_k: int,
    ) -> List[Dict[str, Any]]:
        """
        Build a call-graph slice for function-level questions.

        Retrieves definitions, callers, and direct callees for intent flow symbols.
        """
        if intent.primary not in ("jwt", "auth", "route", "function"):
            return []

        flow_symbols = {s.lower() for s in intent.flow_symbols}
        if not flow_symbols:
            for item in seeds[:3]:
                for sym in self._metadata_symbols(item.get("metadata", {})):
                    flow_symbols.add(sym.lower())

        if not flow_symbols:
            return []

        flow_results: List[Dict[str, Any]] = []
        seen_ids: Set[str] = set()

        def add(item: Dict[str, Any], expansion_type: str, distance: float = 0.25) -> None:
            if item["chunk_id"] in seen_ids:
                return
            copy = dict(item)
            copy["expansion_type"] = expansion_type
            copy["distance"] = min(float(copy.get("distance", distance)), distance)
            flow_results.append(copy)
            seen_ids.add(item["chunk_id"])

        for chunk_id, stored in session.chunks.items():
            meta = stored["metadata"]
            fn = str(meta.get("function_name") or "").lower()
            item = {
                "chunk_id": chunk_id,
                "content": stored["content"],
                "distance": 0.3,
                "metadata": meta,
            }

            if fn and fn in flow_symbols:
                add(item, "flow_definition", 0.2)

        seed_names = set()
        for item in seeds:
            for sym in self._metadata_symbols(item.get("metadata", {})):
                seed_names.add(sym.lower())

        target_calls = flow_symbols | seed_names
        for chunk_id, stored in session.chunks.items():
            meta = stored["metadata"]
            fn = str(meta.get("function_name") or "").lower()
            refs = str(meta.get("references") or "").lower()
            content_lower = stored["content"].lower()
            item = {
                "chunk_id": chunk_id,
                "content": stored["content"],
                "distance": 0.35,
                "metadata": meta,
            }

            for sym in target_calls:
                if not sym:
                    continue
                if sym == fn:
                    continue
                calls_sym = bool(re.search(rf"\b{re.escape(sym)}\s*\(", content_lower))
                refs_sym = sym in refs
                if calls_sym or refs_sym:
                    if self._intent_allows_chunk(item, intent):
                        add(item, "flow_caller" if calls_sym else "flow_reference", 0.32)

        return flow_results[: top_k * 2]

    def _apply_diversity_filter(
        self,
        results: List[Dict[str, Any]],
        query_text: str,
        query_terms: List[str],
        intent: QueryIntent,
        top_k: int,
    ) -> List[Dict[str, Any]]:
        """Select a diverse, intent-filtered final result set."""
        if not results:
            return results

        symbol_hits = self._count_symbol_hits(results, query_text, query_terms)
        for item in results:
            item["rank_score"] = self._enhanced_score_chunk(
                item, query_text, query_terms, symbol_hits, intent
            )

        results.sort(key=lambda item: item["rank_score"])

        diverse: List[Dict[str, Any]] = []
        seen_fingerprints: Set[str] = set()
        file_counts: Dict[str, int] = {}
        symbol_counts: Dict[str, int] = {}
        chunk_type_counts: Dict[str, int] = {}

        for item in results:
            if not self._intent_allows_chunk(item, intent):
                continue

            fp = self._item_fingerprint(item)
            if fp in seen_fingerprints:
                continue

            meta = item.get("metadata", {})
            file_path = str(meta.get("file_path") or meta.get("filename") or "unknown")
            symbol = self._chunk_symbol_key(item)
            chunk_type = str(meta.get("chunk_type") or "unknown")
            type_key = f"{symbol or file_path}::{chunk_type}"

            if file_counts.get(file_path, 0) >= MAX_CHUNKS_PER_FILE:
                continue
            if symbol and symbol_counts.get(symbol, 0) >= MAX_CHUNKS_PER_SYMBOL:
                continue
            if chunk_type_counts.get(type_key, 0) >= MAX_CHUNKS_PER_CHUNK_TYPE:
                continue

            if item.get("expansion_type") in ("reference", "flow_reference") and not self._intent_allows_chunk(
                item, intent, strict=True
            ):
                continue

            if (
                len(diverse) >= top_k - 1
                and not symbol
                and item.get("expansion_type") in ("reference", "neighbor", "flow_reference")
            ):
                continue

            seen_fingerprints.add(fp)
            file_counts[file_path] = file_counts.get(file_path, 0) + 1
            if symbol:
                symbol_counts[symbol] = symbol_counts.get(symbol, 0) + 1
            chunk_type_counts[type_key] = chunk_type_counts.get(type_key, 0) + 1
            diverse.append(item)
            if len(diverse) >= top_k:
                break

        for item in diverse:
            item.pop("rank_score", None)
        return diverse

    @staticmethod
    def _attach_context_groups(
        results: List[Dict[str, Any]],
        intent: QueryIntent,
    ) -> List[Dict[str, Any]]:
        for item in results:
            item["context_group"] = assign_context_group(item.get("metadata", {}), intent)
        return results

    @staticmethod
    def assemble_grouped_context(results: List[Dict[str, Any]]) -> List[str]:
        """Build context groups for LLM prompt assembly."""
        groups: Dict[str, List[Dict[str, Any]]] = {}
        for item in results:
            group = item.get("context_group") or "Context"
            groups.setdefault(group, []).append(item)

        formatted: List[str] = []
        for group_name, chunks in groups.items():
            parts = [f"=== {group_name} ==="]
            for chunk in chunks:
                meta = chunk.get("metadata", {})
                header_bits = []
                file_path = meta.get("file_path") or meta.get("filename") or "unknown"
                header_bits.append(f"File: {file_path}")
                if meta.get("function_name"):
                    header_bits.append(f"Function: {meta['function_name']}()")
                if meta.get("start_line") and meta.get("end_line"):
                    header_bits.append(f"Lines: {meta['start_line']}-{meta['end_line']}")
                parts.append(f"[{' | '.join(header_bits)}]\n{chunk.get('content', '')}")
            formatted.append("\n\n".join(parts))
        return formatted

    @staticmethod
    def _content_fingerprint(content: str) -> str:
        normalized = "\n".join(
            line.strip() for line in content.splitlines() if line.strip()
        )
        return hashlib.sha256(normalized.encode()).hexdigest()

    def _item_fingerprint(self, item: Dict[str, Any]) -> str:
        meta = item.get("metadata", {})
        stored = meta.get("content_fingerprint")
        if stored:
            return str(stored)
        return self._content_fingerprint(item.get("content", ""))

    @staticmethod
    def _chunk_symbol_key(item: Dict[str, Any]) -> str:
        meta = item.get("metadata", {})
        function_name = str(meta.get("function_name") or "").strip()
        class_name = str(meta.get("class_name") or "").strip()
        if function_name:
            file_path = str(meta.get("file_path") or meta.get("filename") or "")
            return f"{file_path}::{function_name}"
        if class_name:
            file_path = str(meta.get("file_path") or meta.get("filename") or "")
            return f"{file_path}::{class_name}"
        return ""

    def _intent_allows_chunk(
        self,
        item: Dict[str, Any],
        intent: QueryIntent,
        strict: bool = False,
    ) -> bool:
        """Return True if chunk is relevant to the classified query intent."""
        meta = item.get("metadata", {})
        function_name = str(meta.get("function_name") or "").lower()
        file_path = str(meta.get("file_path") or meta.get("filename") or "").lower()
        chunk_type = str(meta.get("chunk_type") or "").lower()
        content_lower = item.get("content", "").lower()
        refs = str(meta.get("references") or "").lower()
        imports = str(meta.get("imports") or "").lower()

        for ext in intent.penalize_extensions:
            if file_path.endswith(ext):
                return False

        if chunk_type in intent.penalize_chunk_types and not function_name and not meta.get("class_name"):
            if intent.primary in ("jwt", "function", "route", "auth"):
                return False

        if function_name in {s.lower() for s in intent.penalize_symbols}:
            return False

        if intent.primary == "jwt":
            jwt_symbols = {s.lower() for s in intent.boost_symbols | intent.flow_symbols}
            if function_name in jwt_symbols:
                return True
            if any(m in content_lower for m in intent.content_markers):
                return True
            if "jwt" in refs or "sign" in refs:
                return True
            if "jwt" in imports:
                return True
            if function_name in {"handlelogin", "handle_login"}:
                return True
            if strict:
                return False
            if function_name:
                return function_name not in {s.lower() for s in intent.penalize_symbols}
            return False

        if intent.primary == "auth":
            auth_symbols = {s.lower() for s in intent.boost_symbols | intent.flow_symbols}
            if function_name in auth_symbols:
                return True
            if any(m in content_lower for m in intent.content_markers):
                return True
            if strict and not function_name:
                return False
            return True

        if intent.primary in ("function", "route"):
            if function_name:
                return True
            if strict:
                return False
            return chunk_type in ("function", "method", "class")

        return True

    def _legacy_rerank_and_dedup(self, results: List[Dict[str, Any]], top_k: int) -> List[Dict[str, Any]]:
        for item in results:
            item["rank_score"] = self._legacy_score_chunk(item)

        results.sort(key=lambda item: item["rank_score"])

        unique_results: List[Dict[str, Any]] = []
        seen_fingerprints: Set[str] = set()
        for item in results:
            fp = self._item_fingerprint(item)
            if fp in seen_fingerprints:
                continue
            seen_fingerprints.add(fp)
            unique_results.append(item)
            if len(unique_results) >= top_k:
                break

        for item in unique_results:
            item.pop("rank_score", None)
        return unique_results

    def _enhanced_rerank(
        self,
        results: List[Dict[str, Any]],
        query_text: str,
        query_terms: List[str],
        intent: QueryIntent,
        top_k: int,
    ) -> List[Dict[str, Any]]:
        symbol_hits = self._count_symbol_hits(results, query_text, query_terms)

        for item in results:
            item["rank_score"] = self._enhanced_score_chunk(
                item, query_text, query_terms, symbol_hits, intent
            )

        results.sort(key=lambda item: item["rank_score"])

        unique_results: List[Dict[str, Any]] = []
        seen_fingerprints: Set[str] = set()
        for item in results:
            if not self._intent_allows_chunk(item, intent):
                continue
            fp = self._item_fingerprint(item)
            if fp in seen_fingerprints:
                continue
            seen_fingerprints.add(fp)
            unique_results.append(item)
            if len(unique_results) >= top_k * 2:
                break

        for item in unique_results:
            item.pop("rank_score", None)
        return unique_results

    def _count_symbol_hits(
        self,
        results: List[Dict[str, Any]],
        query_text: str,
        query_terms: List[str],
    ) -> Dict[str, int]:
        hits: Dict[str, int] = {}
        all_terms = set(query_terms) | {t.lower() for t in query_terms}

        for item in results:
            meta = item.get("metadata", {})
            content_lower = item.get("content", "").lower()
            symbols = self._metadata_symbols(meta)
            for sym in symbols:
                sym_lower = sym.lower()
                if sym_lower in all_terms or sym_lower in query_text.lower():
                    hits[sym] = hits.get(sym, 0) + 1
            for term in query_terms:
                if term in content_lower:
                    hits[term] = hits.get(term, 0) + 1
        return hits

    def _symbol_score(
        self,
        item: Dict[str, Any],
        intent: QueryIntent,
        query_terms: List[str],
    ) -> float:
        """Compute symbol-aware boost (higher = more relevant)."""
        meta = item.get("metadata", {})
        function_name = str(meta.get("function_name") or "")
        class_name = str(meta.get("class_name") or "")
        content_lower = item.get("content", "").lower()
        refs = str(meta.get("references") or "").lower()
        score = 0.0

        for sym in intent.boost_symbols:
            sym_lower = sym.lower()
            if function_name.lower() == sym_lower:
                score += 0.35
            elif sym_lower in class_name.lower():
                score += 0.25
            elif sym_lower in content_lower:
                score += 0.20
            elif sym_lower in refs:
                score += 0.15

        for sym in intent.penalize_symbols:
            if function_name.lower() == sym.lower():
                score -= 0.40

        for term in query_terms:
            if term in function_name.lower():
                score += 0.18
            if term in refs:
                score += 0.08

        for marker in intent.content_markers:
            if marker in content_lower:
                score += 0.12

        return score

    def _filename_score(self, item: Dict[str, Any], query_terms: List[str], intent: QueryIntent) -> float:
        meta = item.get("metadata", {})
        file_path = str(meta.get("file_path", "") or meta.get("filename", "")).lower()
        score = 0.0

        for term in query_terms:
            if term in file_path:
                score += 0.10

        if intent.primary == "jwt" and any(k in file_path for k in ("handler", "auth", "jwt")):
            score += 0.12
        if intent.primary == "auth" and any(k in file_path for k in ("auth", "login", "handler", "main")):
            score += 0.10
        if intent.primary in ("jwt", "function") and file_path.endswith((".html", ".md", ".json")):
            score -= 0.30

        return score

    def _enhanced_score_chunk(
        self,
        item: Dict[str, Any],
        query_text: str,
        query_terms: List[str],
        symbol_hits: Dict[str, int],
        intent: QueryIntent,
    ) -> float:
        """Combined score: semantic distance - boosts. Lower is better."""
        base_distance = float(item.get("distance", 0.0))

        expansion = item.get("expansion_type")
        if expansion in ("reference", "flow_reference"):
            base_distance = max(base_distance, 0.42)
        elif expansion == "neighbor":
            base_distance = max(base_distance, 0.38)
        elif expansion in ("flow_definition", "flow_caller"):
            base_distance = max(base_distance, 0.22)

        boost = 0.0
        meta = item.get("metadata", {})
        content = item.get("content", "")
        content_lower = content.lower()
        query_lower = query_text.lower()

        if self._contains_definition(content):
            boost += 0.06

        boost += self._symbol_score(item, intent, query_terms)
        boost += self._filename_score(item, query_terms, intent)

        function_name = str(meta.get("function_name", "")).lower()
        for sym, count in symbol_hits.items():
            sym_lower = sym.lower()
            if sym_lower in content_lower and count > 1:
                boost += min(0.04 * count, 0.12)

        if intent.primary == "auth":
            if "401" in query_lower or "fail" in query_lower or "invalid" in query_lower:
                if "401" in content or "invalid" in content_lower or "credentials" in content_lower:
                    boost += 0.18
                if function_name in ("handlelogin", "handle_login"):
                    boost += 0.15

        return max(base_distance - boost, 0.0)

    def _legacy_score_chunk(self, item: Dict[str, Any]) -> float:
        base_distance = float(item.get("distance", 0.0))
        boost = 0.08 if self._contains_definition(item.get("content", "")) else 0.0
        return max(base_distance - boost, 0.0)

    async def _expand_neighbors(
        self,
        results: List[Dict[str, Any]],
        session: SessionData,
        intent: QueryIntent,
        top_k: int,
    ) -> List[Dict[str, Any]]:
        if not results or intent.primary in ("jwt", "function"):
            return results

        seen_ids = {item["chunk_id"] for item in results}
        seen_fingerprints = {self._item_fingerprint(item) for item in results}
        expanded = list(results)

        for item in list(results):
            meta = item.get("metadata", {})
            file_id = meta.get("file_id")
            chunk_index = meta.get("chunk_index")
            if file_id is None or chunk_index is None:
                continue

            try:
                chunk_index = int(chunk_index)
            except (TypeError, ValueError):
                continue

            for neighbor_index in (chunk_index - 1, chunk_index + 1):
                if neighbor_index < 0:
                    continue
                neighbor = self._get_chunk_by_file_and_index(session, file_id, neighbor_index)
                if neighbor and neighbor["chunk_id"] not in seen_ids:
                    if not self._intent_allows_chunk(neighbor, intent):
                        continue
                    fp = self._item_fingerprint(neighbor)
                    if fp in seen_fingerprints:
                        continue
                    neighbor["expansion_type"] = "neighbor"
                    expanded.append(neighbor)
                    seen_ids.add(neighbor["chunk_id"])
                    seen_fingerprints.add(fp)

        return expanded[: top_k * 2]

    async def _multi_hop_expand(
        self,
        results: List[Dict[str, Any]],
        session: SessionData,
        query_text: str,
        intent: QueryIntent,
        top_k: int,
    ) -> List[Dict[str, Any]]:
        if not results:
            return results

        symbols: Set[str] = set(intent.flow_symbols)
        for item in results:
            if item.get("expansion_type", "").startswith("flow"):
                for sym in self._metadata_symbols(item.get("metadata", {})):
                    symbols.add(sym)

        if intent.primary == "jwt":
            symbols.update({"generateJWT", "jwt"})

        query_terms = extract_query_terms(query_text)
        for term in query_terms:
            if len(term) > 3 and intent.primary != "jwt":
                symbols.add(term)

        if not symbols:
            return results

        seen_ids = {item["chunk_id"] for item in results}
        seen_fingerprints = {self._item_fingerprint(item) for item in results}
        expanded = list(results)
        hop_results = self._find_references(session, symbols, limit=top_k * 2)

        for hop_item in hop_results:
            if hop_item.get("reference_score", 0) < 0.45:
                continue
            if not self._intent_allows_chunk(hop_item, intent, strict=True):
                continue
            if hop_item["chunk_id"] in seen_ids:
                continue
            fp = self._item_fingerprint(hop_item)
            if fp in seen_fingerprints:
                continue
            hop_item["expansion_type"] = "reference"
            expanded.append(hop_item)
            seen_ids.add(hop_item["chunk_id"])
            seen_fingerprints.add(fp)

        return expanded

    @staticmethod
    def _get_chunk_by_file_and_index(
        session: SessionData,
        file_id: str,
        chunk_index: int,
    ) -> Optional[Dict[str, Any]]:
        for chunk_id, item in session.chunks.items():
            meta = item["metadata"]
            if meta.get("file_id") == file_id and meta.get("chunk_index") == chunk_index:
                return {
                    "chunk_id": chunk_id,
                    "content": item["content"],
                    "distance": 0.5,
                    "metadata": meta,
                }
        return None

    def _find_references(
        self,
        session: SessionData,
        symbols: Set[str],
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        matches: List[Dict[str, Any]] = []
        symbol_list = sorted(symbols)[:30]

        for chunk_id, item in session.chunks.items():
            score = self._reference_match_score(
                item["content"], item["metadata"], symbol_list
            )
            if score > 0:
                matches.append({
                    "chunk_id": chunk_id,
                    "content": item["content"],
                    "distance": max(0.0, 1.0 - min(score, 1.0)),
                    "metadata": item["metadata"],
                    "reference_score": score,
                })

        matches.sort(key=lambda item: item.get("reference_score", 0), reverse=True)

        best_by_fingerprint: Dict[str, Dict[str, Any]] = {}
        for item in matches:
            fp = self._content_fingerprint(item.get("content", ""))
            if fp not in best_by_fingerprint:
                best_by_fingerprint[fp] = item

        deduped = sorted(
            best_by_fingerprint.values(),
            key=lambda item: item.get("reference_score", 0),
            reverse=True,
        )
        return deduped[:limit]

    def _reference_match_score(
        self,
        content: str,
        metadata: Dict[str, Any],
        symbols: List[str],
    ) -> float:
        score = 0.0
        content_lower = content.lower()
        meta_symbols = {s.lower() for s in self._metadata_symbols(metadata)}

        for sym in symbols:
            sym_lower = sym.lower()
            if sym_lower in meta_symbols:
                score += 0.3
            if re.search(rf"\b{re.escape(sym_lower)}\s*\(", content_lower):
                score += 0.5
            elif sym_lower in content_lower:
                score += 0.2

        refs = str(metadata.get("references", "")).lower()
        for sym in symbols:
            if sym.lower() in refs:
                score += 0.15

        return score

    @staticmethod
    def _metadata_symbols(metadata: Dict[str, Any]) -> List[str]:
        symbols: List[str] = []
        for key in ("function_name", "class_name"):
            value = metadata.get(key, "")
            if value and str(value).strip():
                symbols.append(str(value).strip())
        return symbols

    @staticmethod
    def _extract_callable_symbols(content: str) -> Set[str]:
        symbols: Set[str] = set()
        for match in re.finditer(r"\b(?:def|function|async function)\s+(\w+)", content):
            symbols.add(match.group(1))
        for match in re.finditer(r"\b([a-zA-Z_][a-zA-Z0-9_]*)\s*\(", content):
            name = match.group(1)
            if name not in {"if", "for", "while", "return", "catch", "switch"}:
                symbols.add(name)
        return symbols

    def _contains_definition(self, content: str) -> bool:
        normalized = content.lower()
        markers = [
            "def ", "function ", "async ", "class ",
            "fn ", "func ", "public ", "private ", "protected ",
        ]
        return any(marker in normalized for marker in markers)

    async def delete_chunks(self, session_id: str, file_id: str) -> bool:
        """Delete all stored chunks for a file identifier within a session."""
        try:
            session = self._session_store.get(session_id)
            if session is None:
                return True

            with self._session_store._lock:
                to_delete = [
                    chunk_id
                    for chunk_id, item in session.chunks.items()
                    if item["metadata"].get("file_id") == file_id
                ]
                for chunk_id in to_delete:
                    fp = session.chunks[chunk_id]["metadata"].get("content_fingerprint")
                    if fp:
                        session.fingerprints.discard(fp)
                    del session.chunks[chunk_id]

            logger.debug("Deleted chunks for file %s in session %s", file_id, session_id)
            return True
        except Exception as exc:
            logger.error("Failed to delete chunks for file %s: %s", file_id, exc)
            return False

    def get_chunk_count(self, session_id: str) -> int:
        return self._session_store.chunk_count(session_id)


_retrieval_service: Optional[RetrievalService] = None


async def get_retrieval_service() -> RetrievalService:
    """Get retrieval service instance."""
    global _retrieval_service
    if _retrieval_service is None:
        _retrieval_service = RetrievalService()
    return _retrieval_service
