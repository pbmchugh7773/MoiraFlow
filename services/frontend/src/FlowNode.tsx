// A rich job node shared by the editor (interactive) and the read-only DAG views.
// Shows the type icon, job id, a type tag, an optional live-status badge, a one-line
// preview of the job's key field, and (in the editor) a warning when required fields
// are missing. Handles are always present so edges render in read-only views too.

import { Handle, Position, type Node, type NodeProps } from "@xyflow/react";
import { JobIcon } from "./JobIcon";
import { TINT } from "./builder-model";

export type FlowNodeData = {
  jobId: string;
  type: string;
  run_on?: string;
  status?: string; // read-only: live execution status
} & Record<string, unknown>;

export const STATUS_TINT: Record<string, string> = {
  success: "#7fb98f",
  failed: "#d4897a",
  running: "#d8b46a",
  skipped: "#8a857c",
  pending: "#8a857c",
  cancelled: "#8a857c",
};

const s = (v: unknown): string => (v == null ? "" : String(v));
const present = (d: FlowNodeData, k: string): boolean => d[k] !== undefined;
const blank = (d: FlowNodeData, k: string): boolean => !s(d[k]).trim();

/** One-line preview of the job's main field (empty when the field isn't loaded). */
export function jobInfo(d: FlowNodeData): string {
  switch (d.type) {
    case "command":
      return s(d.command);
    case "rest":
      return `${s(d.method)} ${s(d.url)}`.trim();
    case "sql":
      return s(d.statement);
    case "transform":
      return `${s(d.format)} ${s(d.url) || (s(d.content) ? "inline" : "")}`.trim();
    case "file_transfer":
      return d.source || d.destination ? `${s(d.source)} → ${s(d.destination)}` : "";
    default:
      return "";
  }
}

/** Whether the (editor) node is missing a required field. False in read-only views,
 *  where the type-specific fields aren't present on the node data. */
export function jobIncomplete(d: FlowNodeData): boolean {
  switch (d.type) {
    case "command":
      return present(d, "command") && blank(d, "command");
    case "rest":
      return present(d, "url") && (blank(d, "url") || d.url === "https://");
    case "sql":
      return present(d, "statement") && (blank(d, "statement") || blank(d, "connection"));
    case "transform":
      return (
        present(d, "format") && blank(d, "content") && (blank(d, "url") || d.url === "https://")
      );
    case "file_transfer":
      return present(d, "source") && (blank(d, "source") || blank(d, "destination"));
    default:
      return false;
  }
}

export function FlowNode({ data, selected }: NodeProps<Node<FlowNodeData>>) {
  const tint = TINT[data.type as keyof typeof TINT] ?? "#9b9488";
  const statusTint = data.status ? STATUS_TINT[data.status] : undefined;
  const info = jobInfo(data);
  const incomplete = jobIncomplete(data);
  return (
    <div
      className={`flow-node${selected ? " selected" : ""}`}
      style={{
        borderColor: statusTint ?? tint,
        boxShadow: statusTint ? `0 0 20px -6px ${statusTint}` : undefined,
      }}
    >
      <Handle id="in" type="target" position={Position.Left} className="flow-handle" />
      <span className="flow-node-icon" style={{ color: tint }}>
        <JobIcon type={data.type} />
      </span>
      <div className="flow-node-body">
        <div className="flow-node-id mono">{data.jobId || "—"}</div>
        <div className="flow-node-meta">
          <span className="flow-tag" style={{ color: tint, borderColor: tint }}>{data.type}</span>
          {data.run_on === "agent" && <span className="flow-tag agent">agent</span>}
          {data.status && (
            <span className={`flow-status s-${data.status}`} style={{ color: statusTint }}>
              {data.status}
            </span>
          )}
        </div>
        {info && <div className="flow-node-info mono" title={info}>{info}</div>}
      </div>
      {incomplete && <span className="flow-node-warn" title="Missing a required field">!</span>}
      <Handle id="out" type="source" position={Position.Right} className="flow-handle" />
    </div>
  );
}
