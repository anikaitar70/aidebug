"""Generate project description and sample questions without calling Gemini."""

from __future__ import annotations

import re
from collections import Counter
from typing import Any, Dict, List, Set, Tuple

from app.utils.path_filters import categorize_indexed_path

_QUESTION_RULES: List[Tuple[re.Pattern, str]] = [
    (re.compile(r"classif|predict|model|inference|ml|train", re.I), "How does it classify the text?"),
    (re.compile(r"model|sklearn|pytorch|tensorflow|bert", re.I), "Which model is used for predictions?"),
    (re.compile(r"predict|inference", re.I), "How does the prediction flow work?"),
    (re.compile(r"auth|login|jwt|password|session", re.I), "How does authentication work?"),
    (re.compile(r"route|endpoint|handler|api", re.I), "What API endpoints are defined?"),
    (re.compile(r"database|db|sql|mongo|postgres", re.I), "How is the database accessed?"),
    (re.compile(r"train", re.I), "How is the model trained?"),
    (re.compile(r"frontend|component|app\.(js|tsx)", re.I), "How does the frontend interact with the backend?"),
    (re.compile(r"service", re.I), "What do the service layers do?"),
    (re.compile(r"config|settings", re.I), "How is the application configured?"),
]

_GENERIC_QUESTIONS = [
    "What is the overall architecture of this project?",
    "What is the main entry point of the application?",
    "Which are the most important functions in this codebase?",
    "How is data processed end to end?",
    "What technologies and frameworks does this project use?",
]


def _collect_session_signals(session_chunks: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    paths: List[str] = []
    languages: Counter = Counter()
    symbols: Set[str] = set()
    path_blob = ""

    for item in session_chunks.values():
        meta = item.get("metadata", {})
        fp = str(meta.get("file_path") or meta.get("filename") or "")
        if fp:
            paths.append(fp)
            path_blob += " " + fp.lower()
        lang = str(meta.get("language") or "")
        if lang and lang != "unknown":
            languages[lang] += 1
        for key in ("function_name", "class_name"):
            val = str(meta.get(key) or "").strip()
            if val:
                symbols.add(val)

    categories: Counter = Counter()
    for p in set(paths):
        categories[categorize_indexed_path(p)] += 1

    return {
        "paths": paths,
        "unique_paths": sorted(set(paths)),
        "path_blob": path_blob,
        "languages": languages,
        "symbols": sorted(symbols)[:40],
        "categories": categories,
    }


def _build_description(signals: Dict[str, Any], total_chunks: int) -> str:
    paths = signals["unique_paths"]
    cats = signals["categories"]
    langs = signals["languages"]

    if not paths:
        return "No indexed files found for this project."

    parts = [
        f"This project contains {len(paths)} source file(s) "
        f"indexed as {total_chunks} searchable code chunk(s)."
    ]

    lang_list = [f"{lang} ({count})" for lang, count in langs.most_common(5)]
    if lang_list:
        parts.append(f"Languages: {', '.join(lang_list)}.")

    area_bits = []
    for label, key in (
        ("backend", "backend"),
        ("frontend", "frontend"),
        ("tests", "tests"),
        ("services", "other"),
    ):
        count = cats.get(key, 0)
        if count:
            area_bits.append(f"{count} {label}")

    if area_bits:
        parts.append(f"Areas detected: {', '.join(area_bits)}.")

    notable = [p for p in paths if not any(x in p.lower() for x in (".test.", "/test", "node_modules"))][:8]
    if notable:
        names = ", ".join(p.split("/")[-1] for p in notable[:6])
        parts.append(f"Key files include: {names}.")

    if signals["symbols"]:
        sym_preview = ", ".join(signals["symbols"][:8])
        parts.append(f"Notable symbols: {sym_preview}.")

    return " ".join(parts)


def _build_sample_questions(signals: Dict[str, Any]) -> List[str]:
    blob = signals["path_blob"] + " " + " ".join(signals["symbols"]).lower()
    chosen: List[str] = []
    seen: Set[str] = set()

    for pattern, question in _QUESTION_RULES:
        if pattern.search(blob) and question not in seen:
            chosen.append(question)
            seen.add(question)
        if len(chosen) >= 5:
            return chosen[:5]

    for q in _GENERIC_QUESTIONS:
        if q not in seen:
            chosen.append(q)
            seen.add(q)
        if len(chosen) >= 5:
            break

    return chosen[:5]


def generate_project_overview(session_chunks: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    """Build description + 5 sample questions from indexed metadata (no LLM call)."""
    signals = _collect_session_signals(session_chunks)
    total_chunks = len(session_chunks)
    description = _build_description(signals, total_chunks)
    questions = _build_sample_questions(signals)

    return {
        "description": description,
        "sample_questions": questions,
        "total_files": len(signals["unique_paths"]),
        "total_chunks": total_chunks,
        "languages": dict(signals["languages"]),
        "top_files": [p.split("/")[-1] for p in signals["unique_paths"][:10]],
    }
