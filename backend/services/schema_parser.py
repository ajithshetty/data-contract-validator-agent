"""
Parses incoming schemas into a normalized format for validation.
Supports: Iceberg JSON schema, dbt schema.yml, raw SQL DDL.
"""
import re
import yaml
import json
from typing import List, Dict, Any


def normalize_schema(raw: str, schema_type: str) -> Dict[str, Any]:
    """
    Parse raw schema input into normalized column list.

    Returns:
        {
            "table": str,
            "columns": [{"name": str, "type": str, "nullable": bool}],
            "raw_type": str,
        }
    """
    schema_type = schema_type.lower().strip()

    if schema_type == "iceberg":
        return _parse_iceberg(raw)
    elif schema_type == "dbt":
        return _parse_dbt(raw)
    elif schema_type in ("sql", "ddl"):
        return _parse_ddl(raw)
    else:
        raise ValueError(f"Unknown schema_type: {schema_type}. Use iceberg | dbt | sql")


def _parse_iceberg(raw: str) -> Dict[str, Any]:
    """Parse Iceberg JSON schema (output of table.schema() or REST catalog)."""
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        # Try extracting JSON block if wrapped in text
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if match:
            data = json.loads(match.group())
        else:
            raise ValueError("Could not parse Iceberg schema as JSON")

    table = data.get("identifier", data.get("table", "unknown"))
    fields = data.get("fields", data.get("schema", {}).get("fields", []))

    columns = []
    for f in fields:
        col_type = f.get("type", "unknown")
        if isinstance(col_type, dict):
            col_type = col_type.get("type", str(col_type))
        columns.append({
            "name": f.get("name", f.get("id", "unknown")),
            "type": str(col_type).lower(),
            "nullable": f.get("optional", f.get("nullable", True)),
        })

    return {"table": table, "columns": columns, "raw_type": "iceberg"}


def _parse_dbt(raw: str) -> Dict[str, Any]:
    """Parse dbt schema.yml model definition."""
    try:
        data = yaml.safe_load(raw)
    except yaml.YAMLError as e:
        raise ValueError(f"Could not parse dbt YAML: {e}")

    # Handle both full schema.yml and single model block
    models = data.get("models", [data] if "name" in data else [])
    if not models:
        raise ValueError("No models found in dbt schema YAML")

    model = models[0]
    table = model.get("name", "unknown")
    columns = []
    for col in model.get("columns", []):
        dtype = col.get("data_type", col.get("type", "unknown"))
        not_null = any(
            t.get("name") == "not_null" if isinstance(t, dict) else t == "not_null"
            for t in col.get("tests", [])
        )
        columns.append({
            "name": col["name"],
            "type": str(dtype).lower() if dtype else "unknown",
            "nullable": not not_null,
        })

    return {"table": table, "columns": columns, "raw_type": "dbt"}


def _parse_ddl(raw: str) -> Dict[str, Any]:
    """Parse CREATE TABLE SQL DDL statement."""
    # Extract table name
    table_match = re.search(r"CREATE\s+(?:OR\s+REPLACE\s+)?TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?([^\s(]+)", raw, re.IGNORECASE)
    table = table_match.group(1).strip("`\"'") if table_match else "unknown"

    # Extract column block
    body_match = re.search(r"\((.+)\)", raw, re.DOTALL)
    if not body_match:
        raise ValueError("Could not find column definitions in DDL")

    body = body_match.group(1)
    columns = []

    for line in body.split("\n"):
        line = line.strip().rstrip(",")
        # Skip constraints
        if re.match(r"(PRIMARY|FOREIGN|UNIQUE|CHECK|CONSTRAINT|INDEX)", line, re.IGNORECASE):
            continue
        if not line:
            continue

        parts = line.split()
        if len(parts) < 2:
            continue

        col_name = parts[0].strip("`\"'")
        col_type = parts[1].lower()
        nullable = "NOT NULL" not in line.upper()

        columns.append({"name": col_name, "type": col_type, "nullable": nullable})

    return {"table": table, "columns": columns, "raw_type": "sql"}


def schema_to_text(parsed: Dict[str, Any]) -> str:
    """Serialize parsed schema to text for embedding/retrieval."""
    lines = [f"TABLE: {parsed['table']}", f"TYPE: {parsed['raw_type']}", "COLUMNS:"]
    for col in parsed["columns"]:
        null_str = "nullable" if col["nullable"] else "not_null"
        lines.append(f"  - {col['name']}: {col['type']} ({null_str})")
    return "\n".join(lines)
