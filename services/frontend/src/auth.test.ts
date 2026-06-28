import { describe, expect, it } from "vitest";
import { canLaunch, canWrite } from "./auth";

describe("RBAC helpers", () => {
  it("canWrite: only admin and developer may author workflows", () => {
    expect(canWrite("admin")).toBe(true);
    expect(canWrite("developer")).toBe(true);
    expect(canWrite("operator")).toBe(false);
    expect(canWrite("viewer")).toBe(false);
    expect(canWrite(undefined)).toBe(false);
  });

  it("canLaunch: admin, developer and operator may launch executions", () => {
    expect(canLaunch("admin")).toBe(true);
    expect(canLaunch("developer")).toBe(true);
    expect(canLaunch("operator")).toBe(true);
    expect(canLaunch("viewer")).toBe(false);
    expect(canLaunch(undefined)).toBe(false);
  });
});
