import { motion } from "framer-motion";
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, type Overview } from "../api";

export function Dashboard() {
  const nav = useNavigate();
  const [ov, setOv] = useState<Overview | null>(null);

  useEffect(() => {
    const load = () => api.getOverview().then(setOv).catch(() => setOv(null));
    load();
    const t = setInterval(load, 5000);
    return () => clearInterval(t);
  }, []);

  const ex = ov?.executions;
  const rate = ex?.success_rate;
  const cards = [
    { label: "Workflows", value: ov?.workflows ?? "—" },
    { label: "Executions", value: ex?.total ?? "—" },
    {
      label: "Success rate",
      value: rate == null ? "—" : `${Math.round(rate * 100)}%`,
      tone: rate == null ? undefined : rate >= 0.9 ? "ok" : rate >= 0.5 ? "run" : "fail",
    },
    { label: "Failed", value: ex?.by_status.failed ?? 0, tone: (ex?.by_status.failed ?? 0) > 0 ? "fail" : undefined },
    { label: "Running", value: ex?.by_status.running ?? 0, tone: (ex?.by_status.running ?? 0) > 0 ? "run" : undefined },
  ];

  return (
    <div>
      <div className="page-head">
        <div>
          <div className="eyebrow">The loom at a glance</div>
          <h1 className="page-title">Overview</h1>
        </div>
      </div>

      <div className="stat-grid">
        {cards.map((c, i) => (
          <motion.div key={c.label} className="stat-card" initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.04 }}>
            <div className="stat-value" style={{ color: c.tone ? `var(--${c.tone})` : undefined }}>{c.value}</div>
            <div className="stat-label">{c.label}</div>
          </motion.div>
        ))}
      </div>

      <div className="dash-cols">
        <div>
          <h3 className="display" style={{ fontSize: 18, margin: "26px 0 12px" }}>Schedules</h3>
          <div className="panel" style={{ overflow: "hidden" }}>
            {!ov?.schedules.length ? (
              <div className="empty">No scheduled (cron) workflows.</div>
            ) : (
              <table className="table">
                <thead><tr><th>Workflow</th><th>Cron</th><th>Timezone</th><th>State</th></tr></thead>
                <tbody>
                  {ov.schedules.map((s) => (
                    <tr key={s.id} onClick={() => nav(`/workflows/${s.id}`)}>
                      <td style={{ fontWeight: 500 }}>{s.name}</td>
                      <td className="mono dim">{s.cron ?? "—"}</td>
                      <td className="dim">{s.timezone ?? "UTC"}</td>
                      <td><span className="status" style={{ color: s.enabled ? "var(--ok)" : "var(--pending)" }}>
                        <span className="dot" style={{ background: "currentColor" }} />{s.enabled ? "enabled" : "paused"}</span></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </div>

        <div>
          <h3 className="display" style={{ fontSize: 18, margin: "26px 0 12px" }}>Recent failures</h3>
          <div className="panel" style={{ overflow: "hidden" }}>
            {!ov?.recent_failures.length ? (
              <div className="empty" style={{ color: "var(--ok)" }}>No recent failures. ✓</div>
            ) : (
              <table className="table">
                <thead><tr><th>Workflow</th><th>When</th></tr></thead>
                <tbody>
                  {ov.recent_failures.map((f) => (
                    <tr key={f.id} onClick={() => nav(`/executions/${f.id}`)}>
                      <td><span className="status failed"><span className="dot" style={{ background: "currentColor" }} />{f.workflow_name ?? "—"}</span></td>
                      <td className="dim">{new Date(f.created_at).toLocaleString()}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
