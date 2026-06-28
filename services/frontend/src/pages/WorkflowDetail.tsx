import { motion } from "framer-motion";
import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api, ApiError, token, type Execution, type JobDef, type Workflow, type WorkflowDefinition, type WorkflowVersion } from "../api";
import { canLaunch, canWrite, useAuth } from "../auth";
import { DagView, StatusBadge } from "../components";
import { WorkflowBuilder } from "./WorkflowBuilder";

export function WorkflowDetail() {
  const { id = "" } = useParams();
  const { user } = useAuth();
  const nav = useNavigate();
  const [wf, setWf] = useState<Workflow | null>(null);
  const [versions, setVersions] = useState<WorkflowVersion[]>([]);
  const [runs, setRuns] = useState<Execution[]>([]);
  const [jobs, setJobs] = useState<JobDef[]>([]);
  const [definition, setDefinition] = useState<WorkflowDefinition | null>(null);
  const [editing, setEditing] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const reload = () => {
    api.getWorkflow(id).then((w) => {
      setWf(w);
      api.listVersions(id).then((vs) => {
        setVersions(vs);
        const active = vs.find((v) => v.id === w.active_version_id) ?? vs[vs.length - 1];
        if (active) {
          api.getVersion(id, active.version).then((d) => {
            setJobs(d.definition.spec.jobs ?? []);
            setDefinition(d.definition);
          }).catch(() => {});
        }
      }).catch(() => {});
    }).catch(() => setErr("Workflow not found"));
    api.listExecutions(id).then(setRuns).catch(() => {});
  };
  useEffect(reload, [id]);

  const [launching, setLaunching] = useState(false);

  const doLaunch = async (inputContext: Record<string, unknown>) => {
    setErr(null);
    try {
      const ex = await api.launch(id, Object.keys(inputContext).length ? inputContext : undefined);
      nav(`/executions/${ex.id}`);
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : "Launch failed");
    }
  };

  const exportYaml = async () => {
    const res = await fetch(api.exportWorkflow(id), {
      headers: { Authorization: `Bearer ${token.get()}` },
    });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(new Blob([await res.text()], { type: "text/yaml" }));
    a.download = `${wf?.name ?? "workflow"}.yaml`;
    a.click();
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
        <div className="row" style={{ gap: 10 }}>
          {canWrite(user?.role) && definition && (
            <button className="btn" onClick={() => setEditing((v) => !v)}>{editing ? "Close editor" : "Edit"}</button>
          )}
          {canWrite(user?.role) && (
            <button className="btn" onClick={() =>
              (wf.is_enabled ? api.disableWorkflow(id) : api.enableWorkflow(id)).then(reload)}>
              {wf.is_enabled ? "Disable" : "Enable"}
            </button>
          )}
          <button className="btn" onClick={exportYaml}>Export</button>
          {canWrite(user?.role) && (
            <button className="btn" style={{ color: "var(--fail)" }} onClick={() => {
              if (confirm(`Delete workflow "${wf.name}"?`)) api.deleteWorkflow(id).then(() => nav("/workflows"));
            }}>Delete</button>
          )}
          {canLaunch(user?.role) && (
            <button className="btn btn-gold" onClick={() => setLaunching((v) => !v)} disabled={!wf.active_version_id}>
              {launching ? "Cancel" : "Launch"}
            </button>
          )}
        </div>
      </div>
      {err && <div className="err" style={{ marginBottom: 16 }}>{err}</div>}

      {editing && definition && (
        <div style={{ marginBottom: 24 }}>
          <WorkflowBuilder
            editWorkflow={{ id, definition }}
            onSaved={() => { setEditing(false); reload(); }}
          />
        </div>
      )}

      {launching && (
        <LaunchPanel
          declared={(definition?.spec.context as Record<string, unknown>) ?? {}}
          onRun={doLaunch}
          onCancel={() => setLaunching(false)}
        />
      )}

      <div className="row" style={{ gap: 10, marginBottom: 24 }}>
        <span className="pill">trigger: {wf.trigger_type}</span>
        <span className="pill">{wf.is_enabled ? "enabled" : "disabled"}</span>
        <span className="pill mono">{id.slice(0, 8)}</span>
      </div>

      {jobs.length > 0 && !editing && (
        <div style={{ marginBottom: 28 }}>
          <h3 className="display" style={{ fontSize: 18, marginBottom: 12 }}>Shape</h3>
          <DagView jobs={jobs} />
        </div>
      )}

      <Section title="Versions">
        <table className="table">
          <thead><tr><th>Version</th><th>Hash</th><th>Format</th><th>Created</th><th></th></tr></thead>
          <tbody>
            {versions.map((v) => (
              <tr key={v.id}>
                <td>v{v.version}{wf.active_version_id === v.id && <span className="pill" style={{ marginLeft: 8 }}>active</span>}</td>
                <td className="mono dim">{v.definition_hash.slice(0, 12)}</td>
                <td className="dim">{v.source_format}</td>
                <td className="dim">{new Date(v.created_at).toLocaleString()}</td>
                <td style={{ textAlign: "right" }}>
                  {wf.active_version_id !== v.id && canWrite(user?.role) && (
                    <button className="btn btn-ghost" style={{ padding: "4px 10px", fontSize: 12 }}
                      onClick={() => api.activate(id, v.version).then(reload)}>Activate</button>
                  )}
                </td>
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

/** Collect launch inputs. Pre-fills the workflow's declared `spec.context`
 *  defaults; each value is parsed as JSON when possible, else kept as a string. */
function LaunchPanel({ declared, onRun, onCancel }: {
  declared: Record<string, unknown>;
  onRun: (input: Record<string, unknown>) => void;
  onCancel: () => void;
}) {
  const initial = Object.entries(declared).map(([key, value]) => ({
    key,
    value: typeof value === "string" ? value : JSON.stringify(value),
  }));
  const [rows, setRows] = useState<{ key: string; value: string }[]>(
    initial.length ? initial : [{ key: "", value: "" }],
  );
  const set = (i: number, p: Partial<{ key: string; value: string }>) =>
    setRows((rs) => rs.map((r, k) => (k === i ? { ...r, ...p } : r)));

  const parse = (s: string): unknown => {
    try { return JSON.parse(s); } catch { return s; }
  };
  const run = () => {
    const input: Record<string, unknown> = {};
    for (const r of rows) if (r.key.trim()) input[r.key.trim()] = parse(r.value);
    onRun(input);
  };

  return (
    <motion.div className="panel" style={{ padding: 18, marginBottom: 24 }}
      initial={{ opacity: 0, y: -6 }} animate={{ opacity: 1, y: 0 }}>
      <div className="row between" style={{ marginBottom: 12 }}>
        <h3 className="display" style={{ fontSize: 17, margin: 0 }}>Launch with inputs</h3>
        <button className="btn btn-ghost" style={{ padding: "4px 10px", fontSize: 12 }}
          onClick={() => setRows((rs) => [...rs, { key: "", value: "" }])}>+ Add input</button>
      </div>
      <p className="faint" style={{ fontSize: 12, marginTop: 0, marginBottom: 12 }}>
        {Object.keys(declared).length
          ? "Declared context — override values for this run. Plain text or JSON (numbers, true/false, objects)."
          : "This workflow declares no inputs. Add ad-hoc context keys, or just run it."}
      </p>
      <div className="stack" style={{ gap: 8 }}>
        {rows.map((r, i) => (
          <div key={i} className="row" style={{ gap: 8 }}>
            <input className="input mono" style={{ maxWidth: 200 }} value={r.key} placeholder="key"
              onChange={(e) => set(i, { key: e.target.value })} />
            <input className="input mono grow" value={r.value} placeholder="value (text or JSON)"
              onChange={(e) => set(i, { value: e.target.value })} />
            <button className="btn btn-ghost" style={{ padding: "4px 8px", fontSize: 12, color: "var(--fail)" }}
              onClick={() => setRows((rs) => rs.filter((_, k) => k !== i))}>×</button>
          </div>
        ))}
      </div>
      <div className="row" style={{ gap: 10, marginTop: 16 }}>
        <button className="btn btn-gold" onClick={run}>Run</button>
        <button className="btn" onClick={onCancel}>Cancel</button>
      </div>
    </motion.div>
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
