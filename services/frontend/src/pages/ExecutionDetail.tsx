import { AnimatePresence, motion } from "framer-motion";
import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api, streamUrl, type Execution, type ExecutionEvent } from "../api";
import { StatusBadge } from "../components";

interface Item { type: string; job_id: string | null; payload: Record<string, unknown> }

const fromStored = (e: ExecutionEvent): Item => ({
  type: e.event_type,
  job_id: (e.payload?.job_id as string) ?? null,
  payload: e.payload ?? {},
});

export function ExecutionDetail() {
  const { id = "" } = useParams();
  const [exec, setExec] = useState<Execution | null>(null);
  const [events, setEvents] = useState<Item[]>([]);
  const [status, setStatus] = useState<string>("pending");
  const [live, setLive] = useState(false);
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let ws: WebSocket | null = null;
    api.getExecution(id).then((e) => { setExec(e); setStatus(e.status); }).catch(() => {});
    api.getEvents(id).then((rows) => setEvents(rows.map(fromStored))).catch(() => {});
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

  const jobStatus = useMemo(() => {
    const m: Record<string, string> = {};
    for (const e of events) {
      if (!e.job_id) continue;
      if (e.type === "job_started") m[e.job_id] = "running";
      else if (e.type === "job_succeeded") m[e.job_id] = "success";
      else if (e.type === "job_failed") m[e.job_id] = "failed";
    }
    return m;
  }, [events]);

  return (
    <div>
      <div className="page-head">
        <div>
          <div className="eyebrow">Execution</div>
          <h1 className="page-title mono" style={{ fontSize: 24 }}>{id.slice(0, 8)}</h1>
        </div>
        <div className="row" style={{ gap: 14 }}>
          {live && <span className="status running"><span className="dot" style={{ background: "currentColor" }} />live</span>}
          <StatusBadge status={status} />
        </div>
      </div>

      <div className="row" style={{ gap: 10, marginBottom: 24, flexWrap: "wrap" }}>
        {exec && <span className="pill mono">run {exec.temporal_run_id?.slice(0, 8) ?? "—"}</span>}
        {Object.entries(jobStatus).map(([jid, st]) => (
          <span key={jid} className={`status ${st}`} style={{ border: "1px solid var(--line)", borderRadius: 6, padding: "4px 9px" }}>
            <span className="dot" style={{ background: "currentColor" }} />
            <span className="mono" style={{ color: "var(--text)" }}>{jid}</span>
          </span>
        ))}
      </div>

      <h3 className="display" style={{ fontSize: 18, marginBottom: 14 }}>Event stream</h3>
      <div className="panel" style={{ padding: "20px 24px" }}>
        {events.length === 0 ? <div className="empty">Waiting for the first thread…</div> : (
          <div className="timeline">
            <AnimatePresence initial={false}>
              {events.map((e, i) => (
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

function summary(e: Item): string | null {
  const p = e.payload ?? {};
  if (e.type === "execution_started" && "job_count" in p) return `${p.job_count} jobs`;
  if (e.type === "job_succeeded" && p.outputs && Object.keys(p.outputs as object).length)
    return `outputs: ${JSON.stringify(p.outputs)}`;
  if (e.type === "execution_failed" || e.type === "job_failed") return String(p.error ?? "");
  return null;
}
