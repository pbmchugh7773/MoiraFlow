import { ReactFlow, Background, type Edge, type Node } from "@xyflow/react";
import { useMemo } from "react";
import type { Status } from "./api";

export function StatusBadge({ status }: { status: Status | string }) {
  return (
    <span className={`status ${status}`}>
      <span className="dot" style={{ background: "currentColor" }} />
      {status}
    </span>
  );
}

interface JobDef { id: string; needs?: string[]; type?: string }

/** Layered left-to-right DAG from job definitions; node tint reflects live status. */
export function DagView({ jobs, statuses }: { jobs: JobDef[]; statuses?: Record<string, string> }) {
  const { nodes, edges } = useMemo(() => buildGraph(jobs, statuses ?? {}), [jobs, statuses]);
  return (
    <div className="rf-wrap">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        fitView
        nodesDraggable={false}
        nodesConnectable={false}
        elementsSelectable={false}
        proOptions={{ hideAttribution: true }}
      >
        <Background color="#2c2833" gap={22} size={1} />
      </ReactFlow>
    </div>
  );
}

const TINT: Record<string, string> = {
  success: "#7fb98f",
  failed: "#d4897a",
  running: "#d8b46a",
};

function buildGraph(jobs: JobDef[], statuses: Record<string, string>): { nodes: Node[]; edges: Edge[] } {
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
    const tint = statuses[j.id] ? TINT[statuses[j.id]] : undefined;
    return {
      id: j.id,
      position: { x: d * 220, y: row * 96 },
      data: { label: nodeLabel(j, statuses[j.id]) },
      style: {
        background: "#211e28",
        color: "#ece8e1",
        border: `1px solid ${tint ?? "#2c2833"}`,
        borderRadius: 9,
        padding: "10px 14px",
        fontSize: 12,
        fontFamily: "IBM Plex Mono, monospace",
        boxShadow: tint ? `0 0 18px -6px ${tint}` : "none",
        width: 170,
      },
    };
  });

  const edges: Edge[] = jobs.flatMap((j) =>
    (j.needs ?? []).map((n) => ({
      id: `${n}->${j.id}`,
      source: n,
      target: j.id,
      animated: statuses[j.id] === "running",
      style: { stroke: "rgba(201,168,106,0.5)" },
    })),
  );
  return { nodes, edges };
}

function nodeLabel(j: JobDef, status?: string): string {
  const mark = status === "success" ? " ✓" : status === "failed" ? " ✕" : status === "running" ? " …" : "";
  return `${j.id}${mark}\n${j.type ?? ""}`;
}
