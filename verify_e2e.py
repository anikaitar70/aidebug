"""End-to-end verification: upload -> index -> search (session-scoped in-memory RAG)."""
import json
import sys
import time
import uuid

import requests

BASE = "http://localhost:8000"
SESSION_ID = str(uuid.uuid4())
QUERIES = [
    "How does authentication work?",
    "What happens when authentication fails?",
    "Which functions generate JWTs?",
    "Trace authentication flow.",
]


def main() -> int:
    print("=" * 60)
    print("E2E VERIFICATION — Session In-Memory RAG")
    print("=" * 60)
    print(f"Session ID: {SESSION_ID}")

    health = requests.get(f"{BASE}/health", timeout=30)
    print(f"Health: {health.status_code} {health.json()}")

    stats_before = requests.get(
        f"{BASE}/api/query/stats",
        params={"session_id": SESSION_ID},
        timeout=30,
    ).json()
    baseline = stats_before.get("collection_count", 0)
    print(f"Session chunk count (before): {baseline}")
    print(f"Storage: {stats_before.get('storage', 'unknown')}")

    with open("sample_project.zip", "rb") as f:
        upload = requests.post(
            f"{BASE}/api/upload/zip",
            files={"file": ("sample_project.zip", f, "application/zip")},
            params={"session_id": SESSION_ID},
            timeout=120,
        )
    upload.raise_for_status()
    up = upload.json()
    print(f"\n[UPLOAD]")
    print(f"  Files extracted: {up.get('extracted_files_count')}")
    print(f"  upload_id: {up.get('upload_id')}")
    print(f"  session_id: {up.get('session_id')}")

    process = requests.post(
        f"{BASE}/api/upload/zip/process",
        params={"upload_id": up["upload_id"], "session_id": SESSION_ID},
        timeout=120,
    )
    process.raise_for_status()
    proc = process.json()
    files_queued = proc.get("files_queued", 0)
    print(f"\n[PROCESS]")
    print(f"  Files queued: {files_queued}")

    final_count = baseline
    for i in range(60):
        time.sleep(2)
        stats = requests.get(
            f"{BASE}/api/query/stats",
            params={"session_id": SESSION_ID},
            timeout=30,
        ).json()
        count = stats.get("collection_count", 0)
        if count > baseline:
            time.sleep(2)
            count2 = requests.get(
                f"{BASE}/api/query/stats",
                params={"session_id": SESSION_ID},
                timeout=30,
            ).json().get("collection_count", 0)
            if count2 == count:
                final_count = count
                break
            final_count = count2
        if i == 59:
            final_count = count

    chunks_stored = final_count - baseline
    print(f"\n[INDEX]")
    print(f"  Session chunk count (after): {final_count}")
    print(f"  Chunks stored (delta): {chunks_stored}")

    failures = []
    if chunks_stored <= 0:
        failures.append("no chunks indexed")

    for qi, query in enumerate(QUERIES, 1):
        print(f"\n[SEARCH {qi}] Query: {query}")
        search = requests.post(
            f"{BASE}/api/query/search",
            json={"query": query, "top_k": 5, "session_id": SESSION_ID},
            timeout=180,
        )
        search.raise_for_status()
        result = search.json()

        print(f"  Retrieved snippets: {len(result.get('context', []))}")
        print(f"  Model used: {result.get('model')}")
        print(f"  Tokens used: {result.get('tokens_used')}")
        print(f"  Answer preview: {(result.get('answer') or '')[:200]}")

        answer = result.get("answer") or ""
        if "404" in answer or "LLM generation failed" in answer:
            failures.append(f"query {qi}: LLM error in answer")
        if len(result.get("context", [])) == 0:
            failures.append(f"query {qi}: no retrieved snippets")
        if not answer.strip():
            failures.append(f"query {qi}: empty answer")

    # Session isolation check
    other_session = str(uuid.uuid4())
    isolated_stats = requests.get(
        f"{BASE}/api/query/stats",
        params={"session_id": other_session},
        timeout=30,
    ).json()
    if isolated_stats.get("collection_count", 0) != 0:
        failures.append("session isolation failed: other session has chunks")

    print("\n" + "=" * 60)
    if failures:
        print("FAILED:", ", ".join(failures))
        return 1
    print("SUCCESS: Upload -> Index -> Retrieve -> Generate pipeline verified")
    print("No ChromaDB dependency — session-scoped in-memory storage only")
    return 0


if __name__ == "__main__":
    sys.exit(main())
