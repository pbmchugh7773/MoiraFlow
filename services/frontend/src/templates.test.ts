import { describe, expect, it } from "vitest";
import { fromDefinition } from "./builder-model";
import { TEMPLATES } from "./templates";

describe("starter templates", () => {
  it("each template seeds the builder with at least one job and a name", () => {
    for (const t of TEMPLATES) {
      const seed = fromDefinition(t.definition);
      expect(seed.name).toBeTruthy();
      expect(seed.nodes.length).toBeGreaterThan(0);
      // every node carries a job id and a known type
      for (const n of seed.nodes) {
        expect(n.data.jobId).toBeTruthy();
        expect(n.data.type).toBeTruthy();
      }
    }
  });

  it("template ids and titles are unique", () => {
    expect(new Set(TEMPLATES.map((t) => t.id)).size).toBe(TEMPLATES.length);
    expect(new Set(TEMPLATES.map((t) => t.title)).size).toBe(TEMPLATES.length);
  });

  it("derives needs edges from a multi-step template", () => {
    const fetch = TEMPLATES.find((t) => t.id === "fetch_process")!;
    const seed = fromDefinition(fetch.definition);
    expect(seed.edges.length).toBe(2); // fetch->extract->use
  });
});
