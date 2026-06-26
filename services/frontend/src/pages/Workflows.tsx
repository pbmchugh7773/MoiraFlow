import { motion } from "framer-motion";
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, type Workflow } from "../api";
import { canWrite, useAuth } from "../auth";
import { WorkflowBuilder } from "./WorkflowBuilder";

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

      {creating && <WorkflowBuilder onCreated={() => { setCreating(false); load(); }} />}

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
