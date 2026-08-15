"""
Loads and parses YAML data contracts from the contracts directory.
Each contract file defines expected schema, SLAs, ownership, and rules.
"""
import yaml
from pathlib import Path
from typing import List, Dict, Any
from backend.config import settings


def load_all_contracts(contracts_dir: str | None = None) -> List[Dict[str, Any]]:
    """Load all YAML contracts from the contracts directory."""
    path = Path(contracts_dir or settings.contracts_dir)
    contracts = []
    for file in sorted(path.rglob("*.yml")) + sorted(path.rglob("*.yaml")):
        try:
            with open(file) as f:
                data = yaml.safe_load(f)
                if data:
                    data["_source_file"] = file.name
                    contracts.append(data)
        except Exception as e:
            print(f"Warning: could not parse {file.name}: {e}")
    return contracts


def contract_to_text(contract: Dict[str, Any]) -> str:
    """Serialize a contract to a text block for embedding."""
    lines = []
    lines.append(f"CONTRACT: {contract.get('name', 'unknown')}")
    lines.append(f"TABLE: {contract.get('table', 'unknown')}")
    lines.append(f"OWNER: {contract.get('owner', 'unknown')}")
    lines.append(f"DESCRIPTION: {contract.get('description', '')}")

    if contract.get("sla"):
        sla = contract["sla"]
        lines.append(f"SLA_FRESHNESS: {sla.get('freshness_hours', 'N/A')}h")
        lines.append(f"SLA_AVAILABILITY: {sla.get('availability_pct', 'N/A')}%")

    if contract.get("schema"):
        lines.append("SCHEMA:")
        for col in contract["schema"]:
            nullable = "nullable" if col.get("nullable", True) else "not_null"
            pii = " PII" if col.get("pii") else ""
            lines.append(
                f"  - {col['name']}: {col['type']} ({nullable}){pii}"
                + (f" | {col.get('description', '')}" if col.get("description") else "")
            )

    if contract.get("rules"):
        lines.append("RULES:")
        for rule in contract["rules"]:
            lines.append(f"  - [{rule.get('severity','WARNING')}] {rule.get('description','')}")

    return "\n".join(lines)
