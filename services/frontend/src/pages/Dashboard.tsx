import { motion } from "framer-motion";
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, type ActivityDay, type Overview } from "../api";

const STATUS_TINT: Record<string, string> = {
  success: "#7fb98f",
  failed: "#d4897a",
  running: "#d8b46a",
  cancelled: "#8a857c",
  pending: "#8a857c",
};

function ago(iso: string): string {
  const s = (Date.now() - new Date(iso).getTime()) / 1000;
  if (s < 60) return "just now";
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
  return `${Math.floor(s / 86400)}d ago`;
}
function dur(sec: number | null): string {
  if (sec == null) return "—";
  if (sec < 1) return "<1s";
  if (sec < 60) return `${sec < 10 ? sec.toFixed(1) : Math.round(sec)}s`;
  return `${Math.floor(sec / 60)}m ${Math.round(sec % 60)}s`;
}
function weekday(date: string): string {
  return new Date(`${date}T00:00:00`).toLocaleDateString(undefined, { weekday: "short" });
}

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

      <div className="panel dash-activity">
        <div className="row between" style={{ marginBottom: 16 }}>
          <h3 className="display" style={{ fontSize: 17 }}>Execution activity · last 7 days</h3>
          <StatusBreakdown byStatus={ex?.by_status ?? {}} />
        </div>
        <ActivityChart days={ov?.activity ?? []} />
      </div>

      <div className="dash-cols">
        <div>
          <h3 className="display" style={{ fontSize: 18, margin: "26px 0 12px" }}>Recent runs</h3>
          <div className="panel" style={{ overflow: "hidden" }}>
            {!ov?.recent_executions.length ? (
              <div className="empty">No executions yet.</div>
            ) : (
              <table className="table">
                <thead><tr><th>Workflow</th><th>Status</th><th>Duration</th><th>When</th></tr></thead>
                <tbody>
                  {ov.recent_executions.map((r) => (
                    <tr key={r.id} onClick={() => nav(`/executions/${r.id}`)}>
                      <td style={{ fontWeight: 500 }}>{r.workflow_name ?? "—"}</td>
                      <td><span className={`status ${r.status}`}><span className="dot" style={{ background: "currentColor" }} />{r.status}</span></td>
                      <td className="mono dim">{dur(r.duration_seconds)}</td>
                      <td className="dim">{ago(r.created_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </div>

        <div>
          <h3 className="display" style={{ fontSize: 18, margin: "26px 0 12px" }}>Schedules</h3>
          <div className="panel" style={{ overflow: "hidden" }}>
            {!ov?.schedules.length ? (
              <div className="empty">No scheduled (cron) workflows.</div>
            ) : (
              <table className="table">
                <thead><tr><th>Workflow</th><th>Cron</th><th>State</th></tr></thead>
                <tbody>
                  {ov.schedules.map((s) => (
                    <tr key={s.id} onClick={() => nav(`/workflows/${s.id}`)}>
                      <td style={{ fontWeight: 500 }}>{s.name}</td>
                      <td className="mono dim" title={s.timezone ?? "UTC"}>{s.cron ?? "—"}</td>
                      <td><span className="status" style={{ color: s.enabled ? "var(--ok)" : "var(--pending)" }}>
                        <span className="dot" style={{ background: "currentColor" }} />{s.enabled ? "enabled" : "paused"}</span></td>
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

function ActivityChart({ days }: { days: ActivityDay[] }) {
  if (!days.length) return <div className="empty" style={{ border: 0 }}>No activity.</div>;
  const max = Math.max(1, ...days.map((d) => d.total));
  return (
    <div className="act-chart">
      {days.map((d) => {
        const other = Math.max(0, d.total - d.success - d.failed);
        const h = (n: number) => `${(n / max) * 100}%`;
        const isToday = d.date === days[days.length - 1].date;
        return (
          <div key={d.date} className="act-col" title={`${d.date}\n${d.total} runs · ${d.success} ok · ${d.failed} failed`}>
            <div className="act-bar-track">
              <div className="act-bar">
                {d.failed > 0 && <div className="act-seg" style={{ height: h(d.failed), background: STATUS_TINT.failed }} />}
                {other > 0 && <div className="act-seg" style={{ height: h(other), background: STATUS_TINT.running }} />}
                {d.success > 0 && <div className="act-seg" style={{ height: h(d.success), background: STATUS_TINT.success }} />}
              </div>
            </div>
            <div className={`act-label${isToday ? " today" : ""}`}>{weekday(d.date)}</div>
            <div className="act-count">{d.total || ""}</div>
          </div>
        );
      })}
    </div>
  );
}

function StatusBreakdown({ byStatus }: { byStatus: Record<string, number> }) {
  const order = ["success", "running", "failed", "cancelled", "pending"];
  const entries = order.filter((s) => (byStatus[s] ?? 0) > 0).map((s) => [s, byStatus[s]] as const);
  const total = entries.reduce((a, [, n]) => a + n, 0);
  if (!total) return null;
  return (
    <div className="status-breakdown">
      <div className="status-bar">
        {entries.map(([s, n]) => (
          <div key={s} className="status-seg" title={`${s}: ${n}`}
            style={{ width: `${(n / total) * 100}%`, background: STATUS_TINT[s] }} />
        ))}
      </div>
      <div className="status-legend">
        {entries.map(([s, n]) => (
          <span key={s} className="sl-item"><span className="sl-dot" style={{ background: STATUS_TINT[s] }} />{s} {n}</span>
        ))}
      </div>
    </div>
  );
}
