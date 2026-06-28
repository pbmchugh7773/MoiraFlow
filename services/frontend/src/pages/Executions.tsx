import { motion } from "framer-motion";
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, type Execution } from "../api";
import { StatusBadge } from "../components";

export function Executions() {
  const nav = useNavigate();
  const [items, setItems] = useState<Execution[] | null>(null);

  useEffect(() => {
    const load = () => api.listExecutions().then(setItems).catch(() => setItems([]));
    load();
    const t = setInterval(load, 4000); // light polling for the list view
    return () => clearInterval(t);
  }, []);

  return (
    <div>
      <div className="page-head">
        <div>
          <div className="eyebrow">The weave in motion</div>
          <h1 className="page-title">Executions</h1>
        </div>
      </div>
      <div className="panel" style={{ overflow: "hidden" }}>
        {items === null ? <div className="empty">Loading…</div>
          : items.length === 0 ? <div className="empty">No executions yet. Launch a workflow.</div>
          : (
            <table className="table">
              <thead><tr><th>Status</th><th>Workflow</th><th>Execution</th><th>Trigger</th><th>Run id</th><th>Started</th></tr></thead>
              <tbody>
                {items.map((r, i) => (
                  <motion.tr key={r.id} initial={{ opacity: 0 }} animate={{ opacity: 1 }}
                    transition={{ delay: i * 0.02 }} onClick={() => nav(`/executions/${r.id}`)}>
                    <td><StatusBadge status={r.status} /></td>
                    <td style={{ fontWeight: 500 }}>{r.workflow_name ?? "—"}</td>
                    <td className="mono dim">{r.id.slice(0, 8)}</td>
                    <td><span className="pill">{r.trigger_source}</span></td>
                    <td className="mono faint">{r.temporal_run_id?.slice(0, 8) ?? "—"}</td>
                    <td className="dim">{new Date(r.created_at).toLocaleString()}</td>
                  </motion.tr>
                ))}
              </tbody>
            </table>
          )}
      </div>
    </div>
  );
}
