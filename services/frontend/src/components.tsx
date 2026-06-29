import {
  Background,
  Controls,
  MiniMap,
  ReactFlow,
  type Edge,
  type Node,
} from "@xyflow/react";
import { useMemo, useState } from "react";
import type { Status } from "./api";
import { TINT } from "./builder-model";
import { FlowNode, type FlowNodeData, STATUS_TINT } from "./FlowNode";

export function StatusBadge({ status }: { status: Status | string }) {
  return (
    <span className={`status ${status}`}>
      <span className="dot" style={{ background: "currentColor" }} />
      {status}
    </span>
  );
}

const LEGEND: [string, string][] = [
  ["running", STATUS_TINT.running],
  ["success", STATUS_TINT.success],
  ["failed", STATUS_TINT.failed],
  ["skipped", STATUS_TINT.skipped],
];

/** Colour key for the live execution DAG. */
export function StatusLegend() {
  return (
    <div className="legend">
      {LEGEND.map(([label, color]) => (
        <span key={label} className="legend-item">
          <span className="legend-dot" style={{ background: color }} />
          {label}
        </span>
      ))}
    </div>
  );
}

interface JobInfo {
  id: string;
  type?: string;
  needs?: string[];
  run_on?: string;
  condition?: string;
  with?: Record<string, unknown>;
}

const NODE_TYPES = { job: FlowNode };

/** Layered left-to-right DAG. Rich nodes (icon + type + live status); click a node to
 *  inspect its config. Pan/zoom via Controls + MiniMap for larger graphs. */
export function DagView({ jobs, statuses }: { jobs: JobInfo[]; statuses?: Record<string, string> }) {
  const [selected, setSelected] = useState<string | null>(null);
  const { nodes, edges } = useMemo(() => buildGraph(jobs, statuses ?? {}), [jobs, statuses]);
  const job = jobs.find((j) => j.id === selected) ?? null;

  return (
    <div className="rf-wrap" style={{ position: "relative" }}>
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={NODE_TYPES}
        fitView
        minZoom={0.2}
        nodesDraggable={false}
        nodesConnectable={false}
        elementsSelectable
        onNodeClick={(_, n) => setSelected(n.id)}
        onPaneClick={() => setSelected(null)}
        proOptions={{ hideAttribution: true }}
      >
        <Background color="#2c2833" gap={22} size={1} />
        <Controls showInteractive={false} />
        <MiniMap
          pannable
          zoomable
          maskColor="rgba(16,15,18,0.66)"
          nodeColor={(n) => {
            const d = n.data as FlowNodeData;
            return (d.status && STATUS_TINT[d.status]) || TINT[d.type as keyof typeof TINT] || "#3a3540";
          }}
        />
      </ReactFlow>
      {job && <JobDetails job={job} status={statuses?.[job.id]} onClose={() => setSelected(null)} />}
    </div>
  );
}

function JobDetails({
  job,
  status,
  onClose,
}: {
  job: JobInfo;
  status?: string;
  onClose: () => void;
}) {
  const tint = TINT[(job.type ?? "") as keyof typeof TINT] ?? "#9b9488";
  const entries = Object.entries(job.with ?? {});
  return (
    <div className="job-details">
      <div className="row between" style={{ marginBottom: 8 }}>
        <span className="mono" style={{ color: tint, fontWeight: 600 }}>{job.id}</span>
        <button className="btn btn-ghost" style={{ padding: "2px 8px", fontSize: 14 }} onClick={onClose}>×</button>
      </div>
      <div className="row" style={{ gap: 6, flexWrap: "wrap", marginBottom: 8 }}>
        <span className="pill">{job.type}</span>
        {job.run_on === "agent" && <span className="pill">agent</span>}
        {status && <span className="status" style={{ color: STATUS_TINT[status] }}>{status}</span>}
      </div>
      {job.needs && job.needs.length > 0 && (
        <div className="jd-row"><span className="jd-key">needs</span><span className="mono">{job.needs.join(", ")}</span></div>
      )}
      {job.condition && (
        <div className="jd-row"><span className="jd-key">if</span><span className="mono">{job.condition}</span></div>
      )}
      {entries.map(([k, v]) => (
        <div key={k} className="jd-row">
          <span className="jd-key">{k}</span>
          <span className="mono jd-val">{typeof v === "string" ? v : JSON.stringify(v)}</span>
        </div>
      ))}
    </div>
  );
}

function buildGraph(
  jobs: JobInfo[],
  statuses: Record<string, string>,
): { nodes: Node[]; edges: Edge[] } {
  const byId = new Map(jobs.map((j) => [j.id, j]));
  const depth = new Map<string, number>();
  const compute = (id: string, seen = new Set<string>()): number => {
    if (depth.has(id)) return depth.get(id)!;
    if (seen.has(id)) return 0;
    seen.add(id);
    const needs = byId.get(id)?.needs ?? [];
    const d = needs.length ? Math.max(...needs.map((n) => compute(n, seen) + 1)) : 0;
    depth.set(id, d);
    return d;
  };
  jobs.forEach((j) => compute(j.id));

  const perLevel: Record<number, number> = {};
  const nodes: Node[] = jobs.map((j) => {
    const d = depth.get(j.id) ?? 0;
    const row = perLevel[d] ?? 0;
    perLevel[d] = row + 1;
    return {
      id: j.id,
      type: "job",
      position: { x: d * 230, y: row * 108 },
      data: { jobId: j.id, type: j.type ?? "command", run_on: j.run_on, status: statuses[j.id] },
    };
  });

  const edges: Edge[] = jobs.flatMap((j) =>
    (j.needs ?? []).map((n) => ({
      id: `${n}->${j.id}`,
      source: n,
      target: j.id,
      sourceHandle: "out",
      targetHandle: "in",
      animated: statuses[j.id] === "running",
      style: { stroke: "rgba(201,168,106,0.5)", strokeWidth: 1.6 },
    })),
  );
  return { nodes, edges };
}
