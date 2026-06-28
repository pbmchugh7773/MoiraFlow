// Thin typed client over the MoiraFlow API (single contract; mirrors the OpenAPI).
const BASE = import.meta.env.VITE_API_URL ?? "http://localhost:8001/api/v1";

export type Role = "admin" | "operator" | "developer" | "viewer";
export type Status = "pending" | "running" | "success" | "failed" | "cancelled";

export interface User { id: string; email: string; role: Role; tenant_id: string; is_active: boolean }
export interface Workflow {
  id: string; name: string; description: string | null; trigger_type: string;
  trigger_config: Record<string, unknown>; is_enabled: boolean;
  active_version_id: string | null; created_at: string;
}
export interface WorkflowVersion {
  id: string; version: number; definition_hash: string; source_format: string; created_at: string;
}
export interface Execution {
  id: string; workflow_id: string; workflow_name: string | null;
  workflow_version_id: string; temporal_workflow_id: string;
  temporal_run_id: string | null; status: Status; trigger_source: string;
  input_context: Record<string, unknown>; created_at: string;
}
export interface ExecutionEvent {
  id: number; event_type: string; payload: Record<string, unknown>;
  job_execution_id: string | null; created_at: string;
}
export interface Artifact {
  id: string; name: string; size_bytes: number; content_type: string | null;
  download_url: string; created_at: string;
}
export interface Agent {
  id: string; name: string; status: string; os: string; task_queue: string;
  fingerprint: string | null; labels: Record<string, unknown>;
  last_heartbeat_at: string | null; created_at: string;
}
export interface EnrollToken { enrollment_token: string; temporal_host: string; expires_in: number }
export interface ValidationError { code: string; message: string; loc: string }
export interface ValidationResult { valid: boolean; errors: ValidationError[] }

export interface JobDef { id: string; type?: string; needs?: string[]; with?: Record<string, unknown>; outputs?: Record<string, string> }
export interface WorkflowDefinition {
  apiVersion: string; kind: string; metadata: { name: string };
  spec: { jobs: JobDef[] } & Record<string, unknown>;
}

const TOKEN_KEY = "moiraflow.token";
export const token = {
  get: () => localStorage.getItem(TOKEN_KEY),
  set: (t: string) => localStorage.setItem(TOKEN_KEY, t),
  clear: () => localStorage.removeItem(TOKEN_KEY),
};

export class ApiError extends Error {
  constructor(public status: number, public code: string, message: string, public details?: unknown) {
    super(message);
  }
}

async function request<T>(path: string, opts: RequestInit = {}): Promise<T> {
  const headers: Record<string, string> = { "Content-Type": "application/json", ...(opts.headers as object) };
  const t = token.get();
  if (t) headers.Authorization = `Bearer ${t}`;
  const res = await fetch(BASE + path, { ...opts, headers });
  if (res.status === 204) return undefined as T;
  const body = await res.json().catch(() => ({}));
  if (!res.ok) {
    const e = body?.error ?? {};
    throw new ApiError(res.status, e.code ?? "error", e.message ?? res.statusText, e.details);
  }
  return body as T;
}

export const api = {
  login: (email: string, password: string) =>
    request<{ access_token: string; expires_in: number }>("/auth/login", {
      method: "POST", body: JSON.stringify({ email, password }),
    }),
  me: () => request<User>("/auth/me"),
  refreshToken: () =>
    request<{ access_token: string; expires_in: number }>("/auth/refresh", { method: "POST" }),
  logout: () => request<void>("/auth/logout", { method: "POST" }),

  listWorkflows: () => request<Workflow[]>("/workflows"),
  getWorkflow: (id: string) => request<Workflow>(`/workflows/${id}`),
  deleteWorkflow: (id: string) => request<void>(`/workflows/${id}`, { method: "DELETE" }),
  enableWorkflow: (id: string) => request<Workflow>(`/workflows/${id}/enable`, { method: "POST" }),
  disableWorkflow: (id: string) =>
    request<Workflow>(`/workflows/${id}/disable`, { method: "POST" }),

  listUsers: () => request<User[]>("/users"),
  createUser: (email: string, password: string, role: Role) =>
    request<User>("/users", { method: "POST", body: JSON.stringify({ email, password, role }) }),
  setUserActive: (id: string, active: boolean) =>
    request<User>(`/users/${id}/${active ? "activate" : "deactivate"}`, { method: "POST" }),

  listAgents: () => request<Agent[]>("/agents"),
  enrollAgent: () => request<EnrollToken>("/agents/enroll", { method: "POST" }),
  approveAgent: (id: string) => request<Agent>(`/agents/${id}/approve`, { method: "POST" }),
  revokeAgent: (id: string) => request<Agent>(`/agents/${id}/revoke`, { method: "POST" }),

  listSecretKeys: () => request<{ keys: string[] }>("/secrets"),
  putSecret: (key: string, value: string) =>
    request<void>(`/secrets/${key}`, { method: "PUT", body: JSON.stringify({ value }) }),
  deleteSecret: (key: string) => request<void>(`/secrets/${key}`, { method: "DELETE" }),
  createWorkflow: (content: string, format: "yaml" | "json") =>
    request<Workflow>("/workflows", { method: "POST", body: JSON.stringify({ content, format }) }),
  createVersion: (id: string, content: string, format: "yaml" | "json") =>
    request<WorkflowVersion>(`/workflows/${id}/versions`, {
      method: "POST", body: JSON.stringify({ content, format }),
    }),
  listVersions: (id: string) => request<WorkflowVersion[]>(`/workflows/${id}/versions`),
  getVersion: (id: string, version: number) =>
    request<WorkflowVersion & { definition: WorkflowDefinition }>(`/workflows/${id}/versions/${version}`),
  activate: (id: string, version: number) =>
    request<Workflow>(`/workflows/${id}/activate/${version}`, { method: "POST" }),
  exportWorkflow: (id: string) => `${BASE}/workflows/${id}/export?format=yaml`,
  validate: (content: string, format: "yaml" | "json") =>
    request<ValidationResult>("/workflows/validate", {
      method: "POST", body: JSON.stringify({ content, format }),
    }),

  listExecutions: (workflowId?: string) =>
    request<Execution[]>(`/executions${workflowId ? `?workflow_id=${workflowId}` : ""}`),
  getExecution: (id: string) => request<Execution>(`/executions/${id}`),
  launch: (workflow_id: string, input_context?: Record<string, unknown>) =>
    request<Execution>("/executions", {
      method: "POST",
      body: JSON.stringify({ workflow_id, ...(input_context ? { input_context } : {}) }),
    }),
  replay: (id: string) => request<Execution>(`/executions/${id}/replay`, { method: "POST" }),
  getEvents: (id: string) => request<ExecutionEvent[]>(`/executions/${id}/events`),
  getArtifacts: (id: string) => request<Artifact[]>(`/executions/${id}/artifacts`),
  getExecutionDefinition: (id: string) =>
    request<WorkflowDefinition>(`/executions/${id}/definition`),
};

export function streamUrl(executionId: string): string {
  const t = token.get() ?? "";
  const wsBase = BASE.replace(/^http/, "ws");
  return `${wsBase}/executions/${executionId}/stream?token=${encodeURIComponent(t)}`;
}
