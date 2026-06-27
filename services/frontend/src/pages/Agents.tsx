import { useEffect, useState } from "react";
import { api, ApiError, type Agent, type EnrollToken } from "../api";

const STATUS_COLOR: Record<string, string> = {
  pending_approval: "var(--run)",
  approved: "var(--gold)",
  online: "var(--ok)",
  offline: "var(--text-dim)",
  revoked: "var(--fail)",
};

function short(s: string | null, n = 12) {
  return s ? s.slice(0, n) + "…" : "—";
}

export function Agents() {
  const [agents, setAgents] = useState<Agent[] | null>(null);
  const [enrolled, setEnrolled] = useState<EnrollToken | null>(null);
  const [err, setErr] = useState<string | null>(null);

  const load = () => api.listAgents().then(setAgents).catch(() => setAgents([]));
  useEffect(() => { load(); }, []);

  const enroll = async () => {
    setErr(null);
    try {
      setEnrolled(await api.enrollAgent());
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : "failed");
    }
  };

  return (
    <div>
      <div className="page-head">
        <div><div className="eyebrow">Fleet</div><h1 className="page-title">Agents</h1></div>
        <button className="btn btn-gold" onClick={enroll}>Enroll agent</button>
      </div>
      <p className="dim" style={{ marginTop: -14, marginBottom: 20, fontSize: 13.5 }}>
        Remote workers run <span className="mono">run_on: agent</span> jobs on their own queue. An
        enrolled agent stays <b>pending</b> until you approve it; <b>revoke</b> blocks it from
        running anything — secrets are sealed to each agent's key, never shared.
      </p>

      {err && <div className="err" style={{ marginBottom: 16 }}>{err}</div>}

      {enrolled && (
        <div className="panel" style={{ padding: 18, marginBottom: 20, borderColor: "var(--gold)" }}>
          <div className="label">Single-use enrollment token (expires in {Math.round(enrolled.expires_in / 60)} min)</div>
          <code className="mono" style={{ display: "block", padding: "10px 12px", margin: "8px 0",
            background: "rgba(0,0,0,.3)", borderRadius: 8, wordBreak: "break-all", fontSize: 12.5 }}>
            {enrolled.enrollment_token}
          </code>
          <div className="row" style={{ gap: 10, alignItems: "center" }}>
            <button className="btn btn-ghost" style={{ fontSize: 12, padding: "5px 10px" }}
              onClick={() => navigator.clipboard?.writeText(enrolled.enrollment_token)}>Copy</button>
            <span className="dim" style={{ fontSize: 12.5 }}>
              Run the agent with this token (Temporal at <span className="mono">{enrolled.temporal_host}</span>).
            </span>
            <button className="btn btn-ghost" style={{ fontSize: 12, padding: "5px 10px", marginLeft: "auto" }}
              onClick={() => setEnrolled(null)}>Dismiss</button>
          </div>
        </div>
      )}

      <div className="panel" style={{ overflow: "hidden" }}>
        {agents === null ? <div className="empty">Loading…</div>
          : agents.length === 0 ? <div className="empty">No agents enrolled yet.</div> : (
            <table className="table">
              <thead><tr><th>Name</th><th>Status</th><th>Queue</th><th>Fingerprint</th><th>Last seen</th><th></th></tr></thead>
              <tbody>
                {agents.map((a) => (
                  <tr key={a.id}>
                    <td>{a.name}</td>
                    <td>
                      <span className="pill" style={{ color: STATUS_COLOR[a.status] ?? "var(--text-dim)" }}>
                        {a.status}
                      </span>
                    </td>
                    <td className="mono dim">{short(a.task_queue, 14)}</td>
                    <td className="mono dim">{short(a.fingerprint)}</td>
                    <td className="dim">{a.last_heartbeat_at ? new Date(a.last_heartbeat_at).toLocaleString() : "—"}</td>
                    <td style={{ textAlign: "right", whiteSpace: "nowrap" }}>
                      {a.status === "pending_approval" && (
                        <button className="btn btn-ghost" style={{ padding: "5px 10px", fontSize: 12, color: "var(--gold)" }}
                          onClick={() => api.approveAgent(a.id).then(load)}>Approve</button>
                      )}
                      {a.status !== "revoked" && (
                        <button className="btn btn-ghost" style={{ padding: "5px 10px", fontSize: 12, color: "var(--fail)", marginLeft: 6 }}
                          onClick={() => { if (confirm(`Revoke agent "${a.name}"?`)) api.revokeAgent(a.id).then(load); }}>Revoke</button>
                      )}
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
