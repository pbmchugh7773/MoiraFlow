import { motion } from "framer-motion";
import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { parse } from "yaml";
import { api, ApiError, type ValidationError, type Workflow } from "../api";
import { canWrite, useAuth } from "../auth";
import { DagView } from "../components";

const SAMPLE = `apiVersion: moiraflow/v1
kind: Workflow
metadata:
  name: daily_import
spec:
  trigger: { type: manual }
  jobs:
    - id: fetch
      type: command
      with: { command: "echo fetching" }
      outputs: { done: "yes" }
    - id: load
      type: command
      needs: [fetch]
      with: { command: "echo load {{ jobs.fetch.outputs.done }}" }
`;

export function Workflows() {
  const { user } = useAuth();
  const nav = useNavigate();
  const [items, setItems] = useState<Workflow[] | null>(null);
  const [creating, setCreating] = useState(false);

  const load = () => api.listWorkflows().then(setItems).catch(() => setItems([]));
  useEffect(() => { load(); }, []);

  return (
    <div>
      <div className="page-head">
        <div>
          <div className="eyebrow">The loom</div>
          <h1 className="page-title">Workflows</h1>
        </div>
        {canWrite(user?.role) && (
          <button className="btn btn-gold" onClick={() => setCreating((v) => !v)}>
            {creating ? "Close" : "New workflow"}
          </button>
        )}
      </div>

      {creating && <Composer onCreated={() => { setCreating(false); load(); }} />}

      <div className="panel" style={{ overflow: "hidden", marginTop: 20 }}>
        {items === null ? (
          <div className="empty">Loading…</div>
        ) : items.length === 0 ? (
          <div className="empty">No workflows yet. Weave your first thread.</div>
        ) : (
          <table className="table">
            <thead>
              <tr><th>Name</th><th>Trigger</th><th>Active version</th><th>Created</th></tr>
            </thead>
            <tbody>
              {items.map((w, i) => (
                <motion.tr key={w.id}
                  initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: i * 0.03 }}
                  onClick={() => nav(`/workflows/${w.id}`)}>
                  <td><span style={{ fontWeight: 500 }}>{w.name}</span></td>
                  <td><span className="pill">{w.trigger_type}</span></td>
                  <td className="dim">{w.active_version_id ? "set" : "—"}</td>
                  <td className="dim">{new Date(w.created_at).toLocaleString()}</td>
                </motion.tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}

function Composer({ onCreated }: { onCreated: () => void }) {
  const [content, setContent] = useState(SAMPLE);
  const [errors, setErrors] = useState<ValidationError[] | null>(null);
  const [ok, setOk] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);

  const validate = async () => {
    setMsg(null);
    const res = await api.validate(content, "yaml");
    setOk(res.valid);
    setErrors(res.valid ? [] : res.errors);
  };
  const create = async () => {
    setMsg(null);
    try {
      const wf = await api.createWorkflow(content, "yaml");
      onCreated();
      setMsg(`Created ${wf.name}`);
    } catch (e) {
      if (e instanceof ApiError) {
        setMsg(e.message);
        if (Array.isArray(e.details)) setErrors(e.details as ValidationError[]);
      }
    }
  };

  const jobs = useMemo(() => {
    try {
      const d = parse(content);
      const list = d?.spec?.jobs;
      return Array.isArray(list) ? list.map((j) => ({ id: j.id, needs: j.needs, type: j.type })) : [];
    } catch {
      return [];
    }
  }, [content]);

  return (
    <motion.div className="panel" style={{ padding: 22, marginTop: 4 }}
      initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: "auto" }}>
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 18 }}>
        <div>
          <label className="label" style={{ display: "block", marginBottom: 8 }}>Workflow as code (YAML)</label>
          <textarea className="textarea" rows={16} value={content} onChange={(e) => setContent(e.target.value)} />
        </div>
        <div>
          <label className="label" style={{ display: "block", marginBottom: 8 }}>DAG preview</label>
          {jobs.length > 0 ? <DagView jobs={jobs} /> : <div className="empty" style={{ height: 340, display: "grid", placeItems: "center" }}>The thread takes shape as you write.</div>}
        </div>
      </div>
      <div className="row between" style={{ marginTop: 14 }}>
        <div className="row" style={{ gap: 10 }}>
          <button className="btn" onClick={validate}>Validate</button>
          <button className="btn btn-gold" onClick={create}>Create</button>
        </div>
        {ok && (!errors || errors.length === 0) && <span className="status success"><span className="dot" style={{ background: "currentColor" }} />valid</span>}
        {msg && <span className="dim" style={{ fontSize: 13 }}>{msg}</span>}
      </div>
      {errors && errors.length > 0 && (
        <div className="stack" style={{ marginTop: 14, gap: 6 }}>
          {errors.map((e, i) => (
            <div key={i} className="err" style={{ fontSize: 12.5 }}>
              <span className="mono">{e.code}</span> <span className="faint">{e.loc}</span> — {e.message}
            </div>
          ))}
        </div>
      )}
    </motion.div>
  );
}
