"""E2E trace of upload -> index -> query pipeline (session-scoped in-memory RAG)."""

import asyncio
import json
import sys
import time
import uuid

import requests

BASE = "http://localhost:8000"
SESSION_ID = str(uuid.uuid4())


async def session_stats(label: str) -> dict:
    """Fetch per-session stats from the API."""
    resp = requests.get(
        f"{BASE}/api/query/stats",
        params={"session_id": SESSION_ID},
        timeout=30,
    )
    data = resp.json()
    print(f"[{label}] session_stats: {json.dumps(data)}")
    return data


def main() -> int:
    print("=" * 60)
    print("PIPELINE TRACE — Session In-Memory RAG")
    print(f"Session: {SESSION_ID}")
    print("=" * 60)

    before = asyncio.run(session_stats("before"))

    with open("sample_project.zip", "rb") as f:
        upload = requests.post(
            f"{BASE}/api/upload/zip",
            files={"file": ("sample_project.zip", f, "application/zip")},
            params={"session_id": SESSION_ID},
            timeout=120,
        )
    upload.raise_for_status()
    up = upload.json()
    upload_id = up["upload_id"]
    print(f"Upload OK: {up.get('extracted_files_count')} files, upload_id={upload_id}")

    process = requests.post(
        f"{BASE}/api/upload/zip/process",
        params={"upload_id": upload_id, "session_id": SESSION_ID},
        timeout=120,
    )
    process.raise_for_status()
    print(f"Process queued: {process.json()}")

    baseline = before.get("collection_count", 0)
    for attempt in range(30):
        time.sleep(2)
        stats = asyncio.run(session_stats("polling"))
        count = stats.get("collection_count", 0)
        if count > baseline:
            time.sleep(2)
            stats2 = asyncio.run(session_stats("stable-check"))
            if stats2.get("collection_count") == count:
                break

    after = asyncio.run(session_stats("after"))
    print(f"\nChunks indexed: {after.get('collection_count', 0) - baseline}")

    search = requests.post(
        f"{BASE}/api/query/search",
        json={
            "query": "How does authentication work?",
            "top_k": 5,
            "session_id": SESSION_ID,
        },
        timeout=180,
    )
    search.raise_for_status()
    result = search.json()
    print(f"\nQuery result:")
    print(f"  snippets: {len(result.get('context', []))}")
    print(f"  model: {result.get('model')}")
    print(f"  answer: {(result.get('answer') or '')[:300]}")

    if after.get("storage") != "in-memory":
        print("FAIL: storage is not in-memory")
        return 1
    if len(result.get("context", [])) == 0:
        print("FAIL: no context retrieved")
        return 1

    print("\nSUCCESS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
