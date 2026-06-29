// Pure model layer for the workflow builder — no React, so it's unit-testable in
// isolation. Each canvas node carries the full job definition in `data`; the node
// id is a stable internal key (`n3`) decoupled from the user-facing `jobId`, so
// renaming a job never disturbs React Flow's nodes/edges. Dependencies (`needs`)
// are derived from edges, not stored on the job.

import type { Edge, Node } from "@xyflow/react";
import { stringify } from "yaml";
import type { WorkflowDefinition } from "./api";

// Single source of truth for job types. The palette, the properties Type dropdown,
// and the node tint all derive from this — add a type here (and a path in JobIcon)
// and it shows up everywhere. Keeps the list from drifting across the UI.
export const JOB_TYPES = [
  { type: "command", tint: "#c9a86a" },
  { type: "rest", tint: "#7fa9d8" },
  { type: "sql", tint: "#9f86c0" },
  { type: "transform", tint: "#7bb89a" },
  { type: "file_transfer", tint: "#d49a6a" },
] as const;

export type JobType = (typeof JOB_TYPES)[number]["type"];
export const JOB_TYPE_LIST: JobType[] = JOB_TYPES.map((j) => j.type);
export const TINT: Record<JobType, string> = Object.fromEntries(
  JOB_TYPES.map((j) => [j.type, j.tint]),
) as Record<JobType, string>;

export type KV = { key: string; value: string };

export interface JobData extends Record<string, unknown> {
  jobId: string;
  type: JobType;
  run_on: "server" | "agent";
  command: string;
  artifacts: string; // space/comma separated paths
  method: string;
  url: string; // rest URL, or transform download URL
  body: string; // JSON text (rest)
  connection: string;
  statement: string;
  format: string; // transform: csv | json | xml
  content: string; // transform: inline data to parse (templatable)
  source: string; // file_transfer: source URI
  destination: string; // file_transfer: destination URI
  credentials: string; // file_transfer: secret://<key> for SFTP
  params: KV[]; // → env (command) | headers (rest) | params (sql)
  outputs: KV[]; // job outputs; for transform the values are path expressions
  timeout: string; // e.g. "30s"
  retries: number; // max_attempts
  condition: string; // run only if truthy, e.g. "{{ context.go }} == yes"
}

export type JobNode = Node<JobData>;

export function blankData(jobId: string, type: JobType): JobData {
  return {
    jobId,
    type,
    run_on: "server",
    command: "echo hello",
    artifacts: "",
    method: "GET",
    url: "https://",
    body: "",
    connection: "secret://pg_main",
    statement: "SELECT 1",
    format: "json",
    content: "",
    source: "",
    destination: "",
    credentials: "",
    params: [],
    outputs: [],
    timeout: "",
    retries: 1,
    condition: "",
  };
}

// ── helpers ──────────────────────────────────────────────────────────────────
export const kvToObj = (kv: KV[]): Record<string, string> =>
  Object.fromEntries(kv.filter((p) => p.key.trim()).map((p) => [p.key.trim(), p.value]));

export const objToKv = (o: Record<string, unknown> | undefined): KV[] =>
  Object.entries(o ?? {}).map(([key, value]) => ({
    key,
    value: typeof value === "string" ? value : JSON.stringify(value),
  }));

// Context values are typed: parse each as JSON (numbers/bools/objects), else keep
// the raw string. Mirrors how the Launch panel reads declared inputs.
export const kvToTypedObj = (rows: KV[]): Record<string, unknown> => {
  const o: Record<string, unknown> = {};
  for (const r of rows) {
    if (!r.key.trim()) continue;
    try { o[r.key.trim()] = JSON.parse(r.value); } catch { o[r.key.trim()] = r.value; }
  }
  return o;
};

export const splitPaths = (s: string): string[] => s.split(/[\s,]+/).filter(Boolean);

export function parseBody(text: string): unknown {
  const t = text.trim();
  if (!t) return undefined;
  try {
    return JSON.parse(t);
  } catch {
    return t; // pass through as a raw string; validation will surface issues
  }
}

export const dep = (source: string, target: string): Edge => ({
  id: `${source}-${target}`, source, target, sourceHandle: "out", targetHandle: "in",
});

/** Would adding source→target create a cycle? True if target already reaches source
 *  (so the new edge would close a loop), or if it's a self-edge. */
export function createsCycle(
  edges: { source: string; target: string }[],
  source: string,
  target: string,
): boolean {
  if (source === target) return true;
  const adj = new Map<string, string[]>();
  for (const e of edges) (adj.get(e.source) ?? adj.set(e.source, []).get(e.source)!).push(e.target);
  const stack = [target];
  const seen = new Set<string>();
  while (stack.length) {
    const x = stack.pop()!;
    if (x === source) return true;
    if (seen.has(x)) continue;
    seen.add(x);
    for (const n of adj.get(x) ?? []) stack.push(n);
  }
  return false;
}

// ── auto-layout (depth-based, left→right) for edit-mode imports ───────────────
export function layout(
  ids: string[],
  needsOf: (id: string) => string[],
): Record<string, { x: number; y: number }> {
  const depth = new Map<string, number>();
  const compute = (id: string, seen = new Set<string>()): number => {
    if (depth.has(id)) return depth.get(id)!;
    if (seen.has(id)) return 0;
    seen.add(id);
    const ns = needsOf(id);
    const d = ns.length ? Math.max(...ns.map((n) => compute(n, seen) + 1)) : 0;
    depth.set(id, d);
    return d;
  };
  ids.forEach((id) => compute(id));
  const perLevel: Record<number, number> = {};
  const pos: Record<string, { x: number; y: number }> = {};
  ids.forEach((id) => {
    const d = depth.get(id) ?? 0;
    const row = perLevel[d] ?? 0;
    perLevel[d] = row + 1;
    pos[id] = { x: 40 + d * 230, y: 40 + row * 120 };
  });
  return pos;
}

// ── import an existing definition into nodes + edges (edit mode) ──────────────
export function fromDefinition(def: WorkflowDefinition): {
  name: string;
  triggerType: "manual" | "cron";
  cron: string;
  tz: string;
  nodes: JobNode[];
  edges: Edge[];
  counter: number;
  context: KV[];
} {
  const jobs = def.spec.jobs ?? [];
  const trigger = (def.spec.trigger ?? {}) as { type?: string; cron?: string; timezone?: string };
  const keyOf = new Map<string, string>(); // jobId → node key
  jobs.forEach((j, i) => keyOf.set(j.id, `n${i + 1}`));
  const needsOf = (jobId: string) => jobs.find((j) => j.id === jobId)?.needs ?? [];
  const pos = layout(jobs.map((j) => j.id), needsOf);

  const nodes: JobNode[] = jobs.map((j) => {
    const w = (j.with ?? {}) as Record<string, unknown>;
    const type = (j.type ?? "command") as JobType;
    const d = blankData(j.id, type);
    d.run_on = (j as { run_on?: string }).run_on === "agent" ? "agent" : "server";
    d.outputs = objToKv(j.outputs as Record<string, unknown>);
    d.timeout = String((j as { timeout?: string }).timeout ?? "");
    d.retries = Number((j as { retry?: { max_attempts?: number } }).retry?.max_attempts ?? 1);
    d.condition = String((j as { condition?: string }).condition ?? "");
    if (type === "command") {
      d.command = String(w.command ?? "");
      d.artifacts = Array.isArray(w.artifacts) ? (w.artifacts as string[]).join(" ") : "";
      d.params = objToKv(w.env as Record<string, unknown>);
    } else if (type === "rest") {
      d.method = String(w.method ?? "GET");
      d.url = String(w.url ?? "");
      d.body = w.body === undefined ? "" : JSON.stringify(w.body, null, 2);
      d.params = objToKv(w.headers as Record<string, unknown>);
    } else if (type === "transform") {
      d.format = String(w.format ?? "json");
      d.url = String(w.url ?? "");
      d.content =
        w.content === undefined
          ? ""
          : typeof w.content === "string"
            ? w.content
            : JSON.stringify(w.content, null, 2);
    } else if (type === "file_transfer") {
      d.source = String(w.source ?? "");
      d.destination = String(w.destination ?? "");
      d.credentials = String(w.credentials ?? "");
    } else {
      d.connection = String(w.connection ?? "");
      d.statement = String(w.statement ?? "");
      d.params = objToKv(w.params as Record<string, unknown>);
    }
    return { id: keyOf.get(j.id)!, type: "job", position: pos[j.id], data: d };
  });

  const edges: Edge[] = jobs.flatMap((j) =>
    needsOf(j.id)
      .filter((n) => keyOf.has(n))
      .map((n) => dep(keyOf.get(n)!, keyOf.get(j.id)!)),
  );

  return {
    name: def.metadata?.name ?? "workflow",
    triggerType: trigger.type === "cron" ? "cron" : "manual",
    cron: trigger.cron ?? "0 6 * * *",
    tz: trigger.timezone ?? "",
    nodes,
    edges,
    counter: jobs.length,
    context: objToKv(def.spec.context as Record<string, unknown> | undefined),
  };
}

// ── YAML generation from the live canvas ─────────────────────────────────────
export function toYaml(
  name: string,
  triggerType: "manual" | "cron",
  cron: string,
  tz: string,
  nodes: JobNode[],
  edges: Edge[],
  context: KV[],
): string {
  const idOf = new Map(nodes.map((n) => [n.id, n.data.jobId]));
  const needsOf = (nodeId: string): string[] =>
    edges.filter((e) => e.target === nodeId).map((e) => idOf.get(e.source) ?? "").filter(Boolean);

  const trigger: Record<string, unknown> =
    triggerType === "cron" ? { type: "cron", cron, ...(tz ? { timezone: tz } : {}) } : { type: "manual" };

  const jobs = nodes.map((n) => {
    const d = n.data;
    const job: Record<string, unknown> = { id: d.jobId, type: d.type };
    if (d.run_on === "agent") job.run_on = "agent";
    const needs = needsOf(n.id);
    if (needs.length) job.needs = needs;
    const params = kvToObj(d.params);
    const hasParams = Object.keys(params).length > 0;
    if (d.type === "command") {
      const arts = splitPaths(d.artifacts);
      job.with = {
        command: d.command,
        ...(hasParams ? { env: params } : {}),
        ...(arts.length ? { artifacts: arts } : {}),
      };
    } else if (d.type === "rest") {
      const body = parseBody(d.body);
      job.with = {
        method: d.method,
        url: d.url,
        ...(hasParams ? { headers: params } : {}),
        ...(body !== undefined ? { body } : {}),
      };
    } else if (d.type === "transform") {
      const url = d.url.trim();
      const hasUrl = url !== "" && url !== "https://";
      job.with = {
        format: d.format,
        ...(hasUrl ? { url } : d.content.trim() ? { content: d.content } : {}),
      };
    } else if (d.type === "file_transfer") {
      job.with = {
        source: d.source,
        destination: d.destination,
        ...(d.credentials.trim() ? { credentials: d.credentials.trim() } : {}),
      };
    } else {
      job.with = {
        connection: d.connection,
        statement: d.statement,
        ...(hasParams ? { params } : {}),
      };
    }
    const outs = kvToObj(d.outputs);
    if (Object.keys(outs).length) job.outputs = outs;
    if (d.timeout.trim()) job.timeout = d.timeout.trim();
    if (d.retries > 1) job.retry = { max_attempts: d.retries };
    if (d.condition.trim()) job.condition = d.condition.trim();
    return job;
  });

  const ctx = kvToTypedObj(context);
  const spec: Record<string, unknown> = {
    trigger,
    ...(Object.keys(ctx).length ? { context: ctx } : {}),
    jobs,
  };
  // Serialize as YAML 1.1: the API parses with PyYAML (1.1), where yes/no/on/off
  // are booleans. The js-yaml default (1.2) leaves them unquoted, so a string
  // value like "yes" would reparse as a bool and fail dict[str,str] validation.
  return stringify(
    { apiVersion: "moiraflow/v1", kind: "Workflow", metadata: { name }, spec },
    { version: "1.1" },
  );
}
