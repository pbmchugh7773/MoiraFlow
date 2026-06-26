import { useEffect, useState } from "react";
import { api, ApiError } from "../api";

export function Secrets() {
  const [keys, setKeys] = useState<string[] | null>(null);
  const [key, setKey] = useState("");
  const [value, setValue] = useState("");
  const [err, setErr] = useState<string | null>(null);

  const load = () => api.listSecretKeys().then((r) => setKeys(r.keys)).catch(() => setKeys([]));
  useEffect(() => { load(); }, []);

  const save = async () => {
    setErr(null);
    try {
      await api.putSecret(key, value);
      setKey(""); setValue(""); load();
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : "failed");
    }
  };

  return (
    <div>
      <div className="page-head">
        <div><div className="eyebrow">Governance</div><h1 className="page-title">Secrets</h1></div>
      </div>
      <p className="dim" style={{ marginTop: -14, marginBottom: 20, fontSize: 13.5 }}>
        Stored encrypted at rest. Values are write-only — only keys are ever shown. Reference them in
        jobs as <span className="mono">secret://&lt;key&gt;</span>.
      </p>

      <div className="panel" style={{ padding: 18, marginBottom: 20 }}>
        <div className="row" style={{ gap: 12, alignItems: "flex-end", flexWrap: "wrap" }}>
          <div><label className="label">Key</label>
            <input className="input mono" value={key} onChange={(e) => setKey(e.target.value)} placeholder="pg_main" /></div>
          <div className="grow"><label className="label">Value</label>
            <input className="input mono" type="password" value={value} onChange={(e) => setValue(e.target.value)} placeholder="dsn / token / password" /></div>
          <button className="btn btn-gold" onClick={save} disabled={!key || !value}>Save secret</button>
        </div>
        {err && <div className="err" style={{ marginTop: 10 }}>{err}</div>}
      </div>

      <div className="panel" style={{ overflow: "hidden" }}>
        {keys === null ? <div className="empty">Loading…</div>
          : keys.length === 0 ? <div className="empty">No secrets defined.</div> : (
            <table className="table">
              <thead><tr><th>Key</th><th></th></tr></thead>
              <tbody>
                {keys.map((k) => (
                  <tr key={k}>
                    <td className="mono">{k}</td>
                    <td style={{ textAlign: "right" }}>
                      <button className="btn btn-ghost" style={{ padding: "5px 10px", fontSize: 12, color: "var(--fail)" }}
                        onClick={() => api.deleteSecret(k).then(load)}>Delete</button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
      </div>
    </div>
  );
}
