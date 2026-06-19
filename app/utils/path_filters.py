"""Repository path filtering and code-importance scoring for indexing and retrieval."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional, Tuple

# Directories that must never be indexed
EXCLUDED_DIR_NAMES = frozenset({
    "node_modules",
    "dist",
    "build",
    "coverage",
    ".next",
    ".cache",
    "venv",
    ".venv",
    "__pycache__",
    ".git",
    "logs",
    "tmp",
})

EXCLUDED_FILE_NAMES = frozenset({
    "package-lock.json",
    "yarn.lock",
})

EXCLUDED_SUFFIXES = (
    ".min.js",
    ".map",
)

# Implementation source extensions (Phase 8)
IMPLEMENTATION_EXTENSIONS = frozenset({
    ".py", ".ts", ".tsx", ".js", ".java", ".go", ".rs",
})

# Highest-priority path segments for ML / backend implementation
HIGH_PRIORITY_SEGMENTS = (
    "classifier", "classify", "model", "predict", "prediction",
    "inference", "train", "training", "ml", "machine_learning",
    "services", "service", "backend", "app/services",
    "bert", "tfidf", "sklearn", "tensorflow", "pytorch",
)

MEDIUM_PRIORITY_SEGMENTS = (
    "frontend/src", "components", "hooks", "lib", "utils",
)

LOW_PRIORITY_SEGMENTS = (
    "test", "tests", "__tests__", "spec", "config", "settings",
)

VERY_LOW_PRIORITY_SEGMENTS = (
    "node_modules", "dist", "build", "coverage", ".next",
    "generated", "vendor", "third_party",
)

TEST_FILE_PATTERN = re.compile(
    r"(^|/)(test_|tests/|__tests__/|.*\.test\.|.*\.spec\.)",
    re.IGNORECASE,
)

GENERATED_FILE_PATTERN = re.compile(
    r"(\.generated\.|\.g\.|_pb2\.|\.min\.|/dist/|/build/)",
    re.IGNORECASE,
)


def _normalize_path(path: str) -> str:
    return path.replace("\\", "/").strip("/")


def _path_parts(path: str) -> Tuple[str, ...]:
    return tuple(p for p in _normalize_path(path).split("/") if p)


def should_index_path(path: str) -> bool:
    """Return False for dependency, build, cache, and generated paths."""
    normalized = _normalize_path(path)
    if not normalized:
        return False

    name = Path(normalized).name.lower()
    if name in EXCLUDED_FILE_NAMES:
        return False

    lower = normalized.lower()
    for suffix in EXCLUDED_SUFFIXES:
        if lower.endswith(suffix):
            return False

    for part in _path_parts(normalized):
        if part.lower() in EXCLUDED_DIR_NAMES:
            return False

    return True


def categorize_indexed_path(path: str) -> str:
    """Classify a file path for indexing audits."""
    normalized = _normalize_path(path).lower()
    parts = _path_parts(normalized)

    if any(p == "node_modules" for p in parts):
        return "node_modules"
    if any(p in {"dist", "build", "coverage", ".next", ".cache"} for p in parts):
        return "build"
    if TEST_FILE_PATTERN.search(f"/{normalized}"):
        return "tests"
    if any(p in {"frontend", "client", "ui", "public"} for p in parts):
        return "frontend"
    if any(p in {"backend", "server", "api", "app", "services", "src"} for p in parts):
        return "backend"
    if GENERATED_FILE_PATTERN.search(f"/{normalized}"):
        return "generated"
    return "other"


def compute_path_importance(file_path: str) -> float:
    """
    Score path importance for retrieval ranking.

    Returns a value in [0.0, 1.0] where higher means more implementation-relevant.
    """
    normalized = _normalize_path(file_path).lower()
    score = 0.50  # neutral baseline

    for seg in VERY_LOW_PRIORITY_SEGMENTS:
        if seg in normalized:
            return 0.05

    if TEST_FILE_PATTERN.search(f"/{normalized}"):
        score = min(score, 0.25)

    for seg in LOW_PRIORITY_SEGMENTS:
        if seg in normalized:
            score = min(score, 0.30)

    ext = Path(normalized).suffix.lower()
    if ext in IMPLEMENTATION_EXTENSIONS:
        score += 0.05
    elif ext in {".md", ".txt", ".json", ".yaml", ".yml"}:
        score = min(score, 0.35)

    for seg in MEDIUM_PRIORITY_SEGMENTS:
        if seg in normalized:
            score = max(score, 0.55)

    for seg in HIGH_PRIORITY_SEGMENTS:
        if seg in normalized:
            score = max(score, 0.90)

    # Filename-level boosts for classifier/model files
    stem = Path(normalized).stem.lower()
    if stem in {"classifier", "model", "predict", "inference", "train"}:
        score = max(score, 0.95)
    if "classif" in stem or "predict" in stem or "inference" in stem:
        score = max(score, 0.92)

    return min(max(score, 0.0), 1.0)


def path_importance_boost(file_path: str) -> float:
    """Convert path importance into a retrieval rank boost (lower rank_score is better)."""
    importance = compute_path_importance(file_path)
    # Map [0, 1] → boost up to 0.40 for top implementation paths
    return importance * 0.40


def path_importance_penalty(file_path: str) -> float:
    """Penalty added to rank_score for low-value paths (higher = worse)."""
    importance = compute_path_importance(file_path)
    if importance <= 0.10:
        return 0.50
    if importance <= 0.25:
        return 0.30
    if importance <= 0.35:
        return 0.15
    return 0.0


def is_excluded_at_retrieval(file_path: str) -> bool:
    """Safety net: exclude junk paths even if they were indexed before filtering."""
    return not should_index_path(file_path)


def matches_ml_path_keywords(file_path: str, keywords: Tuple[str, ...]) -> bool:
    """Check whether a file path matches ML-related keywords."""
    normalized = _normalize_path(file_path).lower()
    return any(kw in normalized for kw in keywords)


def audit_indexed_paths(paths: list[str]) -> dict:
    """Summarize indexed file distribution for repository audits."""
    categories = {
        "frontend": 0,
        "backend": 0,
        "tests": 0,
        "node_modules": 0,
        "build": 0,
        "generated": 0,
        "other": 0,
    }
    for path in paths:
        cat = categorize_indexed_path(path)
        categories[cat] = categories.get(cat, 0) + 1
    return {
        "total_files": len(paths),
        "by_category": categories,
        "node_modules_indexed": categories["node_modules"] > 0,
        "build_artifacts_indexed": categories["build"] > 0,
        "tests_indexed": categories["tests"] > 0,
        "dependency_sources_indexed": categories["node_modules"] > 0,
    }
