import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { api, ApiError, token } from "./api";

const BASE = "http://localhost:8001/api/v1";

function fakeResponse(status: number, body: unknown): Response {
  return {
    status,
    ok: status >= 200 && status < 300,
    json: async () => body,
  } as unknown as Response;
}

function mockFetch(status: number, body: unknown) {
  const fn = vi.fn(async () => fakeResponse(status, body));
  vi.stubGlobal("fetch", fn);
  return fn;
}

beforeEach(() => {
  localStorage.clear();
});
afterEach(() => {
  vi.unstubAllGlobals();
});

describe("api client", () => {
  it("sends the bearer token and Content-Type when a token is stored", async () => {
    token.set("t-123");
    const fetchMock = mockFetch(200, { id: "u1", email: "a@b.io", role: "admin" });
    await api.me();
    const [url, opts] = fetchMock.mock.calls[0];
    expect(url).toBe(`${BASE}/auth/me`);
    const headers = opts!.headers as Record<string, string>;
    expect(headers.Authorization).toBe("Bearer t-123");
    expect(headers["Content-Type"]).toBe("application/json");
  });

  it("omits Authorization when there is no token", async () => {
    const fetchMock = mockFetch(200, {});
    await api.listWorkflows();
    const headers = fetchMock.mock.calls[0][1]!.headers as Record<string, string>;
    expect(headers.Authorization).toBeUndefined();
  });

  it("throws ApiError carrying the server error envelope on non-2xx", async () => {
    mockFetch(404, { error: { code: "not_found", message: "execution x not found", details: null } });
    await expect(api.getExecution("x")).rejects.toMatchObject({
      status: 404,
      code: "not_found",
      message: "execution x not found",
    });
    await expect(api.getExecution("x")).rejects.toBeInstanceOf(ApiError);
  });

  it("returns undefined for 204 No Content", async () => {
    mockFetch(204, null);
    await expect(api.logout()).resolves.toBeUndefined();
  });

  it("launch posts only workflow_id when no inputs", async () => {
    const fetchMock = mockFetch(201, { id: "e1", status: "running" });
    await api.launch("wf-1");
    expect(JSON.parse(fetchMock.mock.calls[0][1]!.body as string)).toEqual({ workflow_id: "wf-1" });
  });

  it("launch includes input_context when provided", async () => {
    const fetchMock = mockFetch(201, { id: "e1", status: "running" });
    await api.launch("wf-1", { mode: "run" });
    expect(JSON.parse(fetchMock.mock.calls[0][1]!.body as string)).toEqual({
      workflow_id: "wf-1",
      input_context: { mode: "run" },
    });
  });

  it("createVersion targets the workflow versions endpoint", async () => {
    const fetchMock = mockFetch(201, { id: "v2", version: 2 });
    await api.createVersion("wf-1", "yaml-content", "yaml");
    const [url, opts] = fetchMock.mock.calls[0];
    expect(url).toBe(`${BASE}/workflows/wf-1/versions`);
    expect(opts!.method).toBe("POST");
    expect(JSON.parse(opts!.body as string)).toEqual({ content: "yaml-content", format: "yaml" });
  });
});
