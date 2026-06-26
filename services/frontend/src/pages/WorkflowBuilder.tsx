import { motion } from "framer-motion";
import { useMemo, useState } from "react";
import { stringify } from "yaml";
import { api, ApiError, type JobDef, type ValidationError } from "../api";
import { DagView } from "../components";

type JobType = "command" | "rest" | "sql";

interface JobForm {
  id: string;
  type: JobType;
  run_on: "server" | "agent";
  needs: string[];
  command: string;
  method: string;
  url: string;
  connection: string;
  statement: string;
  outputs: { key: string; value: string }[];
}

const newJob = (n: number): JobForm => ({
  id: `job_${n}`,
  type: "command",
  run_on: "server",
  needs: [],
  command: "echo hello",
  method: "GET",
  url: "https://",
  connection: "secret://pg_main",
  statement: "SELECT 1",
  outputs: [],
});

function toYaml(name: string, triggerType: "manual" | "cron", cron: string, tz: string, jobs: JobForm[]): string {
  const trigger: Record<string, unknown> =
    triggerType === "cron" ? { type: "cron", cron, ...(tz ? { timezone: tz } : {}) } : { type: "manual" };
  const spec: Record<string, unknown> = {
    trigger,
    jobs: jobs.map((j) => {
      const job: Record<string, unknown> = { id: j.id, type: j.type };
      if (j.run_on === "agent") job.run_on = "agent";
      if (j.needs.length) job.needs = j.needs;
      if (j.type === "command") job.with = { command: j.command };
      else if (j.type === "rest") job.with = { method: j.method, url: j.url };
      else job.with = { connection: j.connection, statement: j.statement };
      const outs = j.outputs.filter((o) => o.key);
      if (outs.length) job.outputs = Object.fromEntries(outs.map((o) => [o.key, o.value]));
      return job;
    }),
  };
  return stringify({ apiVersion: "moiraflow/v1", kind: "Workflow", metadata: { name }, spec });
}

export function WorkflowBuilder({ onCreated }: { onCreated: () => void }) {
  const [name, setName] = useState("daily_import");
  const [triggerType, setTriggerType] = useState<"manual" | "cron">("manual");
  const [cron, setCron] = useState("0 6 * * *");
  const [tz, setTz] = useState("");
  const [jobs, setJobs] = useState<JobForm[]>([newJob(1)]);
  const [errors, setErrors] = useState<ValidationError[] | null>(null);
  const [ok, setOk] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);

  const yaml = useMemo(() => toYaml(name, triggerType, cron, tz, jobs), [name, triggerType, cron, tz, jobs]);
  const dagJobs: JobDef[] = jobs.map((j) => ({ id: j.id, type: j.type, needs: j.needs }));

  const patch = (i: number, p: Partial<JobForm>) =>
    setJobs((js) => js.map((j, k) => (k === i ? { ...j, ...p } : j)));

  const validate = async () => {
    setMsg(null);
    const res = await api.validate(yaml, "yaml");
    setOk(res.valid);
    setErrors(res.valid ? [] : res.errors);
  };
  const create = async () => {
    setMsg(null);
    try {
      const wf = await api.createWorkflow(yaml, "yaml");
      setMsg(`Created ${wf.name}`);
      onCreated();
    } catch (e) {
      if (e instanceof ApiError) {
        setMsg(e.message);
        if (Array.isArray(e.details)) setErrors(e.details as ValidationError[]);
      }
    }
  };

  return (
    <motion.div className="panel" style={{ padding: 24, marginTop: 4 }}
      initial={{ opacity: 0, y: -6 }} animate={{ opacity: 1, y: 0 }}>
      <div style={{ display: "grid", gridTemplateColumns: "1.1fr 0.9fr", gap: 26 }}>
        {/* ---- form ---- */}
        <div className="stack" style={{ gap: 18 }}>
          <div className="row" style={{ gap: 14 }}>
            <div className="grow">
              <label className="label">Name</label>
              <input className="input" value={name} onChange={(e) => setName(e.target.value)} />
            </div>
            <div>
              <label className="label">Trigger</label>
              <select className="select" value={triggerType} onChange={(e) => setTriggerType(e.target.value as "manual" | "cron")}>
                <option value="manual">manual</option>
                <option value="cron">cron</option>
              </select>
            </div>
          </div>
          {triggerType === "cron" && (
            <div className="row" style={{ gap: 14 }}>
              <div className="grow"><label className="label">Cron</label>
                <input className="input mono" value={cron} onChange={(e) => setCron(e.target.value)} placeholder="0 6 * * *" /></div>
              <div className="grow"><label className="label">Timezone</label>
                <input className="input" value={tz} onChange={(e) => setTz(e.target.value)} placeholder="Europe/Madrid" /></div>
            </div>
          )}

          <div className="row between">
            <span className="label">Jobs</span>
            <button className="btn btn-ghost" style={{ padding: "5px 11px", fontSize: 12 }}
              onClick={() => setJobs((js) => [...js, newJob(js.length + 1)])}>+ Add job</button>
          </div>

          {jobs.map((j, i) => (
            <div key={i} className="panel" style={{ padding: 16, background: "var(--ink-2)" }}>
              <div className="row" style={{ gap: 10, marginBottom: 12 }}>
                <input className="input mono" style={{ maxWidth: 150 }} value={j.id} onChange={(e) => patch(i, { id: e.target.value })} />
                <select className="select" style={{ maxWidth: 110 }} value={j.type} onChange={(e) => patch(i, { type: e.target.value as JobType })}>
                  <option value="command">command</option><option value="rest">rest</option><option value="sql">sql</option>
                </select>
                <select className="select" style={{ maxWidth: 110 }} value={j.run_on} onChange={(e) => patch(i, { run_on: e.target.value as "server" | "agent" })}>
                  <option value="server">server</option><option value="agent">agent</option>
                </select>
                <div className="grow" />
                {jobs.length > 1 && <button className="btn btn-ghost" style={{ padding: "5px 9px", fontSize: 12, color: "var(--fail)" }} onClick={() => setJobs((js) => js.filter((_, k) => k !== i))}>Remove</button>}
              </div>

              {j.type === "command" && (
                <input className="input mono" value={j.command} onChange={(e) => patch(i, { command: e.target.value })} placeholder="shell command" />
              )}
              {j.type === "rest" && (
                <div className="row" style={{ gap: 10 }}>
                  <select className="select" style={{ maxWidth: 100 }} value={j.method} onChange={(e) => patch(i, { method: e.target.value })}>
                    {["GET", "POST", "PUT", "DELETE"].map((m) => <option key={m}>{m}</option>)}
                  </select>
                  <input className="input mono grow" value={j.url} onChange={(e) => patch(i, { url: e.target.value })} placeholder="https://…" />
                </div>
              )}
              {j.type === "sql" && (
                <div className="stack" style={{ gap: 8 }}>
                  <input className="input mono" value={j.connection} onChange={(e) => patch(i, { connection: e.target.value })} placeholder="secret://pg_main or dsn" />
                  <input className="input mono" value={j.statement} onChange={(e) => patch(i, { statement: e.target.value })} placeholder="SQL statement" />
                </div>
              )}

              {jobs.length > 1 && (
                <div style={{ marginTop: 10 }}>
                  <span className="label">Needs</span>
                  <div className="row" style={{ gap: 12, flexWrap: "wrap", marginTop: 6 }}>
                    {jobs.filter((_, k) => k !== i).map((other) => (
                      <label key={other.id} className="row" style={{ gap: 5, fontSize: 12.5, cursor: "pointer" }}>
                        <input type="checkbox" checked={j.needs.includes(other.id)}
                          onChange={(e) => patch(i, { needs: e.target.checked ? [...j.needs, other.id] : j.needs.filter((n) => n !== other.id) })} />
                        <span className="mono">{other.id}</span>
                      </label>
                    ))}
                  </div>
                </div>
              )}
            </div>
          ))}
        </div>

        {/* ---- preview ---- */}
        <div className="stack" style={{ gap: 14 }}>
          <div><label className="label" style={{ display: "block", marginBottom: 8 }}>DAG preview</label>
            {dagJobs.length ? <DagView jobs={dagJobs} /> : null}</div>
          <div>
            <label className="label" style={{ display: "block", marginBottom: 8 }}>Generated workflow-as-code</label>
            <pre className="textarea" style={{ margin: 0, maxHeight: 220, overflow: "auto", whiteSpace: "pre" }}>{yaml}</pre>
          </div>
        </div>
      </div>

      <hr className="hairline" style={{ margin: "20px 0" }} />
      <div className="row between">
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
