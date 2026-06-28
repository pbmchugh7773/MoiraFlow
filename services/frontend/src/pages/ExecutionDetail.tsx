import { AnimatePresence, motion } from "framer-motion";
import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api, streamUrl, type Artifact, type Execution, type ExecutionEvent, type JobDef } from "../api";
import { canLaunch, useAuth } from "../auth";
import { DagView, StatusBadge } from "../components";

interface Item { type: string; job_id: string | null; payload: Record<string, unknown> }

const fromStored = (e: ExecutionEvent): Item => ({
  type: e.event_type,
  job_id: (e.payload?.job_id as string) ?? null,
  payload: e.payload ?? {},
});

export function ExecutionDetail() {
  const { id = "" } = useParams();
  const { user } = useAuth();
  const nav = useNavigate();
  const [exec, setExec] = useState<Execution | null>(null);
  const [events, setEvents] = useState<Item[]>([]);
  const [jobs, setJobs] = useState<JobDef[]>([]);
  const [artifacts, setArtifacts] = useState<Artifact[]>([]);
  const [status, setStatus] = useState<string>("pending");
  const [live, setLive] = useState(false);
  const endRef = useRef<HTMLDivElement>(null);
  const logEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let ws: WebSocket | null = null;
    api.getExecution(id).then((e) => { setExec(e); setStatus(e.status); }).catch(() => {});
    api.getEvents(id).then((rows) => setEvents(rows.map(fromStored))).catch(() => {});
    api.getExecutionDefinition(id).then((d) => setJobs(d.spec.jobs ?? [])).catch(() => {});
    try {
      ws = new WebSocket(streamUrl(id));
      ws.onopen = () => setLive(true);
      ws.onclose = () => setLive(false);
      ws.onmessage = (m) => {
        const ev = JSON.parse(m.data);
        setEvents((prev) => [...prev, { type: ev.type, job_id: ev.job_id ?? null, payload: ev.payload ?? {} }]);
        if (ev.type === "execution_finished") setStatus("success");
        else if (ev.type === "execution_failed") setStatus("failed");
        else if (ev.type === "execution_started") setStatus("running");
      };
    } catch { /* ws unsupported */ }
    return () => ws?.close();
  }, [id]);

  useEffect(() => { endRef.current?.scrollIntoView({ behavior: "smooth" }); }, [events.length]);

  // artifacts appear once jobs finish; refetch when the run reaches a terminal state
  useEffect(() => {
    api.getArtifacts(id).then(setArtifacts).catch(() => {});
  }, [id, status]);

  const jobStatus = useMemo(() => {
    const m: Record<string, string> = {};
    for (const e of events) {
      if (!e.job_id) continue;
      if (e.type === "job_started") m[e.job_id] = "running";
      else if (e.type === "job_succeeded") m[e.job_id] = "success";
      else if (e.type === "job_failed") m[e.job_id] = "failed";
      else if (e.type === "job_skipped") m[e.job_id] = "skipped";
    }
    return m;
  }, [events]);

  const logs = useMemo(() => events.filter((e) => e.type === "job_log"), [events]);
  const timeline = useMemo(() => events.filter((e) => e.type !== "job_log"), [events]);
  useEffect(() => { logEndRef.current?.scrollIntoView({ behavior: "smooth" }); }, [logs.length]);

  return (
    <div>
      <div className="page-head">
        <div>
          <div className="eyebrow">Execution</div>
          <h1 className="page-title" style={{ fontSize: 24 }}>{exec?.workflow_name ?? id.slice(0, 8)}</h1>
          {exec?.workflow_name && <div className="mono faint" style={{ fontSize: 12, marginTop: 4 }}>{id.slice(0, 8)}</div>}
        </div>
        <div className="row" style={{ gap: 14 }}>
          {live && <span className="status running"><span className="dot" style={{ background: "currentColor" }} />live</span>}
          <StatusBadge status={status} />
          {canLaunch(user?.role) && status !== "running" && (
            <button className="btn" onClick={() => api.replay(id).then((e) => nav(`/executions/${e.id}`)).catch(() => {})}>
              Replay
            </button>
          )}
        </div>
      </div>

      <div className="row" style={{ gap: 10, marginBottom: 24, flexWrap: "wrap" }}>
        {exec && <span className="pill mono">run {exec.temporal_run_id?.slice(0, 8) ?? "—"}</span>}
      </div>

      {jobs.length > 0 && (
        <div style={{ marginBottom: 28 }}>
          <h3 className="display" style={{ fontSize: 18, marginBottom: 14 }}>The weave</h3>
          <DagView jobs={jobs} statuses={jobStatus} />
        </div>
      )}

      {artifacts.length > 0 && (
        <div style={{ marginBottom: 28 }}>
          <h3 className="display" style={{ fontSize: 18, marginBottom: 14 }}>Artifacts</h3>
          <div className="panel" style={{ overflow: "hidden" }}>
            <table className="table">
              <thead><tr><th>Name</th><th>Type</th><th>Size</th><th></th></tr></thead>
              <tbody>
                {artifacts.map((a) => (
                  <tr key={a.id}>
                    <td className="mono">{a.name}</td>
                    <td className="dim">{a.content_type ?? "—"}</td>
                    <td className="dim">{a.size_bytes} B</td>
                    <td style={{ textAlign: "right" }}>
                      <a className="btn btn-ghost" style={{ padding: "4px 10px", fontSize: 12 }}
                        href={a.download_url} target="_blank" rel="noreferrer">Download</a>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {logs.length > 0 && (
        <div style={{ marginBottom: 28 }}>
          <h3 className="display" style={{ fontSize: 18, marginBottom: 14 }}>Logs</h3>
          <div className="logbox">
            {logs.map((e, i) => (
              <div key={i} className="logline">
                <span className="logts">{fmtTime(e.payload.ts)}</span>
                {e.job_id && <span className="logjob">{e.job_id}</span>}
                <span>{String(e.payload.line ?? "")}</span>
              </div>
            ))}
            <div ref={logEndRef} />
          </div>
        </div>
      )}

      <h3 className="display" style={{ fontSize: 18, marginBottom: 14 }}>Event stream</h3>
      <div className="panel" style={{ padding: "20px 24px" }}>
        {timeline.length === 0 ? <div className="empty">Waiting for the first thread…</div> : (
          <div className="timeline">
            <AnimatePresence initial={false}>
              {timeline.map((e, i) => (
                <motion.div key={i} className="tl-item"
                  initial={{ opacity: 0, x: -8 }} animate={{ opacity: 1, x: 0 }} transition={{ duration: 0.25 }}>
                  <div className="row" style={{ gap: 10 }}>
                    <span className="tl-type">{e.type}</span>
                    {e.job_id && <span className="pill">{e.job_id}</span>}
                  </div>
                  {summary(e) && <div className="tl-meta">{summary(e)}</div>}
                </motion.div>
              ))}
            </AnimatePresence>
            <div ref={endRef} />
          </div>
        )}
      </div>

      <Link to="/executions" className="dim" style={{ fontSize: 13, display: "inline-block", marginTop: 20 }}>← All executions</Link>
    </div>
  );
}

function fmtTime(ts: unknown): string {
  if (typeof ts !== "string") return "";
  const d = new Date(ts);
  if (isNaN(d.getTime())) return "";
  return d.toLocaleTimeString(undefined, { hour12: false }) +
    "." + String(d.getMilliseconds()).padStart(3, "0");
}

function summary(e: Item): string | null {
  const p = e.payload ?? {};
  if (e.type === "execution_started" && "job_count" in p) return `${p.job_count} jobs`;
  if (e.type === "job_succeeded" && p.outputs && Object.keys(p.outputs as object).length)
    return `outputs: ${JSON.stringify(p.outputs)}`;
  if (e.type === "execution_failed" || e.type === "job_failed") return String(p.error ?? "");
  return null;
}
