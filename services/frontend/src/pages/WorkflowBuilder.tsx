import {
  Background,
  Handle,
  MarkerType,
  Position,
  ReactFlow,
  ReactFlowProvider,
  addEdge,
  useEdgesState,
  useNodesState,
  useReactFlow,
  type Connection,
  type NodeProps,
  type OnSelectionChangeParams,
} from "@xyflow/react";
import { motion } from "framer-motion";
import { useCallback, useMemo, useRef, useState } from "react";
import { api, ApiError, type ValidationError, type WorkflowDefinition } from "../api";
import {
  blankData,
  dep,
  fromDefinition,
  toYaml,
  type JobData,
  type JobNode,
  type JobType,
  type KV,
} from "../builder-model";
import { JobIcon } from "../JobIcon";

const TINT: Record<JobType, string> = {
  command: "#c9a86a",
  rest: "#7fa9d8",
  sql: "#9f86c0",
};

// ── custom node ──────────────────────────────────────────────────────────────
function JobNodeView({ data, selected }: NodeProps<JobNode>) {
  const tint = TINT[data.type];
  return (
    <div className={`flow-node${selected ? " selected" : ""}`} style={{ borderColor: tint }}>
      <Handle id="in" type="target" position={Position.Left} className="flow-handle" />
      <span className="flow-node-icon" style={{ color: tint }}><JobIcon type={data.type} /></span>
      <div className="flow-node-body">
        <div className="flow-node-id mono">{data.jobId || "—"}</div>
        <div className="flow-node-meta">
          <span className="flow-tag" style={{ color: tint, borderColor: tint }}>{data.type}</span>
          {data.run_on === "agent" && <span className="flow-tag agent">agent</span>}
        </div>
      </div>
      <Handle id="out" type="source" position={Position.Right} className="flow-handle" />
    </div>
  );
}

const NODE_TYPES = { job: JobNodeView };

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
    return { name: "daily_import", triggerType: "manual" as const, cron: "0 6 * * *", tz: "", nodes: [n], edges: [], counter: 1, context: [] as KV[] };
  }, [editWorkflow]);

  const [name, setName] = useState(seed.name);
  const [triggerType, setTriggerType] = useState<"manual" | "cron">(seed.triggerType);
  const [cron, setCron] = useState(seed.cron);
  const [tz, setTz] = useState(seed.tz);
  const [context, setContext] = useState<KV[]>(seed.context);
  const [nodes, setNodes, onNodesChange] = useNodesState<JobNode>(seed.nodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState(seed.edges);
  const [tab, setTab] = useState<"visual" | "code">("visual");
  const [selectedId, setSelectedId] = useState<string | null>(seed.nodes[0]?.id ?? null);
  const [errors, setErrors] = useState<ValidationError[] | null>(null);
  const [ok, setOk] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const counter = useRef(seed.counter);
  const { screenToFlowPosition } = useReactFlow();
  const wrapRef = useRef<HTMLDivElement>(null);

  const yaml = useMemo(() => toYaml(name, triggerType, cron, tz, nodes, edges, context), [name, triggerType, cron, tz, nodes, edges, context]);
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
      if (c.source === c.target) return;
      setEdges((es) => addEdge(dep(c.source, c.target), es));
    },
    [setEdges],
  );

  const removeEdge = useCallback(
    (id: string) => setEdges((es) => es.filter((e) => e.id !== id)),
    [setEdges],
  );

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
              {(["command", "rest", "sql"] as JobType[]).map((t) => (
                <div key={t} className="palette-item mono" draggable
                  onDragStart={(e) => { e.dataTransfer.setData("application/moiraflow", t); e.dataTransfer.effectAllowed = "move"; }}
                  onDoubleClick={() => addNode(t, { x: 80 + Math.random() * 120, y: 80 + Math.random() * 80 })}
                  style={{ borderColor: TINT[t], color: TINT[t] }}>
                  <JobIcon type={t} size={13} /> {t}
                </div>
              ))}
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
                fitView
                proOptions={{ hideAttribution: true }}
              >
                <Background color="#2c2833" gap={22} size={1} />
              </ReactFlow>
            </div>
            <div className="faint" style={{ fontSize: 11.5 }}>
              Drag node handles to connect (creates <span className="mono">needs</span>). Double-click a connector — or select it and press <span className="mono">Delete</span> — to remove it. Click a node to edit its properties.
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
            <option value="command">command</option><option value="rest">rest</option><option value="sql">sql</option>
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

      <KvEditor label={paramLabel} rows={data.params} onChange={(params) => onChange({ params })} placeholderKey="name" placeholderValue="value" />
      <KvEditor label="Outputs (expressions)" rows={data.outputs} onChange={(outputs) => onChange({ outputs })} placeholderKey="name" placeholderValue="{{ ... }}" mono />

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
