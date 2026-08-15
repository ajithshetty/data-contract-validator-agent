const BASE_URL = import.meta.env.VITE_API_URL || "http://localhost:8000/api";

async function request(path, options = {}) {
  const res = await fetch(`${BASE_URL}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || "Request failed");
  }
  return res.json();
}

export const api = {
  validate: (rawSchema, schemaType) =>
    request("/validate", {
      method: "POST",
      body: JSON.stringify({ raw_schema: rawSchema, schema_type: schemaType }),
    }),

  ingest: (contractsDir = null) =>
    request("/ingest", {
      method: "POST",
      body: JSON.stringify({ contracts_dir: contractsDir }),
    }),

  listContracts: () => request("/contracts"),
  collectionInfo: () => request("/collection"),
  getSettings: () => request("/settings"),
  health: () => request("/health"),
};
