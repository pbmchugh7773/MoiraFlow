import type { Edge } from "@xyflow/react";
import { parse } from "yaml";
import { describe, expect, it } from "vitest";
import type { WorkflowDefinition } from "./api";
import {
  blankData,
  dep,
  fromDefinition,
  kvToObj,
  kvToTypedObj,
  objToKv,
  toYaml,
  type JobData,
  type JobNode,
  type JobType,
} from "./builder-model";

// Build a canvas node carrying job data, like the builder does.
function node(key: string, type: JobType, patch: Partial<JobData> = {}): JobNode {
  return { id: key, type: "job", position: { x: 0, y: 0 }, data: { ...blankData(`${type}_x`, type), ...patch } };
}

function yaml(nodes: JobNode[], edges: Edge[] = [], context = []): ReturnType<typeof parse> {
  return parse(toYaml("wf", "manual", "", "", nodes, edges, context));
}

describe("kv helpers", () => {
  it("kvToObj keeps non-empty keys as strings", () => {
    expect(kvToObj([{ key: "A", value: "1" }, { key: "", value: "x" }])).toEqual({ A: "1" });
  });

  it("kvToTypedObj parses JSON values, falls back to string", () => {
    expect(kvToTypedObj([
      { key: "n", value: "5" },
      { key: "flag", value: "true" },
      { key: "name", value: "hello" },
    ])).toEqual({ n: 5, flag: true, name: "hello" });
  });

  it("objToKv stringifies non-string values", () => {
    expect(objToKv({ a: "x", n: 3 })).toEqual([
      { key: "a", value: "x" },
      { key: "n", value: "3" },
    ]);
  });
});

describe("toYaml", () => {
  it("maps a command job's params to env and splits artifacts", () => {
    const out = yaml([
      node("n1", "command", {
        jobId: "build",
        command: "make",
        params: [{ key: "ENV", value: "prod" }],
        artifacts: "out/a.csv out/b.log",
      }),
    ]);
    const job = out.spec.jobs[0];
    expect(job.id).toBe("build");
    expect(job.with).toEqual({ command: "make", env: { ENV: "prod" }, artifacts: ["out/a.csv", "out/b.log"] });
  });

  it("maps a rest job's params to headers and parses the JSON body", () => {
    const job = yaml([
      node("n1", "rest", {
        jobId: "call",
        method: "POST",
        url: "https://x.io",
        params: [{ key: "X-Token", value: "abc" }],
        body: '{"k": 1}',
      }),
    ]).spec.jobs[0];
    expect(job.with).toEqual({ method: "POST", url: "https://x.io", headers: { "X-Token": "abc" }, body: { k: 1 } });
  });

  it("maps a sql job's params and emits condition/timeout/retry", () => {
    const job = yaml([
      node("n1", "sql", {
        jobId: "q",
        connection: "secret://pg",
        statement: "SELECT 1",
        params: [{ key: "lim", value: "10" }],
        condition: "{{ context.go }} == yes",
        timeout: "30s",
        retries: 3,
      }),
    ]).spec.jobs[0];
    expect(job.with).toEqual({ connection: "secret://pg", statement: "SELECT 1", params: { lim: "10" } });
    expect(job.condition).toBe("{{ context.go }} == yes");
    expect(job.timeout).toBe("30s");
    expect(job.retry).toEqual({ max_attempts: 3 });
  });

  it("derives needs from edges (source jobId of incoming edges)", () => {
    const a = node("n1", "command", { jobId: "a" });
    const b = node("n2", "command", { jobId: "b" });
    const out = yaml([a, b], [dep("n1", "n2")]);
    expect(out.spec.jobs.find((j: { id: string }) => j.id === "b").needs).toEqual(["a"]);
    expect(out.spec.jobs.find((j: { id: string }) => j.id === "a").needs).toBeUndefined();
  });

  it("quotes YAML 1.1 booleans so a string output stays a string (regression)", () => {
    // 'yes'/'no'/'on'/'off' are booleans in PyYAML 1.1; they must round-trip as strings.
    const out = yaml([
      node("n1", "command", { jobId: "a", outputs: [{ key: "done", value: "yes" }] }),
    ]);
    expect(out.spec.jobs[0].outputs.done).toBe("yes"); // not boolean true
    expect(typeof out.spec.jobs[0].outputs.done).toBe("string");
  });

  it("emits typed spec.context from the workflow inputs", () => {
    const out = yaml([node("n1", "command", { jobId: "a" })], [], [{ key: "count", value: "5" }]);
    expect(out.spec.context).toEqual({ count: 5 });
  });

  it("omits empty optional sections", () => {
    const job = yaml([node("n1", "command", { jobId: "a", command: "x" })]).spec.jobs[0];
    expect(job.outputs).toBeUndefined();
    expect(job.retry).toBeUndefined();
    expect(job.condition).toBeUndefined();
  });
});

describe("fromDefinition round-trip", () => {
  const def: WorkflowDefinition = {
    apiVersion: "moiraflow/v1",
    kind: "Workflow",
    metadata: { name: "round_trip" },
    spec: {
      context: { mode: "run" },
      trigger: { type: "manual" },
      jobs: [
        { id: "a", type: "command", with: { command: "echo hi", env: { K: "v" } }, outputs: { done: "yes" } },
        { id: "b", type: "rest", needs: ["a"], with: { method: "GET", url: "https://x.io" }, condition: "{{ context.mode }} == run" },
      ],
    },
  } as unknown as WorkflowDefinition;

  it("imports jobs, needs edges, params and context", () => {
    const seed = fromDefinition(def);
    expect(seed.name).toBe("round_trip");
    expect(seed.nodes.map((n) => n.data.jobId)).toEqual(["a", "b"]);
    expect(seed.edges).toHaveLength(1); // a -> b
    expect(seed.nodes[0].data.params).toEqual([{ key: "K", value: "v" }]);
    expect(seed.nodes[1].data.condition).toBe("{{ context.mode }} == run");
    expect(seed.context).toEqual([{ key: "mode", value: "run" }]);
  });

  it("re-serializes to an equivalent definition", () => {
    const seed = fromDefinition(def);
    const out = parse(toYaml(seed.name, seed.triggerType, seed.cron, seed.tz, seed.nodes, seed.edges, seed.context));
    expect(out.spec.context).toEqual({ mode: "run" });
    const b = out.spec.jobs.find((j: { id: string }) => j.id === "b");
    expect(b.needs).toEqual(["a"]);
    expect(b.condition).toBe("{{ context.mode }} == run");
    expect(out.spec.jobs[0].with.env).toEqual({ K: "v" });
  });
});
