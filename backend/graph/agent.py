"""
LangGraph validation agent.

Flow:
  parse_schema
      ↓
  retrieve_contracts          ← semantic search in Qdrant
      ↓
  match_contract              ← find the best-fit contract for the table
      ↓
  validate_schema             ← column-level structural checks (types, nullability, missing cols)
      ↓
  validate_rules              ← semantic rule checks via LLM
      ↓
  generate_report             ← final structured violation report
"""
import json
from typing import TypedDict, List, Dict, Any, Optional
from langgraph.graph import StateGraph, END

from backend.config import settings
from backend.services import llm as llm_service
from backend.services import vectorstore as vs_service
from backend.services.schema_parser import normalize_schema, schema_to_text


# ── State ──────────────────────────────────────────────────────────────────────

class ValidationState(TypedDict):
    # Inputs
    raw_schema: str
    schema_type: str          # iceberg | dbt | sql

    # Parsed
    parsed_schema: Dict[str, Any]
    schema_text: str

    # Retrieved
    retrieved_contracts: List[Dict[str, Any]]
    matched_contract: Optional[Dict[str, Any]]

    # Violations
    schema_violations: List[Dict[str, Any]]    # structural (type/null mismatches, missing cols)
    rule_violations: List[Dict[str, Any]]      # semantic (LLM-assessed rule breaches)

    # Output
    report: Dict[str, Any]
    execution_trace: List[str]


# ── Helpers ────────────────────────────────────────────────────────────────────

def _violation(severity: str, column: str, rule: str, expected: str, found: str, suggestion: str) -> Dict:
    return {
        "severity": severity,
        "column": column,
        "rule": rule,
        "expected": expected,
        "found": found,
        "suggestion": suggestion,
    }


def _trace(state: ValidationState, msg: str) -> List[str]:
    t = state.get("execution_trace", [])
    t.append(msg)
    return t


# ── Node 1: Parse Schema ───────────────────────────────────────────────────────

def node_parse_schema(state: ValidationState) -> ValidationState:
    try:
        parsed = normalize_schema(state["raw_schema"], state["schema_type"])
        text = schema_to_text(parsed)
        trace = _trace(state, f"parse_schema → table='{parsed['table']}', columns={len(parsed['columns'])}, type={state['schema_type']}")
        return {**state, "parsed_schema": parsed, "schema_text": text, "execution_trace": trace}
    except Exception as e:
        trace = _trace(state, f"parse_schema → ERROR: {e}")
        return {
            **state,
            "parsed_schema": {"table": "unknown", "columns": [], "raw_type": state["schema_type"]},
            "schema_text": "",
            "execution_trace": trace,
            "report": {"error": str(e)},
        }


# ── Node 2: Retrieve Contracts ─────────────────────────────────────────────────

def node_retrieve_contracts(state: ValidationState) -> ValidationState:
    query = f"{state['parsed_schema'].get('table', '')} {state['schema_text']}"
    contracts = vs_service.retrieve_contracts(query, top_k=settings.retrieval_top_k)
    trace = _trace(state, f"retrieve_contracts → found {len(contracts)} candidates: {[c['contract_name'] for c in contracts]}")
    return {**state, "retrieved_contracts": contracts, "execution_trace": trace}


# ── Node 3: Match Contract ─────────────────────────────────────────────────────

def node_match_contract(state: ValidationState) -> ValidationState:
    if not state["retrieved_contracts"]:
        trace = _trace(state, "match_contract → no contracts found in vector store")
        return {**state, "matched_contract": None, "execution_trace": trace}

    table_name = state["parsed_schema"].get("table", "")
    candidates = "\n\n".join([
        f"[{i+1}] {c['contract_name']} (table: {c['table']})\n{c['content']}"
        for i, c in enumerate(state["retrieved_contracts"])
    ])

    prompt = f"""You are a data contract matching agent.

Incoming schema table: "{table_name}"

Candidate contracts:
{candidates}

Which contract number best matches this table? Consider table name similarity and column overlap.
If none match, respond with 0.

Respond ONLY with a JSON object:
{{"match": <0-{len(state['retrieved_contracts'])}>, "reason": "<brief reason>"}}"""

    response = llm_service.invoke(prompt)
    try:
        clean = response.strip().replace("```json", "").replace("```", "").strip()
        result = json.loads(clean)
        idx = int(result.get("match", 0)) - 1
        reason = result.get("reason", "")
        matched = state["retrieved_contracts"][idx] if 0 <= idx < len(state["retrieved_contracts"]) else None
    except Exception:
        matched = state["retrieved_contracts"][0] if state["retrieved_contracts"] else None
        reason = "fallback to top result"

    trace = _trace(state, f"match_contract → matched='{matched['contract_name'] if matched else 'none'}' ({reason})")
    return {**state, "matched_contract": matched, "execution_trace": trace}


# ── Node 4: Validate Schema (structural) ──────────────────────────────────────

def node_validate_schema(state: ValidationState) -> ValidationState:
    contract = state.get("matched_contract")
    if not contract:
        trace = _trace(state, "validate_schema → skipped, no matched contract")
        return {**state, "schema_violations": [], "execution_trace": trace}

    prompt = f"""You are a strict data contract validator. Compare the incoming schema against the contract.

INCOMING SCHEMA:
{state['schema_text']}

CONTRACT:
{contract['content']}

Check for ALL of the following and report every violation:
1. Missing columns (in contract but not in schema) → ERROR
2. Extra columns not in contract → WARNING
3. Type mismatches (e.g. contract says bigint, schema has string) → ERROR
4. Nullability violations (contract says not_null but schema allows nulls) → ERROR
5. PII columns without proper type or naming conventions → WARNING

Respond ONLY with a JSON array of violations. Each violation:
{{"severity": "ERROR"|"WARNING", "column": "<name>", "rule": "<rule name>", "expected": "<what contract says>", "found": "<what schema has>", "suggestion": "<fix>"}}

If no violations, return [].
Do not include markdown, only the JSON array."""

    response = llm_service.invoke(prompt, system_prompt="You are a precise data contract validator. Always respond with valid JSON only.")
    try:
        clean = response.strip().replace("```json", "").replace("```", "").strip()
        violations = json.loads(clean)
        if not isinstance(violations, list):
            violations = []
    except Exception:
        violations = []

    errors = sum(1 for v in violations if v.get("severity") == "ERROR")
    warnings = sum(1 for v in violations if v.get("severity") == "WARNING")
    trace = _trace(state, f"validate_schema → {errors} errors, {warnings} warnings (structural)")
    return {**state, "schema_violations": violations, "execution_trace": trace}


# ── Node 5: Validate Rules (semantic) ─────────────────────────────────────────

def node_validate_rules(state: ValidationState) -> ValidationState:
    contract = state.get("matched_contract")
    if not contract:
        trace = _trace(state, "validate_rules → skipped, no matched contract")
        return {**state, "rule_violations": [], "execution_trace": trace}

    prompt = f"""You are evaluating whether a schema satisfies the semantic rules defined in a data contract.

INCOMING SCHEMA:
{state['schema_text']}

CONTRACT (including rules section):
{contract['content']}

Evaluate each rule listed under RULES in the contract. For each rule that appears violated or at risk:

Respond ONLY with a JSON array:
{{"severity": "ERROR"|"WARNING", "column": "<column or 'table-level'>", "rule": "<rule name>", "expected": "<rule requirement>", "found": "<what schema shows>", "suggestion": "<how to fix>"}}

If no rule violations, return [].
Only output valid JSON array, no markdown."""

    response = llm_service.invoke(prompt, system_prompt="You are a precise data contract validator. Always respond with valid JSON only.")
    try:
        clean = response.strip().replace("```json", "").replace("```", "").strip()
        violations = json.loads(clean)
        if not isinstance(violations, list):
            violations = []
    except Exception:
        violations = []

    errors = sum(1 for v in violations if v.get("severity") == "ERROR")
    warnings = sum(1 for v in violations if v.get("severity") == "WARNING")
    trace = _trace(state, f"validate_rules → {errors} errors, {warnings} warnings (semantic rules)")
    return {**state, "rule_violations": violations, "execution_trace": trace}


# ── Node 6: Generate Report ────────────────────────────────────────────────────

def node_generate_report(state: ValidationState) -> ValidationState:
    all_violations = state.get("schema_violations", []) + state.get("rule_violations", [])
    errors = [v for v in all_violations if v.get("severity") == "ERROR"]
    warnings = [v for v in all_violations if v.get("severity") == "WARNING"]

    contract = state.get("matched_contract")
    status = "PASS" if not errors else "FAIL"
    if status == "PASS" and warnings:
        status = "WARN"

    report = {
        "status": status,
        "table": state["parsed_schema"].get("table", "unknown"),
        "schema_type": state["schema_type"],
        "matched_contract": contract["contract_name"] if contract else None,
        "contract_source": contract["source"] if contract else None,
        "summary": {
            "total_violations": len(all_violations),
            "errors": len(errors),
            "warnings": len(warnings),
        },
        "violations": all_violations,
        "execution_trace": state.get("execution_trace", []),
    }

    trace = _trace(state, f"generate_report → status={status}, total={len(all_violations)} violations")
    report["execution_trace"] = trace

    return {**state, "report": report, "execution_trace": trace}


# ── Build Graph ────────────────────────────────────────────────────────────────

def build_graph():
    g = StateGraph(ValidationState)

    g.add_node("parse_schema", node_parse_schema)
    g.add_node("retrieve_contracts", node_retrieve_contracts)
    g.add_node("match_contract", node_match_contract)
    g.add_node("validate_schema", node_validate_schema)
    g.add_node("validate_rules", node_validate_rules)
    g.add_node("generate_report", node_generate_report)

    g.set_entry_point("parse_schema")
    g.add_edge("parse_schema", "retrieve_contracts")
    g.add_edge("retrieve_contracts", "match_contract")
    g.add_edge("match_contract", "validate_schema")
    g.add_edge("validate_schema", "validate_rules")
    g.add_edge("validate_rules", "generate_report")
    g.add_edge("generate_report", END)

    return g.compile()


agent_graph = build_graph()
