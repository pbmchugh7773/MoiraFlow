import { motion } from "framer-motion";
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, type Workflow, type WorkflowDefinition } from "../api";
import { canWrite, useAuth } from "../auth";
import { TEMPLATES } from "../templates";
import { WorkflowBuilder } from "./WorkflowBuilder";

export function Workflows() {
  const { user } = useAuth();
  const nav = useNavigate();
  const [items, setItems] = useState<Workflow[] | null>(null);
  const [creating, setCreating] = useState(false);
  // undefined = template gallery; null = blank; a definition = seed from template
  const [picked, setPicked] = useState<WorkflowDefinition | null | undefined>(undefined);

  const load = () => api.listWorkflows().then(setItems).catch(() => setItems([]));
  useEffect(() => { load(); }, []);

  const startNew = () => { setCreating((v) => !v); setPicked(undefined); };
  const done = () => { setCreating(false); setPicked(undefined); load(); };

  return (
    <div>
      <div className="page-head">
        <div>
          <div className="eyebrow">The loom</div>
          <h1 className="page-title">Workflows</h1>
        </div>
        {canWrite(user?.role) && (
          <button className="btn btn-gold" onClick={startNew}>
            {creating ? "Close" : "New workflow"}
          </button>
        )}
      </div>

      {creating && picked === undefined && (
        <div className="panel" style={{ padding: 22, marginBottom: 4 }}>
          <h3 className="display" style={{ fontSize: 17, marginBottom: 4 }}>Start a new workflow</h3>
          <div className="faint" style={{ fontSize: 12.5, marginBottom: 16 }}>Pick a template to scaffold, or start from scratch.</div>
          <div className="tpl-grid">
            <button className="tpl-card tpl-blank" onClick={() => setPicked(null)}>
              <div className="tpl-title">＋ Blank workflow</div>
              <div className="tpl-desc">One command job on an empty canvas.</div>
            </button>
            {TEMPLATES.map((t) => (
              <button key={t.id} className="tpl-card" onClick={() => setPicked(t.definition)}>
                <div className="tpl-title">{t.title}</div>
                <div className="tpl-desc">{t.description}</div>
                <div className="tpl-meta">{t.definition.spec.jobs.length} jobs · {String((t.definition.spec.trigger as { type?: string })?.type ?? "manual")}</div>
              </button>
            ))}
          </div>
        </div>
      )}

      {creating && picked !== undefined && (
        <div className="stack" style={{ gap: 10 }}>
          <div>
            <button className="btn btn-ghost" style={{ padding: "5px 11px", fontSize: 12 }} onClick={() => setPicked(undefined)}>← Templates</button>
          </div>
          <WorkflowBuilder template={picked ?? undefined} onCreated={done} />
        </div>
      )}

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
