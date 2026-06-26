import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api, ApiError, type Execution, type Workflow, type WorkflowVersion } from "../api";
import { canLaunch, useAuth } from "../auth";
import { StatusBadge } from "../components";

export function WorkflowDetail() {
  const { id = "" } = useParams();
  const { user } = useAuth();
  const nav = useNavigate();
  const [wf, setWf] = useState<Workflow | null>(null);
  const [versions, setVersions] = useState<WorkflowVersion[]>([]);
  const [runs, setRuns] = useState<Execution[]>([]);
  const [err, setErr] = useState<string | null>(null);

  const reload = () => {
    api.getWorkflow(id).then(setWf).catch(() => setErr("Workflow not found"));
    api.listVersions(id).then(setVersions).catch(() => {});
    api.listExecutions(id).then(setRuns).catch(() => {});
  };
  useEffect(reload, [id]);

  const launch = async () => {
    setErr(null);
    try {
      const ex = await api.launch(id);
      nav(`/executions/${ex.id}`);
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : "Launch failed");
    }
  };

  if (err && !wf) return <div className="empty">{err}</div>;
  if (!wf) return <div className="empty">Loading…</div>;

  return (
    <div>
      <div className="page-head">
        <div>
          <div className="eyebrow">Workflow</div>
          <h1 className="page-title">{wf.name}</h1>
          {wf.description && <p className="dim" style={{ marginTop: 6 }}>{wf.description}</p>}
        </div>
        {canLaunch(user?.role) && (
          <button className="btn btn-gold" onClick={launch} disabled={!wf.active_version_id}>Launch</button>
        )}
      </div>
      {err && <div className="err" style={{ marginBottom: 16 }}>{err}</div>}

      <div className="row" style={{ gap: 10, marginBottom: 24 }}>
        <span className="pill">trigger: {wf.trigger_type}</span>
        <span className="pill">{wf.is_enabled ? "enabled" : "disabled"}</span>
        <span className="pill mono">{id.slice(0, 8)}</span>
      </div>

      <Section title="Versions">
        <table className="table">
          <thead><tr><th>Version</th><th>Hash</th><th>Format</th><th>Created</th></tr></thead>
          <tbody>
            {versions.map((v) => (
              <tr key={v.id}>
                <td>v{v.version}{wf.active_version_id === v.id && <span className="pill" style={{ marginLeft: 8 }}>active</span>}</td>
                <td className="mono dim">{v.definition_hash.slice(0, 12)}</td>
                <td className="dim">{v.source_format}</td>
                <td className="dim">{new Date(v.created_at).toLocaleString()}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Section>

      <Section title="Recent executions">
        {runs.length === 0 ? <div className="empty">No runs yet.</div> : (
          <table className="table">
            <thead><tr><th>Status</th><th>Run</th><th>Started</th></tr></thead>
            <tbody>
              {runs.map((r) => (
                <tr key={r.id} onClick={() => nav(`/executions/${r.id}`)}>
                  <td><StatusBadge status={r.status} /></td>
                  <td className="mono dim">{r.id.slice(0, 8)}</td>
                  <td className="dim">{new Date(r.created_at).toLocaleString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Section>

      <Link to="/workflows" className="dim" style={{ fontSize: 13 }}>← All workflows</Link>
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div style={{ marginBottom: 28 }}>
      <h3 className="display" style={{ fontSize: 18, marginBottom: 12 }}>{title}</h3>
      <div className="panel" style={{ overflow: "hidden" }}>{children}</div>
    </div>
  );
}
