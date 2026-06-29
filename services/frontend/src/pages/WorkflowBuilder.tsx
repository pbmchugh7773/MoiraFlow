import {
  Background,
  Controls,
  MarkerType,
  MiniMap,
  ReactFlow,
  ReactFlowProvider,
  addEdge,
  useEdgesState,
  useNodesState,
  useReactFlow,
  type Connection,
  type OnSelectionChangeParams,
} from "@xyflow/react";
import { motion } from "framer-motion";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api, ApiError, type ValidationError, type WorkflowDefinition } from "../api";
import {
  blankData,
  createsCycle,
  dep,
  fromDefinition,
  layout,
  toYaml,
  JOB_TYPE_LIST,
  TINT,
  type JobData,
  type JobNode,
  type JobType,
  type KV,
  type Notif,
} from "../builder-model";
import { FlowNode, jobIncomplete } from "../FlowNode";
import { JobIcon } from "../JobIcon";

const NODE_TYPES = { job: FlowNode };

// Shared edge appearance (initial + drawn edges render identically).
const EDGE_OPTIONS = {
  style: { stroke: "rgba(201,168,106,0.6)", strokeWidth: 1.6 },
  markerEnd: { type: MarkerType.ArrowClosed, color: "rgba(201,168,106,0.75)" },
};

// ─────────────────────────────────────────────────────────────────────────────
// Builder
// ─────────────────────────────────────────────────────────────────────────────

interface BuilderProps {
  /** Edit an existing workflow: saving creates+activates a new version. */
  editWorkflow?: { id: string; definition: WorkflowDefinition };
  onCreated?: () => void;
  onSaved?: () => void;
}

export function WorkflowBuilder(props: BuilderProps) {
  return (
    <ReactFlowProvider>
      <BuilderInner {...props} />
    </ReactFlowProvider>
  );
}

function BuilderInner({ editWorkflow, onCreated, onSaved }: BuilderProps) {
  const seed = useMemo(() => {
    if (editWorkflow) return fromDefinition(editWorkflow.definition);
    const n: JobNode = { id: "n1", type: "job", position: { x: 60, y: 60 }, data: blankData("job_1", "command") };
    return { name: "daily_import", triggerType: "manual" as const, cron: "0 6 * * *", tz: "", nodes: [n], edges: [], counter: 1, context: [] as KV[], notifications: [] as Notif[] };
  }, [editWorkflow]);

  const [name, setName] = useState(seed.name);
  const [triggerType, setTriggerType] = useState<"manual" | "cron">(seed.triggerType);
  const [cron, setCron] = useState(seed.cron);
  const [tz, setTz] = useState(seed.tz);
  const [context, setContext] = useState<KV[]>(seed.context);
  const [notifications, setNotifications] = useState<Notif[]>(seed.notifications);
  const [nodes, setNodes, onNodesChange] = useNodesState<JobNode>(seed.nodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState(seed.edges);
  const [tab, setTab] = useState<"visual" | "code">("visual");
  const [selectedId, setSelectedId] = useState<string | null>(seed.nodes[0]?.id ?? null);
  const [errors, setErrors] = useState<ValidationError[] | null>(null);
  const [ok, setOk] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const counter = useRef(seed.counter);
  const { screenToFlowPosition, fitView } = useReactFlow();
  const wrapRef = useRef<HTMLDivElement>(null);

  const yaml = useMemo(() => toYaml(name, triggerType, cron, tz, nodes, edges, context, notifications), [name, triggerType, cron, tz, nodes, edges, context, notifications]);
  const selected = nodes.find((n) => n.id === selectedId) ?? null;

  const updateData = useCallback(
    (id: string, patch: Partial<JobData>) =>
      setNodes((ns) => ns.map((n) => (n.id === id ? { ...n, data: { ...n.data, ...patch } } : n))),
    [setNodes],
  );

  const addNode = useCallback(
    (type: JobType, position: { x: number; y: number }) => {
      counter.current += 1;
      const id = `n${counter.current}`;
      const jobId = `${type}_${counter.current}`;
      setNodes((ns) => ns.concat({ id, type: "job", position, data: blankData(jobId, type) }));
      setSelectedId(id);
    },
    [setNodes],
  );

  const removeNode = useCallback(
    (id: string) => {
      setNodes((ns) => ns.filter((n) => n.id !== id));
      setEdges((es) => es.filter((e) => e.source !== id && e.target !== id));
      setSelectedId((cur) => (cur === id ? null : cur));
    },
    [setNodes, setEdges],
  );

  const onConnect = useCallback(
    (c: Connection) => {
      if (!c.source || !c.target) return;
      setEdges((es) => {
        if (es.some((e) => e.source === c.source && e.target === c.target)) return es; // dup
        if (createsCycle(es, c.source!, c.target!)) {
          setMsg("That connection would create a cycle.");
          return es;
        }
        return addEdge(dep(c.source!, c.target!), es);
      });
    },
    [setEdges],
  );

  const removeEdge = useCallback(
    (id: string) => setEdges((es) => es.filter((e) => e.id !== id)),
    [setEdges],
  );

  const duplicateNode = useCallback(
    (id: string) => {
      setNodes((ns) => {
        const src = ns.find((n) => n.id === id);
        if (!src) return ns;
        counter.current += 1;
        const newId = `n${counter.current}`;
        const node: JobNode = {
          id: newId,
          type: "job",
          position: { x: src.position.x + 40, y: src.position.y + 64 },
          data: { ...src.data, jobId: `${src.data.jobId}_copy` },
        };
        setSelectedId(newId);
        return ns.concat(node);
      });
    },
    [setNodes],
  );

  const tidy = useCallback(() => {
    setNodes((ns) => {
      const needsOf = (nodeId: string) =>
        edges.filter((e) => e.target === nodeId).map((e) => e.source);
      const pos = layout(ns.map((n) => n.id), needsOf);
      return ns.map((n) => (pos[n.id] ? { ...n, position: pos[n.id] } : n));
    });
    setTimeout(() => fitView({ duration: 350, padding: 0.2 }), 60);
  }, [setNodes, edges, fitView]);

  const onSelectionChange = useCallback((p: OnSelectionChangeParams) => {
    setSelectedId(p.nodes.length === 1 ? p.nodes[0].id : null);
  }, []);

  const onDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      const type = e.dataTransfer.getData("application/moiraflow") as JobType;
      if (!type) return;
      addNode(type, screenToFlowPosition({ x: e.clientX, y: e.clientY }));
    },
    [addNode, screenToFlowPosition],
  );

  const validate = async () => {
    setMsg(null);
    const res = await api.validate(yaml, "yaml");
    setOk(res.valid);
    setErrors(res.valid ? [] : res.errors);
  };

  const save = async () => {
    setMsg(null);
    setErrors(null);
    try {
      if (editWorkflow) {
        const v = await api.createVersion(editWorkflow.id, yaml, "yaml");
        await api.activate(editWorkflow.id, v.version);
        setMsg(`Saved v${v.version} (activated)`);
        onSaved?.();
      } else {
        const wf = await api.createWorkflow(yaml, "yaml");
        setMsg(`Created ${wf.name}`);
        onCreated?.();
      }
    } catch (err) {
      if (err instanceof ApiError) {
        setMsg(err.message);
        if (Array.isArray(err.details)) setErrors(err.details as ValidationError[]);
      }
    }
  };

  // ⌘/Ctrl+Enter saves from anywhere in the builder. A ref keeps the handler current
  // without re-binding the listener each keystroke.
  const saveRef = useRef(save);
  saveRef.current = save;
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === "Enter") {
        e.preventDefault();
        void saveRef.current();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const incompleteCount = nodes.filter((n) => jobIncomplete(n.data)).length;

  return (
    <motion.div className="panel builder" initial={{ opacity: 0, y: -6 }} animate={{ opacity: 1, y: 0 }}>
      {/* workflow-level header */}
      <div className="builder-head">
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
        {triggerType === "cron" && (
          <>
            <div><label className="label">Cron</label>
              <input className="input mono" style={{ width: 130 }} value={cron} onChange={(e) => setCron(e.target.value)} /></div>
            <div><label className="label">Timezone</label>
              <input className="input" style={{ width: 150 }} value={tz} onChange={(e) => setTz(e.target.value)} placeholder="Europe/Madrid" /></div>
          </>
        )}
      </div>

      {/* workflow inputs (spec.context) — declared params, overridable at launch */}
      <div className="builder-inputs">
        <KvEditor label="Workflow inputs (context)" rows={context} onChange={setContext}
          placeholderKey="name" placeholderValue="default (text or JSON)" mono />
        <div style={{ height: 12 }} />
        <NotificationsEditor rows={notifications} onChange={setNotifications} />
      </div>

      {/* tabs */}
      <div className="tabs">
        <button className={`tab${tab === "visual" ? " active" : ""}`} onClick={() => setTab("visual")}>Visual</button>
        <button className={`tab${tab === "code" ? " active" : ""}`} onClick={() => setTab("code")}>Code</button>
      </div>

      {tab === "visual" ? (
        <div className="builder-grid">
          {/* canvas + palette */}
          <div className="stack" style={{ gap: 10 }}>
            <div className="palette">
              <span className="label" style={{ marginRight: 4 }}>Drag onto canvas</span>
              {JOB_TYPE_LIST.map((t) => (
                <div key={t} className="palette-item mono" draggable
                  onDragStart={(e) => { e.dataTransfer.setData("application/moiraflow", t); e.dataTransfer.effectAllowed = "move"; }}
                  onDoubleClick={() => addNode(t, { x: 80 + Math.random() * 120, y: 80 + Math.random() * 80 })}
                  style={{ borderColor: TINT[t], color: TINT[t] }}>
                  <JobIcon type={t} size={13} /> {t}
                </div>
              ))}
              <div className="grow" />
              <button className="btn btn-ghost" style={{ padding: "5px 10px", fontSize: 12 }}
                onClick={() => selectedId && duplicateNode(selectedId)} disabled={!selectedId} title="Duplicate selected node">⧉ Duplicate</button>
              <button className="btn btn-ghost" style={{ padding: "5px 10px", fontSize: 12 }}
                onClick={tidy} disabled={nodes.length === 0} title="Auto-arrange the graph">⤢ Tidy</button>
            </div>
            <div className="rf-edit" ref={wrapRef}
              onDrop={onDrop} onDragOver={(e) => { e.preventDefault(); e.dataTransfer.dropEffect = "move"; }}>
              <ReactFlow
                nodes={nodes}
                edges={edges}
                nodeTypes={NODE_TYPES}
                onNodesChange={onNodesChange}
                onEdgesChange={onEdgesChange}
                onConnect={onConnect}
                onSelectionChange={onSelectionChange}
                onNodeClick={(_, n) => setSelectedId(n.id)}
                onPaneClick={() => setSelectedId(null)}
                onEdgeDoubleClick={(_, e) => removeEdge(e.id)}
                defaultEdgeOptions={EDGE_OPTIONS}
                deleteKeyCode={["Delete", "Backspace"]}
                snapToGrid
                snapGrid={[16, 16]}
                fitView
                minZoom={0.2}
                proOptions={{ hideAttribution: true }}
              >
                <Background color="#2c2833" gap={22} size={1} />
                <Controls showInteractive={false} />
                <MiniMap pannable zoomable maskColor="rgba(16,15,18,0.66)"
                  nodeColor={(n) => TINT[(n.data as { type: JobType }).type] ?? "#3a3540"} />
              </ReactFlow>
              {nodes.length === 0 && (
                <div className="canvas-empty">
                  <div className="display" style={{ fontSize: 16, marginBottom: 6 }}>Empty canvas</div>
                  <div className="faint" style={{ fontSize: 12.5 }}>Drag a job type from the palette, or double-click one to add it.</div>
                </div>
              )}
            </div>
            <div className="faint" style={{ fontSize: 11.5 }}>
              Drag node handles to connect (creates <span className="mono">needs</span>). Double-click a connector — or select it and press <span className="mono">Delete</span> — to remove it. Click a node to edit its properties. Save with <span className="mono">⌘/Ctrl+Enter</span>.
            </div>
          </div>

          {/* properties of selected node */}
          <div className="props">
            {selected ? (
              <PropsPanel
                data={selected.data}
                onChange={(p) => updateData(selected.id, p)}
                onRemove={() => removeNode(selected.id)}
              />
            ) : (
              <div className="empty" style={{ padding: 24, fontSize: 13 }}>
                Select a node to edit its properties, or drag a job type onto the canvas.
              </div>
            )}
          </div>
        </div>
      ) : (
        <div className="stack" style={{ gap: 10 }}>
          <div className="row between">
            <label className="label">Generated workflow-as-code</label>
            <button className="btn btn-ghost" style={{ padding: "5px 11px", fontSize: 12 }}
              onClick={() => navigator.clipboard?.writeText(yaml)}>Copy</button>
          </div>
          <pre className="textarea code-view">{yaml}</pre>
        </div>
      )}

      <hr className="hairline" style={{ margin: "18px 0" }} />
      <div className="row between">
        <div className="row" style={{ gap: 10 }}>
          <button className="btn" onClick={validate}>Validate</button>
          <button className="btn btn-gold" onClick={save}>{editWorkflow ? "Save new version" : "Create"}</button>
        </div>
        {ok && (!errors || errors.length === 0) && <span className="status success"><span className="dot" style={{ background: "currentColor" }} />valid</span>}
        {incompleteCount > 0 && (
          <span className="status" style={{ color: "var(--run)" }}>
            <span className="dot" style={{ background: "currentColor" }} />
            {incompleteCount} job{incompleteCount > 1 ? "s" : ""} missing a required field
          </span>
        )}
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

// ─────────────────────────────────────────────────────────────────────────────
// Properties panel — the old form, now scoped to the selected node.
// ─────────────────────────────────────────────────────────────────────────────

function PropsPanel({ data, onChange, onRemove }: {
  data: JobData;
  onChange: (p: Partial<JobData>) => void;
  onRemove: () => void;
}) {
  const paramLabel = data.type === "command" ? "Environment variables" : data.type === "rest" ? "Headers" : "Query params";
  return (
    <div className="stack" style={{ gap: 14 }}>
      <div className="row between">
        <span className="label">Properties</span>
        <button className="btn btn-ghost" style={{ padding: "4px 9px", fontSize: 12, color: "var(--fail)" }} onClick={onRemove}>Delete node</button>
      </div>

      <div className="row" style={{ gap: 10 }}>
        <div className="grow">
          <label className="label">Job id</label>
          <input className="input mono" value={data.jobId} onChange={(e) => onChange({ jobId: e.target.value })} />
        </div>
        <div>
          <label className="label">Type</label>
          <select className="select" value={data.type} onChange={(e) => onChange({ type: e.target.value as JobType })}>
            {JOB_TYPE_LIST.map((t) => (
              <option key={t} value={t}>{t}</option>
            ))}
          </select>
        </div>
        <div>
          <label className="label">Run on</label>
          <select className="select" value={data.run_on} onChange={(e) => onChange({ run_on: e.target.value as "server" | "agent" })}>
            <option value="server">server</option><option value="agent">agent</option>
          </select>
        </div>
      </div>

      {data.type === "command" && (
        <>
          <Field label="Command">
            <input className="input mono" value={data.command} onChange={(e) => onChange({ command: e.target.value })} placeholder="shell command" />
          </Field>
          <Field label="Artifacts (paths, optional)">
            <input className="input mono" value={data.artifacts} onChange={(e) => onChange({ artifacts: e.target.value })} placeholder="out/report.csv build/*.log" />
          </Field>
        </>
      )}
      {data.type === "rest" && (
        <>
          <div className="row" style={{ gap: 10 }}>
            <div>
              <label className="label">Method</label>
              <select className="select" value={data.method} onChange={(e) => onChange({ method: e.target.value })}>
                {["GET", "POST", "PUT", "PATCH", "DELETE"].map((m) => <option key={m}>{m}</option>)}
              </select>
            </div>
            <div className="grow">
              <label className="label">URL</label>
              <input className="input mono" value={data.url} onChange={(e) => onChange({ url: e.target.value })} placeholder="https://…" />
            </div>
          </div>
          <Field label="Body (JSON, optional)">
            <textarea className="textarea mono" style={{ minHeight: 70 }} value={data.body} onChange={(e) => onChange({ body: e.target.value })} placeholder='{"key": "value"}' />
          </Field>
        </>
      )}
      {data.type === "sql" && (
        <>
          <Field label="Connection">
            <input className="input mono" value={data.connection} onChange={(e) => onChange({ connection: e.target.value })} placeholder="secret://pg_main or dsn" />
          </Field>
          <Field label="Statement">
            <textarea className="textarea mono" style={{ minHeight: 60 }} value={data.statement} onChange={(e) => onChange({ statement: e.target.value })} placeholder="SELECT 1" />
          </Field>
        </>
      )}
      {data.type === "transform" && (
        <>
          <div className="row" style={{ gap: 10 }}>
            <div>
              <label className="label">Format</label>
              <select className="select" value={data.format} onChange={(e) => onChange({ format: e.target.value })}>
                {["json", "csv", "xml"].map((f) => <option key={f}>{f}</option>)}
              </select>
            </div>
            <div className="grow">
              <label className="label">Source URL (optional)</label>
              <input className="input mono" value={data.url} onChange={(e) => onChange({ url: e.target.value })} placeholder="https://… (or use inline content below)" />
            </div>
          </div>
          <Field label="Inline content (optional, templatable)">
            <textarea className="textarea mono" style={{ minHeight: 70 }} value={data.content} onChange={(e) => onChange({ content: e.target.value })} placeholder={'{{ jobs.fetch.outputs.body }}  — or paste raw data'} />
          </Field>
        </>
      )}
      {data.type === "file_transfer" && (
        <>
          <Field label="Source">
            <input className="input mono" value={data.source} onChange={(e) => onChange({ source: e.target.value })} placeholder="https://… · s3://bucket/key · sftp://host/path" />
          </Field>
          <Field label="Destination">
            <input className="input mono" value={data.destination} onChange={(e) => onChange({ destination: e.target.value })} placeholder="artifact://out.csv · s3://bucket/key · sftp://host/path" />
          </Field>
          <Field label="Credentials (optional, for SFTP)">
            <input className="input mono" value={data.credentials} onChange={(e) => onChange({ credentials: e.target.value })} placeholder="secret://sftp_prod" />
          </Field>
        </>
      )}

      {data.type !== "transform" && data.type !== "file_transfer" && (
        <KvEditor label={paramLabel} rows={data.params} onChange={(params) => onChange({ params })} placeholderKey="name" placeholderValue="value" />
      )}
      <KvEditor
        label={data.type === "transform" ? "Outputs (path expressions)" : "Outputs (expressions)"}
        rows={data.outputs} onChange={(outputs) => onChange({ outputs })}
        placeholderKey="name" placeholderValue={data.type === "transform" ? "$.length" : "{{ ... }}"} mono />

      <Field label="Condition (optional) — run only if true">
        <input className="input mono" value={data.condition} onChange={(e) => onChange({ condition: e.target.value })}
          placeholder="{{ context.go }} == yes" />
      </Field>

      <div className="row" style={{ gap: 10 }}>
        <div className="grow">
          <label className="label">Timeout (optional)</label>
          <input className="input mono" value={data.timeout} onChange={(e) => onChange({ timeout: e.target.value })} placeholder="30s" />
        </div>
        <div>
          <label className="label">Max attempts</label>
          <input className="input mono" type="number" min={1} max={100} style={{ width: 90 }} value={data.retries}
            onChange={(e) => onChange({ retries: Math.max(1, Number(e.target.value) || 1) })} />
        </div>
      </div>
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return <div><label className="label">{label}</label>{children}</div>;
}

function NotificationsEditor({ rows, onChange }: {
  rows: Notif[];
  onChange: (rows: Notif[]) => void;
}) {
  const set = (i: number, p: Partial<Notif>) => onChange(rows.map((r, k) => (k === i ? { ...r, ...p } : r)));
  return (
    <div className="stack" style={{ gap: 6 }}>
      <div className="row between">
        <label className="label">Notifications (webhook on outcome)</label>
        <button className="btn btn-ghost" style={{ padding: "3px 9px", fontSize: 11.5 }}
          onClick={() => onChange([...rows, { on: "failed", url: "" }])}>+ Add</button>
      </div>
      {rows.map((r, i) => (
        <div key={i} className="row" style={{ gap: 6 }}>
          <select className="select" style={{ maxWidth: 110 }} value={r.on} onChange={(e) => set(i, { on: e.target.value })}>
            <option value="failed">on failed</option>
            <option value="success">on success</option>
            <option value="always">always</option>
          </select>
          <input className="input mono grow" value={r.url} placeholder="https://hooks.example.com/…"
            onChange={(e) => set(i, { url: e.target.value })} />
          <button className="btn btn-ghost" style={{ padding: "4px 8px", fontSize: 12, color: "var(--fail)" }}
            onClick={() => onChange(rows.filter((_, k) => k !== i))}>×</button>
        </div>
      ))}
    </div>
  );
}

function KvEditor({ label, rows, onChange, placeholderKey, placeholderValue, mono }: {
  label: string;
  rows: KV[];
  onChange: (rows: KV[]) => void;
  placeholderKey: string;
  placeholderValue: string;
  mono?: boolean;
}) {
  const set = (i: number, p: Partial<KV>) => onChange(rows.map((r, k) => (k === i ? { ...r, ...p } : r)));
  return (
    <div className="stack" style={{ gap: 6 }}>
      <div className="row between">
        <label className="label">{label}</label>
        <button className="btn btn-ghost" style={{ padding: "3px 9px", fontSize: 11.5 }} onClick={() => onChange([...rows, { key: "", value: "" }])}>+ Add</button>
      </div>
      {rows.map((r, i) => (
        <div key={i} className="row" style={{ gap: 6 }}>
          <input className={`input${mono ? " mono" : ""}`} style={{ maxWidth: 130 }} value={r.key} placeholder={placeholderKey} onChange={(e) => set(i, { key: e.target.value })} />
          <input className={`input grow${mono ? " mono" : ""}`} value={r.value} placeholder={placeholderValue} onChange={(e) => set(i, { value: e.target.value })} />
          <button className="btn btn-ghost" style={{ padding: "4px 8px", fontSize: 12, color: "var(--fail)" }} onClick={() => onChange(rows.filter((_, k) => k !== i))}>×</button>
        </div>
      ))}
    </div>
  );
}
