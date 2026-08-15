from functools import lru_cache
from typing import List, Dict, Any

from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_core.documents import Document
from langchain_qdrant import QdrantVectorStore
from qdrant_client import QdrantClient

from backend.config import settings
from backend.services.contract_loader import load_all_contracts, contract_to_text


@lru_cache(maxsize=1)
def get_embeddings():
    return HuggingFaceEmbeddings(model_name=settings.embedding_model)


@lru_cache(maxsize=1)
def get_qdrant_client():
    return QdrantClient(host=settings.qdrant_host, port=settings.qdrant_port)


def get_vectorstore():
    return QdrantVectorStore(
        client=get_qdrant_client(),
        collection_name=settings.collection_name,
        embedding=get_embeddings(),
    )


def retrieve_contracts(query: str, top_k: int | None = None) -> List[Dict[str, Any]]:
    """Retrieve the most relevant contracts for a given schema/table query."""
    k = top_k or settings.retrieval_top_k
    vs = get_vectorstore()
    docs = vs.similarity_search(query, k=k)
    return [
        {
            "content": d.page_content,
            "source": d.metadata.get("source", "unknown"),
            "contract_name": d.metadata.get("contract_name", "unknown"),
            "table": d.metadata.get("table", "unknown"),
        }
        for d in docs
    ]


def ingest_contracts(contracts_dir: str | None = None) -> Dict[str, Any]:
    """Load all YAML contracts and upsert into Qdrant."""
    contracts = load_all_contracts(contracts_dir)
    if not contracts:
        return {"status": "error", "message": "No YAML contracts found", "contracts_loaded": 0}

    docs = []
    for contract in contracts:
        text = contract_to_text(contract)
        docs.append(Document(
            page_content=text,
            metadata={
                "source": contract.get("_source_file", "unknown"),
                "contract_name": contract.get("name", "unknown"),
                "table": contract.get("table", "unknown"),
                "owner": contract.get("owner", "unknown"),
            }
        ))

    QdrantVectorStore.from_documents(
        documents=docs,
        embedding=get_embeddings(),
        url=f"http://{settings.qdrant_host}:{settings.qdrant_port}",
        collection_name=settings.collection_name,
        force_recreate=True,
    )

    return {
        "status": "ok",
        "contracts_loaded": len(contracts),
        "documents_indexed": len(docs),
        "collection": settings.collection_name,
    }


def collection_info() -> Dict[str, Any]:
    client = get_qdrant_client()
    existing = [c.name for c in client.get_collections().collections]
    if settings.collection_name not in existing:
        return {"exists": False, "vectors_count": 0}
    info = client.get_collection(settings.collection_name)
    return {"exists": True, "vectors_count": info.points_count, "collection": settings.collection_name}
