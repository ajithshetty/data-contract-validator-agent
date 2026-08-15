import { useState, useEffect } from "react";
import { api } from "./api/client";

// ── Sample schemas ─────────────────────────────────────────────────────────────

const SAMPLES = {
  iceberg: {
    label: "fact_orders (Iceberg JSON)",
    type: "iceberg",
    schema: `{
  "identifier": "warehouse.fact_orders",
  "fields": [
    {"name": "order_id", "type": "bigint", "optional": false},
    {"name": "customer_id", "type": "bigint", "optional": true},
    {"name": "order_ts", "type": "string", "optional": false},
    {"name": "order_status", "type": "varchar", "optional": false},
    {"name": "total_amount", "type": "decimal(10,2)", "optional": true},
    {"name": "country_code", "type": "varchar", "optional": true},
    {"name": "created_at", "type": "timestamptz", "optional": false}
  ]
}`,
  },
  dbt: {
    label: "fact_user_events (dbt YAML)",
    type: "dbt",
    schema: `models:
  - name: fact_user_events
    columns:
      - name: event_id
        data_type: varchar
        tests: [unique, not_null]
      - name: user_id
        data_type: bigint
      - name: session_id
        data_type: varchar
        tests: [not_null]
      - name: event_type
        data_type: varchar
      - name: event_ts
        data_type: timestamptz
      - name: page_url
        data_type: varchar
      - name: ip_address
        data_type: varchar
      - name: properties
        data_type: varchar`,
  },
  sql: {
    label: "dim_customers (SQL DDL)",
    type: "sql",
    schema: `CREATE TABLE warehouse.dim_customers (
    customer_sk      BIGINT       NOT NULL,
    customer_id      BIGINT       NOT NULL,
    full_name        VARCHAR(255),
    email            VARCHAR(255),
    country_code     VARCHAR(2)   NOT NULL,
    customer_segment VARCHAR(50),
    is_active        BOOLEAN      NOT NULL,
    valid_from       TIMESTAMPTZ  NOT NULL,
    valid_to         TIMESTAMPTZ,
    is_current       BOOLEAN      NOT NULL
);`,
  },
};

const GRAPH_NODES = ["parse_schema", "retrieve_contracts", "match_contract", "validate_schema", "validate_rules", "generate_report"];

// ── Sub-components ─────────────────────────────────────────────────────────────

function StatusDot({ status }) {
  const colors = { ok: "#22c55e", error: "#ef4444", idle: "#374151" };
  return (
    <span style={{
      display: "inline-block", width: 7, height: 7, borderRadius: "50%",
      background: colors[status] || colors.idle,
      boxShadow: status === "ok" ? "0 0 6px #22c55e55" : "none",
    }} />
  );
}

function GraphTrace({ trace, running }) {
  const completed = trace.map(t => GRAPH_NODES.find(n => t.startsWith(n))).filter(Boolean);
  return (
    <div>
      <div style={{ display: "flex", alignItems: "center", flexWrap: "wrap", gap: 0, rowGap: 8, marginBottom: 10 }}>
        {GRAPH_NODES.map((node, i) => {
          const isDone = completed.includes(node);
          const isActive = running && i === completed.length;
          return (
            <div key={node} style={{ display: "flex", alignItems: "center" }}>
              <div style={{
                padding: "3px 10px", borderRadius: 4, fontSize: 10, fontFamily: "monospace",
                border: `1px solid ${isActive ? "#3b82f6" : isDone ? "#166534" : "#1f2937"}`,
                background: isActive ? "#0f2942" : isDone ? "#052e16" : "#0d1117",
                color: isActive ? "#60a5fa" : isDone ? "#4ade80" : "#374151",
                transition: "all 0.3s", whiteSpace: "nowrap",
              }}>
                {isDone && "✓ "}{node}
                {isActive && <span style={{ marginLeft: 4, animation: "pulse 1s infinite" }}>●</span>}
              </div>
              {i < GRAPH_NODES.length - 1 && <span style={{ color: "#1f2937", fontSize: 10, margin: "0 1px" }}>→</span>}
            </div>
          );
        })}
      </div>
      {trace.length > 0 && trace.map((t, i) => (
        <div key={i} style={{ fontFamily: "monospace", fontSize: 10, color: "#374151", marginBottom: 2, paddingLeft: 4 }}>
          {i + 1}. {t}
        </div>
      ))}
    </div>
  );
}

function StatusBadge({ status }) {
  const cfg = {
    PASS: { bg: "#052e16", border: "#166534", color: "#4ade80", label: "✓ PASS" },
    WARN: { bg: "#1c1a07", border: "#713f12", color: "#fbbf24", label: "⚠ WARN" },
    FAIL: { bg: "#1a0a0a", border: "#7f1d1d", color: "#f87171", label: "✕ FAIL" },
  }[status] || { bg: "#111827", border: "#1f2937", color: "#94a3b8", label: status };

  return (
    <span style={{
      background: cfg.bg, border: `1px solid ${cfg.border}`, borderRadius: 4,
      color: cfg.color, fontSize: 13, fontWeight: 700, padding: "4px 12px",
      fontFamily: "monospace", letterSpacing: 1,
    }}>{cfg.label}</span>
  );
}

function ViolationCard({ v }) {
  const isError = v.severity === "ERROR";
  return (
    <div style={{
      background: isError ? "#1a0a0a" : "#1c1a07",
      border: `1px solid ${isError ? "#7f1d1d" : "#713f12"}`,
      borderLeft: `3px solid ${isError ? "#ef4444" : "#f59e0b"}`,
      borderRadius: 5, padding: "10px 14px", marginBottom: 8,
    }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 6 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <span style={{
            fontSize: 10, fontWeight: 700, fontFamily: "monospace", letterSpacing: 0.5,
            color: isError ? "#f87171" : "#fbbf24",
            background: isError ? "#450a0a" : "#451a03",
            border: `1px solid ${isError ? "#7f1d1d" : "#92400e"}`,
            borderRadius: 3, padding: "1px 6px",
          }}>{v.severity}</span>
          <span style={{ fontFamily: "monospace", fontSize: 12, color: "#94a3b8" }}>{v.rule}</span>
        </div>
        {v.column && v.column !== "table-level" && (
          <span style={{
            fontFamily: "monospace", fontSize: 10, color: "#60a5fa",
            background: "#0f1e35", border: "1px solid #1e3a5f",
            borderRadius: 3, padding: "1px 6px",
          }}>col: {v.column}</span>
        )}
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "6px 12px", fontSize: 11, marginBottom: 6 }}>
        <div>
          <span style={{ color: "#374151", fontFamily: "monospace" }}>expected: </span>
          <span style={{ color: "#d1d5db" }}>{v.expected}</span>
        </div>
        <div>
          <span style={{ color: "#374151", fontFamily: "monospace" }}>found: </span>
          <span style={{ color: "#d1d5db" }}>{v.found}</span>
        </div>
      </div>
      <div style={{ fontSize: 11, color: "#6b7280" }}>
        <span style={{ color: "#374151", fontFamily: "monospace" }}>suggestion: </span>
        {v.suggestion}
      </div>
    </div>
  );
}

function ContractsList({ contracts }) {
  if (!contracts?.length) return <div style={{ color: "#374151", fontSize: 12 }}>No contracts loaded yet.</div>;
  return (
    <div>
      {contracts.map((c, i) => (
        <div key={i} style={{
          background: "#0a0e14", border: "1px solid #1f2937", borderRadius: 5,
          padding: "8px 12px", marginBottom: 6,
        }}>
          <div style={{ fontFamily: "monospace", fontSize: 12, color: "#94a3b8", marginBottom: 2 }}>{c.name}</div>
          <div style={{ fontSize: 10, color: "#374151" }}>
            table: <span style={{ color: "#60a5fa" }}>{c.table}</span>
            {" · "}{c.columns} columns
            {" · "}<span style={{ color: "#475569" }}>{c.source_file}</span>
          </div>
        </div>
      ))}
    </div>
  );
}

// ── Main App ───────────────────────────────────────────────────────────────────

export default function App() {
  const [schemaInput, setSchemaInput] = useState("");
  const [schemaType, setSchemaType] = useState("iceberg");
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);
  const [backendStatus, setBackendStatus] = useState("idle");
  const [settings, setSettings] = useState(null);
  const [collectionInfo, setCollectionInfo] = useState(null);
  const [contracts, setContracts] = useState([]);
  const [ingesting, setIngesting] = useState(false);
  const [ingestMsg, setIngestMsg] = useState(null);
  const [activeTab, setActiveTab] = useState("validate");
  const [filterSeverity, setFilterSeverity] = useState("ALL");

  useEffect(() => {
    api.health()
      .then(() => {
        setBackendStatus("ok");
        return Promise.all([api.getSettings(), api.collectionInfo(), api.listContracts()]);
      })
      .then(([s, c, cs]) => {
        setSettings(s);
        setCollectionInfo(c);
        setContracts(cs.contracts || []);
      })
      .catch(() => setBackendStatus("error"));
  }, []);

  async function handleValidate() {
    if (!schemaInput.trim()) return;
    setRunning(true);
    setResult(null);
    setError(null);
    try {
      const data = await api.validate(schemaInput, schemaType);
      setResult(data);
    } catch (e) {
      setError(e.message);
    } finally {
      setRunning(false);
    }
  }

  async function handleIngest() {
    setIngesting(true);
    setIngestMsg(null);
    try {
      const data = await api.ingest("./contracts/sample");
      setIngestMsg(`✅ ${data.contracts_loaded} contracts → ${data.documents_indexed} vectors`);
      const [c, cs] = await Promise.all([api.collectionInfo(), api.listContracts()]);
      setCollectionInfo(c);
      setContracts(cs.contracts || []);
    } catch (e) {
      setIngestMsg(`❌ ${e.message}`);
    } finally {
      setIngesting(false);
    }
  }

  function loadSample(key) {
    const s = SAMPLES[key];
    setSchemaInput(s.schema);
    setSchemaType(s.type);
    setResult(null);
    setError(null);
  }

  const canRun = !running && schemaInput.trim().length > 10 && backendStatus === "ok";
  const filteredViolations = result?.violations?.filter(
    v => filterSeverity === "ALL" || v.severity === filterSeverity
  ) || [];

  return (
    <div style={{ minHeight: "100vh", background: "#0d1117", color: "#e2e8f0", fontFamily: "'Inter', system-ui, sans-serif", display: "flex" }}>
      <style>{`
        @keyframes pulse { 0%,100%{opacity:1} 50%{opacity:0.3} }
        @keyframes fadeUp { from{opacity:0;transform:translateY(8px)} to{opacity:1;transform:translateY(0)} }
        * { box-sizing: border-box; }
        ::-webkit-scrollbar { width: 5px; }
        ::-webkit-scrollbar-thumb { background: #1f2937; border-radius: 3px; }
        textarea:focus, select:focus { outline: none !important; }
      `}</style>

      {/* Sidebar */}
      <div style={{
        width: 230, minWidth: 230, background: "#0a0e14", borderRight: "1px solid #1f2937",
        padding: "20px 14px", display: "flex", flexDirection: "column", gap: 16, overflowY: "auto",
      }}>
        <div>
          <div style={{ fontFamily: "monospace", fontWeight: 700, fontSize: 13, color: "#f1f5f9", marginBottom: 3 }}>
            📋 Contract Validator
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 5 }}>
            <StatusDot status={backendStatus} />
            <span style={{ fontSize: 10, color: "#475569", fontFamily: "monospace" }}>
              {backendStatus === "ok" ? "backend connected" : "backend unreachable"}
            </span>
          </div>
        </div>

        {/* Tabs */}
        <div style={{ display: "flex", gap: 4 }}>
          {["validate", "contracts"].map(tab => (
            <button key={tab} onClick={() => setActiveTab(tab)} style={{
              flex: 1, padding: "5px 0", fontSize: 11, fontFamily: "monospace",
              background: activeTab === tab ? "#111827" : "transparent",
              border: `1px solid ${activeTab === tab ? "#1f2937" : "transparent"}`,
              borderRadius: 4, color: activeTab === tab ? "#94a3b8" : "#374151", cursor: "pointer",
            }}>{tab}</button>
          ))}
        </div>

        {activeTab === "validate" ? (
          <>
            <div>
              <div style={{ fontSize: 10, color: "#374151", fontFamily: "monospace", marginBottom: 7 }}>SAMPLE SCHEMAS</div>
              {Object.entries(SAMPLES).map(([key, s]) => (
                <button key={key} onClick={() => loadSample(key)} style={{
                  display: "block", width: "100%", textAlign: "left", background: "transparent",
                  border: "1px solid transparent", borderRadius: 4, color: "#475569",
                  fontSize: 11, padding: "5px 7px", cursor: "pointer", marginBottom: 2,
                }}
                  onMouseEnter={e => { e.currentTarget.style.borderColor = "#1f2937"; e.currentTarget.style.color = "#94a3b8"; }}
                  onMouseLeave={e => { e.currentTarget.style.borderColor = "transparent"; e.currentTarget.style.color = "#475569"; }}
                >→ {s.label}</button>
              ))}
            </div>

            <div>
              <div style={{ fontSize: 10, color: "#374151", fontFamily: "monospace", marginBottom: 7 }}>GRAPH NODES</div>
              {GRAPH_NODES.map(n => (
                <div key={n} style={{ fontFamily: "monospace", fontSize: 10, color: "#374151", marginBottom: 3 }}>· {n}</div>
              ))}
            </div>

            {settings && (
              <div>
                <div style={{ fontSize: 10, color: "#374151", fontFamily: "monospace", marginBottom: 7 }}>CONFIG</div>
                {[
                  ["model", settings.llm_model?.split("-").slice(-2).join("-")],
                  ["top-k", settings.retrieval_top_k],
                  ["contracts", settings.contracts_dir],
                ].map(([k, v]) => (
                  <div key={k} style={{ display: "flex", justifyContent: "space-between", marginBottom: 4, fontSize: 11 }}>
                    <span style={{ color: "#374151" }}>{k}</span>
                    <span style={{ color: "#475569", fontFamily: "monospace" }}>{v}</span>
                  </div>
                ))}
              </div>
            )}
          </>
        ) : (
          <div>
            <div style={{ fontSize: 10, color: "#374151", fontFamily: "monospace", marginBottom: 8 }}>VECTOR STORE</div>
            <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 4, fontSize: 11 }}>
              <span style={{ color: "#374151" }}>status</span>
              <span style={{ display: "flex", alignItems: "center", gap: 4 }}>
                <StatusDot status={collectionInfo?.exists ? "ok" : "error"} />
                <span style={{ color: "#94a3b8", fontFamily: "monospace", fontSize: 10 }}>
                  {collectionInfo?.exists ? `${collectionInfo.vectors_count} vectors` : "not found"}
                </span>
              </span>
            </div>
            <button onClick={handleIngest} disabled={ingesting} style={{
              width: "100%", background: "#111827", border: "1px solid #1f2937",
              borderRadius: 4, color: ingesting ? "#374151" : "#94a3b8",
              fontSize: 11, padding: "6px 0", cursor: ingesting ? "not-allowed" : "pointer",
              fontFamily: "monospace", marginBottom: 8, marginTop: 4,
            }}>
              {ingesting ? "⏳ ingesting..." : "⚡ ingest contracts/sample"}
            </button>
            {ingestMsg && <div style={{ fontSize: 10, color: ingestMsg.startsWith("✅") ? "#4ade80" : "#f87171", fontFamily: "monospace", marginBottom: 10 }}>{ingestMsg}</div>}
            <div style={{ fontSize: 10, color: "#374151", fontFamily: "monospace", marginBottom: 8 }}>LOADED CONTRACTS</div>
            <ContractsList contracts={contracts} />
          </div>
        )}
      </div>

      {/* Main */}
      <div style={{ flex: 1, padding: "28px 32px", overflowY: "auto" }}>
        <div style={{ maxWidth: 820 }}>
          <div style={{ marginBottom: 20 }}>
            <h1 style={{ margin: 0, fontSize: 18, fontWeight: 600, color: "#f1f5f9" }}>Data Contract Validator</h1>
            <p style={{ margin: "4px 0 0", fontSize: 12.5, color: "#475569" }}>
              Paste an Iceberg schema, dbt model YAML, or SQL DDL — the agent matches it to your contracts and reports violations.
            </p>
          </div>

          {/* Schema type selector + textarea */}
          <div style={{ display: "flex", gap: 8, marginBottom: 8, alignItems: "center" }}>
            <div style={{ fontSize: 10, color: "#374151", fontFamily: "monospace" }}>SCHEMA TYPE</div>
            {["iceberg", "dbt", "sql"].map(t => (
              <button key={t} onClick={() => setSchemaType(t)} style={{
                padding: "4px 12px", borderRadius: 4, fontSize: 11, fontFamily: "monospace",
                background: schemaType === t ? "#0f2942" : "transparent",
                border: `1px solid ${schemaType === t ? "#3b82f6" : "#1f2937"}`,
                color: schemaType === t ? "#60a5fa" : "#475569", cursor: "pointer",
              }}>{t}</button>
            ))}
          </div>

          <textarea
            value={schemaInput}
            onChange={e => setSchemaInput(e.target.value)}
            rows={12}
            placeholder={schemaType === "iceberg" ? '{"identifier": "warehouse.fact_orders", "fields": [...]}' : schemaType === "dbt" ? "models:\n  - name: fact_orders\n    columns:\n      - name: order_id\n        data_type: bigint" : "CREATE TABLE warehouse.fact_orders (\n  order_id BIGINT NOT NULL,\n  ...\n);"}
            style={{
              width: "100%", background: "#0a0e14", border: "1px solid #1f2937",
              borderRadius: 6, padding: "12px 14px", color: "#e2e8f0",
              fontSize: 12, fontFamily: "monospace", lineHeight: 1.6, marginBottom: 10, resize: "vertical",
            }}
          />

          <div style={{ display: "flex", gap: 8, marginBottom: 24, alignItems: "center" }}>
            <button onClick={handleValidate} disabled={!canRun} style={{
              background: canRun ? "#2563eb" : "#1e293b",
              color: canRun ? "white" : "#374151",
              border: "none", borderRadius: 5, padding: "9px 22px",
              fontSize: 13, fontWeight: 500, cursor: canRun ? "pointer" : "not-allowed",
            }}>
              {running ? "⏳ Validating..." : "🔍 Validate"}
            </button>
            <button onClick={() => { setSchemaInput(""); setResult(null); setError(null); }} style={{
              background: "transparent", border: "1px solid #1f2937", borderRadius: 5,
              color: "#475569", fontSize: 13, padding: "9px 14px", cursor: "pointer",
            }}>Clear</button>
          </div>

          {/* Trace */}
          {(running || result) && (
            <div style={{ background: "#0a0e14", border: "1px solid #1f2937", borderRadius: 6, padding: "12px 14px", marginBottom: 18 }}>
              <div style={{ fontSize: 10, color: "#374151", fontFamily: "monospace", marginBottom: 8 }}>EXECUTION TRACE</div>
              <GraphTrace trace={result?.execution_trace || []} running={running} />
            </div>
          )}

          {error && (
            <div style={{ background: "#1a0a0a", border: "1px solid #7f1d1d", borderRadius: 6, padding: "12px 14px", color: "#fca5a5", fontSize: 12.5, fontFamily: "monospace", marginBottom: 18 }}>
              ⚠ {error}
            </div>
          )}

          {result && (
            <div style={{ animation: "fadeUp 0.4s ease" }}>
              {/* Status row */}
              <div style={{ display: "flex", alignItems: "center", gap: 14, marginBottom: 16, flexWrap: "wrap" }}>
                <StatusBadge status={result.status} />
                <div style={{ fontSize: 12, color: "#475569" }}>
                  <span style={{ color: "#60a5fa", fontFamily: "monospace" }}>{result.table}</span>
                  {result.matched_contract && (
                    <> · matched <span style={{ color: "#94a3b8", fontFamily: "monospace" }}>{result.matched_contract}</span></>
                  )}
                  {!result.matched_contract && <> · <span style={{ color: "#f87171" }}>no contract matched</span></>}
                </div>
              </div>

              {/* Summary cards */}
              <div style={{ display: "flex", gap: 8, marginBottom: 18, flexWrap: "wrap" }}>
                {[
                  { label: "Total violations", value: result.summary.total_violations, color: "#94a3b8" },
                  { label: "Errors", value: result.summary.errors, color: result.summary.errors > 0 ? "#f87171" : "#4ade80" },
                  { label: "Warnings", value: result.summary.warnings, color: result.summary.warnings > 0 ? "#fbbf24" : "#4ade80" },
                  { label: "Schema type", value: result.schema_type, color: "#60a5fa" },
                ].map(m => (
                  <div key={m.label} style={{ background: "#0a0e14", border: "1px solid #1f2937", borderRadius: 5, padding: "8px 14px" }}>
                    <div style={{ fontSize: 9, color: "#374151", fontFamily: "monospace", marginBottom: 2 }}>{m.label.toUpperCase()}</div>
                    <div style={{ fontSize: 14, fontWeight: 600, color: m.color, fontFamily: "monospace" }}>{m.value}</div>
                  </div>
                ))}
              </div>

              {/* Violations */}
              {result.violations?.length > 0 && (
                <div>
                  <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 12 }}>
                    <div style={{ fontSize: 10, color: "#374151", fontFamily: "monospace" }}>VIOLATIONS</div>
                    {["ALL", "ERROR", "WARNING"].map(f => (
                      <button key={f} onClick={() => setFilterSeverity(f)} style={{
                        padding: "2px 10px", borderRadius: 3, fontSize: 10, fontFamily: "monospace",
                        background: filterSeverity === f ? "#111827" : "transparent",
                        border: `1px solid ${filterSeverity === f ? "#1f2937" : "transparent"}`,
                        color: filterSeverity === f ? "#94a3b8" : "#374151", cursor: "pointer",
                      }}>{f}</button>
                    ))}
                  </div>
                  {filteredViolations.map((v, i) => <ViolationCard key={i} v={v} />)}
                </div>
              )}

              {result.violations?.length === 0 && (
                <div style={{ background: "#052e16", border: "1px solid #166534", borderRadius: 6, padding: "14px 18px", color: "#4ade80", fontSize: 13 }}>
                  ✓ Schema fully complies with contract <strong>{result.matched_contract}</strong>. No violations found.
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
