"""Diagnose retrieval pipeline stages for JWT query."""
import asyncio
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from create_sample_project import create_sample_zip
import zipfile
import io

from app.services.code_parser import CodeParser
from app.services.embedding_service import EmbeddingService
from app.services.retrieval_service import RetrievalService
from app.services.query_classifier import extract_query_terms, classify_top_k, classify_query_intent

QUERY = "Which functions are involved in creating a JWT token?"
SESSION = "diag-jwt"


async def main():
    rs = RetrievalService()
    emb = EmbeddingService()
    zip_data = create_sample_zip()
    with zipfile.ZipFile(io.BytesIO(zip_data)) as zf:
        for name in zf.namelist():
            if name.endswith("/"):
                continue
            content = zf.read(name).decode("utf-8", errors="ignore")
            fid = str(uuid.uuid4())
            lang = CodeParser.get_language(name)
            for chunk in CodeParser.parse_by_functions(content, lang, name):
                meta = CodeParser.build_chunk_metadata(chunk, fid, name, lang)
                et = CodeParser.build_embedding_text(chunk, name)
                vec = await emb.embed_text(et)
                await rs.store_embedding(SESSION, str(uuid.uuid4()), chunk.content, vec, meta)

    session = rs._session_store.get(SESSION)
    qe = await emb.embed_text(QUERY)
    terms = extract_query_terms(QUERY)
    intent = classify_query_intent(QUERY)
    print(f"Intent: {intent.primary}")
    k = classify_top_k(QUERY, intent)
    fetch_k = min(max(k * 3, k + 10), 60)
    raw = rs._retrieve_batch(qe, session, fetch_k, None)
    ranked = rs._enhanced_rerank(list(raw), QUERY, terms, intent, k)
    flow = rs._reconstruct_flow(session, intent, ranked, k)
    merged = rs._merge_unique(ranked, flow)
    expanded = await rs._expand_neighbors(merged, session, intent, k)
    hops = await rs._multi_hop_expand(expanded, session, QUERY, intent, k)
    final = rs._apply_diversity_filter(hops, QUERY, terms, intent, k)

    def show(label, items):
        print(f"\n=== {label} ===")
        for i, r in enumerate(items[:12], 1):
            m = r.get("metadata", {})
            sym = m.get("function_name") or m.get("chunk_type") or "?"
            print(
                f"  {i}. {m.get('file_path', '?')} :: {sym} "
                f"d={r.get('distance', 0):.3f} exp={r.get('expansion_type', '')}"
            )

    show("RAW VECTOR", raw)
    show("RERANKED", ranked)
    show("AFTER NEIGHBOR+MULTIHOP", hops)
    show("FINAL", final)


if __name__ == "__main__":
    asyncio.run(main())
