from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional

from backend.graph.agent import agent_graph
from backend.services import vectorstore as vs_service
from backend.services.contract_loader import load_all_contracts
from backend.config import settings

router = APIRouter()


# ── Models ─────────────────────────────────────────────────────────────────────

class ValidateRequest(BaseModel):
    raw_schema: str = Field(..., description="Raw schema: Iceberg JSON, dbt YAML, or SQL DDL")
    schema_type: str = Field(..., description="iceberg | dbt | sql")


class ViolationModel(BaseModel):
    severity: str
    column: str
    rule: str
    expected: str
    found: str
    suggestion: str


class SummaryModel(BaseModel):
    total_violations: int
    errors: int
    warnings: int


class ValidateResponse(BaseModel):
    status: str
    table: str
    schema_type: str
    matched_contract: Optional[str]
    contract_source: Optional[str]
    summary: SummaryModel
    violations: List[Dict[str, Any]]
    execution_trace: List[str]


class IngestRequest(BaseModel):
    contracts_dir: Optional[str] = None


class IngestResponse(BaseModel):
    status: str
    contracts_loaded: int = 0
    documents_indexed: int = 0
    collection: str = ""
    message: str = ""


class CollectionInfoResponse(BaseModel):
    exists: bool
    vectors_count: int
    collection: str = ""


class SettingsResponse(BaseModel):
    llm_model: str
    embedding_model: str
    collection_name: str
    retrieval_top_k: int
    chunk_size: int
    chunk_overlap: int
    qdrant_host: str
    qdrant_port: int
    contracts_dir: str


# ── Routes ─────────────────────────────────────────────────────────────────────

@router.post("/validate", response_model=ValidateResponse)
async def validate(req: ValidateRequest):
    """Run the LangGraph validation agent on a schema."""
    try:
        initial_state = {
            "raw_schema": req.raw_schema,
            "schema_type": req.schema_type,
            "parsed_schema": {},
            "schema_text": "",
            "retrieved_contracts": [],
            "matched_contract": None,
            "schema_violations": [],
            "rule_violations": [],
            "report": {},
            "execution_trace": [],
        }
        result = agent_graph.invoke(initial_state)
        report = result["report"]

        if "error" in report:
            raise HTTPException(status_code=422, detail=report["error"])

        return ValidateResponse(
            status=report["status"],
            table=report["table"],
            schema_type=report["schema_type"],
            matched_contract=report.get("matched_contract"),
            contract_source=report.get("contract_source"),
            summary=SummaryModel(**report["summary"]),
            violations=report["violations"],
            execution_trace=report["execution_trace"],
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/ingest", response_model=IngestResponse)
async def ingest(req: IngestRequest = IngestRequest()):
    """Ingest YAML contracts from a directory into Qdrant."""
    result = vs_service.ingest_contracts(req.contracts_dir)
    return IngestResponse(**result)


@router.get("/contracts")
async def list_contracts():
    """List all available contracts from the contracts directory."""
    contracts = load_all_contracts()
    return {
        "contracts": [
            {
                "name": c.get("name"),
                "table": c.get("table"),
                "owner": c.get("owner"),
                "source_file": c.get("_source_file"),
                "columns": len(c.get("schema", [])),
            }
            for c in contracts
        ]
    }


@router.get("/collection", response_model=CollectionInfoResponse)
async def collection_info():
    info = vs_service.collection_info()
    return CollectionInfoResponse(**info)


@router.get("/settings", response_model=SettingsResponse)
async def get_settings():
    return SettingsResponse(
        llm_model=settings.llm_model,
        embedding_model=settings.embedding_model,
        collection_name=settings.collection_name,
        retrieval_top_k=settings.retrieval_top_k,
        chunk_size=settings.chunk_size,
        chunk_overlap=settings.chunk_overlap,
        qdrant_host=settings.qdrant_host,
        qdrant_port=settings.qdrant_port,
        contracts_dir=settings.contracts_dir,
    )


@router.get("/health")
async def health():
    return {"status": "ok"}
