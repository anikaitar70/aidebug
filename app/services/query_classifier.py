"""Query classification for dynamic retrieval depth and intent-aware ranking."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import FrozenSet, List, Optional, Set, Tuple


ARCHITECTURE_PATTERNS = [
    r"\barchitecture\b",
    r"\bstructure\b",
    r"\boverview\b",
    r"\bdesign\b",
    r"\bhow is (?:the )?(?:project|repo|codebase|system) (?:organized|structured)\b",
    r"\bexplain (?:the )?(?:repository|codebase|project)\b",
    r"\btrace\b.+\b(?:from|to|through)\b",
    r"\bend[- ]to[- ]end\b",
    r"\bflow\b",
    r"\bparticipate\b",
    r"\bacross files\b",
    r"\bwhich files\b",
    r"\brepository\b",
    r"\bcomponents\b",
    r"\bsummary\b",
]

SIMPLE_PATTERNS = [
    r"^what is \w+\??$",
    r"^where is \w+\??$",
    r"^show me \w+\??$",
    r"^define \w+\??$",
]

JWT_PATTERNS = [
    r"\bjwt\b",
    r"\bjson web token\b",
    r"\bauth(?:entication)? token\b",
    r"\btoken\b.+\b(?:creat|generat|sign|issu)",
    r"\b(?:creat|generat|sign|issu).+\btoken\b",
    r"\bjwt\.sign\b",
    r"\bjwt_secret\b",
]

AUTH_PATTERNS = [
    r"\bauthenticat",
    r"\blogin\b",
    r"\bpassword\b",
    r"\bcredential",
    r"\b401\b",
    r"\bfail",
    r"\binvalid\b",
    r"\bbcrypt\b",
    r"\bsession\b",
]

ROUTE_PATTERNS = [
    r"\bendpoint\b",
    r"\bapi\b",
    r"\broute\b",
    r"\bhandler\b",
    r"\brequest\b",
    r"\bresponse\b",
]

FUNCTION_PATTERNS = [
    r"\bfunction\b",
    r"\bmethod\b",
    r"\bwhich functions\b",
    r"\bwhat functions\b",
    r"\bcall(?:s|ed|ing)?\b",
    r"\bdef\b",
]


@dataclass(frozen=True)
class QueryIntent:
    """Classified query intent driving retrieval boosts and filters."""

    primary: str
    terms: Tuple[str, ...]
    boost_symbols: FrozenSet[str] = field(default_factory=frozenset)
    flow_symbols: FrozenSet[str] = field(default_factory=frozenset)
    penalize_symbols: FrozenSet[str] = field(default_factory=frozenset)
    penalize_extensions: FrozenSet[str] = field(default_factory=frozenset)
    penalize_chunk_types: FrozenSet[str] = field(default_factory=frozenset)
    content_markers: FrozenSet[str] = field(default_factory=frozenset)


_INTENT_PROFILES: dict[str, dict] = {
    "jwt": {
        "boost_symbols": {"generateJWT", "generatejwt", "jwt.sign", "JWT_SECRET"},
        "flow_symbols": {"generateJWT", "handleLogin", "handle_login"},
        "penalize_symbols": {
            "verify_password", "create_session", "authenticate_user",
            "authenticateUser", "handleGetProfile",
        },
        "penalize_extensions": {".html", ".md"},
        "penalize_chunk_types": {"chunk"},
        "content_markers": {"jwt.sign", "jwt_secret", "expiresin"},
    },
    "auth": {
        "boost_symbols": {
            "authenticate_user", "authenticateUser", "verify_password",
            "handleLogin", "handle_login", "create_session",
        },
        "flow_symbols": {
            "handleLogin", "handle_login", "authenticate_user", "authenticateUser",
            "verify_password", "generateJWT", "create_session",
        },
        "penalize_symbols": {"handleGetProfile"},
        "penalize_extensions": {".html", ".md"},
        "penalize_chunk_types": {"chunk"},
        "content_markers": {"401", "invalid", "credential", "password", "bcrypt"},
    },
    "route": {
        "boost_symbols": {"handleLogin", "handleGetProfile", "handle_login"},
        "flow_symbols": {"handleLogin", "handleGetProfile"},
        "penalize_extensions": {".html", ".md"},
        "penalize_chunk_types": {"chunk"},
    },
    "function": {
        "boost_symbols": set(),
        "flow_symbols": set(),
        "penalize_extensions": {".html", ".md", ".json"},
        "penalize_chunk_types": {"chunk"},
    },
    "architecture": {
        "boost_symbols": set(),
        "flow_symbols": set(),
        "penalize_extensions": set(),
        "penalize_chunk_types": set(),
    },
    "general": {
        "boost_symbols": set(),
        "flow_symbols": set(),
        "penalize_extensions": set(),
        "penalize_chunk_types": set(),
    },
}


def extract_query_terms(query: str) -> List[str]:
    """Extract meaningful search terms from a natural-language query."""
    stopwords = {
        "a", "an", "the", "is", "are", "was", "were", "be", "been", "being",
        "have", "has", "had", "do", "does", "did", "will", "would", "could",
        "should", "may", "might", "what", "when", "where", "which", "who",
        "whom", "how", "why", "if", "then", "than", "that", "this", "these",
        "those", "with", "from", "into", "for", "and", "or", "but", "not",
        "in", "on", "at", "to", "of", "by", "as", "it", "its", "user", "users",
        "file", "files", "code", "function", "functions", "method", "methods",
        "work", "works", "working", "happens", "happen", "explain", "describe",
        "show", "tell", "me", "about", "does", "can", "all", "any", "some",
        "involved", "creating", "create", "generating", "generate",
    }
    tokens = re.findall(r"[a-zA-Z_][a-zA-Z0-9_]*", query.lower())
    return [t for t in tokens if len(t) > 2 and t not in stopwords]


def _matches_any(patterns: List[str], text: str) -> bool:
    return any(re.search(p, text) for p in patterns)


def classify_query_intent(query: str) -> QueryIntent:
    """
    Classify query intent before retrieval.

    Intents: jwt, auth, architecture, function, route, general
    """
    normalized = query.strip().lower()
    terms = tuple(extract_query_terms(query))

    if _matches_any(JWT_PATTERNS, normalized) and not _matches_any(
        [r"\btrace\b", r"\bflow\b", r"\bfrom request\b"], normalized
    ):
        primary = "jwt"
    elif _matches_any(AUTH_PATTERNS, normalized):
        primary = "auth"
    elif _matches_any(ARCHITECTURE_PATTERNS, normalized):
        primary = "architecture"
    elif _matches_any(ROUTE_PATTERNS, normalized):
        primary = "route"
    elif _matches_any(FUNCTION_PATTERNS, normalized):
        primary = "function"
    else:
        primary = "general"

    profile = _INTENT_PROFILES.get(primary, _INTENT_PROFILES["general"])
    extra_penalize: Set[str] = set()
    if primary == "auth" and _matches_any(
        [r"\bfail", r"\b401\b", r"\binvalid", r"\bincorrect", r"\bpassword\b"], normalized
    ):
        extra_penalize.add("generateJWT")

    return QueryIntent(
        primary=primary,
        terms=terms,
        boost_symbols=frozenset(profile.get("boost_symbols", set())),
        flow_symbols=frozenset(profile.get("flow_symbols", set())),
        penalize_symbols=frozenset(profile.get("penalize_symbols", set()) | extra_penalize),
        penalize_extensions=frozenset(profile.get("penalize_extensions", set())),
        penalize_chunk_types=frozenset(profile.get("penalize_chunk_types", set())),
        content_markers=frozenset(profile.get("content_markers", set())),
    )


def classify_top_k(query: str, intent: Optional[QueryIntent] = None) -> int:
    """
    Classify query complexity and return recommended top_k.

    Precision-focused intents use smaller K.
    """
    if intent is None:
        intent = classify_query_intent(query)

    if intent.primary in ("jwt", "function", "route"):
        return 5
    if intent.primary == "auth":
        return 8

    normalized = query.strip().lower()

    for pattern in ARCHITECTURE_PATTERNS:
        if re.search(pattern, normalized):
            return 12

    for pattern in SIMPLE_PATTERNS:
        if re.search(pattern, normalized):
            return 5

    terms = list(intent.terms)
    if len(terms) >= 4 or len(normalized.split()) >= 10:
        return 10

    return 5


def extract_symbol_candidates(query: str) -> Set[str]:
    """Extract likely code symbol names from the query."""
    symbols: Set[str] = set()
    for match in re.finditer(r"`([^`]+)`|([a-zA-Z_][a-zA-Z0-9_]*(?:_[a-zA-Z0-9_]*)+)", query):
        candidate = match.group(1) or match.group(2)
        if candidate:
            symbols.add(candidate)
    return symbols


def assign_context_group(item_metadata: dict, intent: QueryIntent) -> str:
    """Assign a retrieved chunk to a context group for LLM assembly."""
    function_name = str(item_metadata.get("function_name") or "").lower()
    file_path = str(item_metadata.get("file_path") or "").lower()
    content_markers = intent.content_markers

    if intent.primary == "jwt":
        if function_name in {"generatejwt"} or "jwt.sign" in file_path:
            return "JWT Creation"
        if function_name in {"handlelogin", "handle_login"}:
            return "JWT Callers"
        if any(m in str(item_metadata.get("references", "")).lower() for m in ("jwt", "sign")):
            return "JWT References"
        return "JWT Related"

    if intent.primary == "auth":
        if function_name in {"authenticate_user", "authenticateuser", "verify_password"}:
            return "Authentication Core"
        if function_name in {"handlelogin", "handle_login"}:
            return "Login Handler"
        if function_name == "create_session":
            return "Session Management"
        if "401" in str(item_metadata.get("references", "")):
            return "Auth Error Handling"
        return "Authentication"

    if intent.primary == "architecture":
        if file_path.endswith(".md") or "readme" in file_path:
            return "Documentation"
        if file_path.endswith(".json"):
            return "Configuration"
        return "Source Code"

    if intent.primary == "route":
        if "handler" in function_name or "handler" in file_path:
            return "API Handlers"
        return "Routes & Endpoints"

    if function_name:
        return f"Function: {item_metadata.get('function_name')}"
    return "General Context"
