import { describe, expect, it } from "vitest";
import { createsCycle } from "./builder-model";
import { jobIncomplete, jobInfo, type FlowNodeData } from "./FlowNode";

const d = (over: Partial<FlowNodeData>): FlowNodeData => ({ jobId: "x", type: "command", ...over });

describe("createsCycle", () => {
  const E = (s: string, t: string) => ({ source: s, target: t });

  it("flags a self-edge", () => {
    expect(createsCycle([], "a", "a")).toBe(true);
  });

  it("flags an edge that closes a loop", () => {
    // a -> b -> c ; adding c -> a would cycle
    const edges = [E("a", "b"), E("b", "c")];
    expect(createsCycle(edges, "c", "a")).toBe(true);
  });

  it("allows an edge that keeps the graph acyclic", () => {
    const edges = [E("a", "b")];
    expect(createsCycle(edges, "b", "c")).toBe(false);
    expect(createsCycle(edges, "a", "c")).toBe(false);
  });
});

describe("jobInfo (node preview)", () => {
  it("summarizes each job type's key field", () => {
    expect(jobInfo(d({ type: "command", command: "make build" }))).toBe("make build");
    expect(jobInfo(d({ type: "rest", method: "POST", url: "https://x.io" }))).toBe("POST https://x.io");
    expect(jobInfo(d({ type: "file_transfer", source: "https://a", destination: "artifact://b" }))).toBe(
      "https://a → artifact://b",
    );
  });

  it("returns empty for read-only data without the field", () => {
    expect(jobInfo(d({ type: "command" }))).toBe("");
  });
});

describe("jobIncomplete (editor validation hint)", () => {
  it("flags an empty required field in the editor", () => {
    expect(jobIncomplete(d({ type: "command", command: "" }))).toBe(true);
    expect(jobIncomplete(d({ type: "command", command: "echo hi" }))).toBe(false);
    expect(jobIncomplete(d({ type: "rest", url: "https://" }))).toBe(true); // unfilled placeholder
    expect(jobIncomplete(d({ type: "file_transfer", source: "sftp://h/x", destination: "" }))).toBe(true);
  });

  it("never flags read-only data (fields absent)", () => {
    expect(jobIncomplete(d({ type: "command" }))).toBe(false);
    expect(jobIncomplete(d({ type: "rest" }))).toBe(false);
  });
});
