// Starter templates offered when creating a workflow. Each is a full definition the
// builder seeds from (via fromDefinition); they're scaffolds meant to be customised
// — references like secret://… and example.com URLs are placeholders to edit.
import type { WorkflowDefinition } from "./api";

export interface Template {
  id: string;
  title: string;
  description: string;
  definition: WorkflowDefinition;
}

const def = (name: string, spec: Record<string, unknown>): WorkflowDefinition =>
  ({ apiVersion: "moiraflow/v1", kind: "Workflow", metadata: { name }, spec }) as WorkflowDefinition;

export const TEMPLATES: Template[] = [
  {
    id: "fetch_process",
    title: "Fetch & process API data",
    description: "Call a REST endpoint, parse the JSON, then act on it.",
    definition: def("fetch_and_process", {
      trigger: { type: "manual" },
      context: { endpoint: "https://api.example.com/data" },
      jobs: [
        { id: "fetch", type: "rest", with: { method: "GET", url: "{{ context.endpoint }}", expect_status: [200] } },
        {
          id: "extract", type: "transform", needs: ["fetch"],
          with: { format: "json", content: "{{ jobs.fetch.outputs.body }}" },
          outputs: { count: "$.length" },
        },
        { id: "use", type: "command", needs: ["extract"], with: { command: "echo got {{ jobs.extract.outputs.count }} records" } },
      ],
    }),
  },
  {
    id: "sftp_ingest",
    title: "Ingest a file into the database",
    description: "Pull a CSV over SFTP, parse it, and load rows with SQL.",
    definition: def("sftp_ingest", {
      trigger: { type: "manual" },
      jobs: [
        { id: "pull", type: "file_transfer", with: { source: "sftp://host/in/data.csv", destination: "artifact://data.csv", credentials: "secret://sftp_prod" } },
        { id: "parse", type: "transform", needs: ["pull"], with: { format: "csv", url: "https://replace-with-artifact-url" }, outputs: { rows: "$.length" } },
        { id: "load", type: "sql", needs: ["parse"], with: { connection: "secret://pg_main", statement: "SELECT 1" } },
      ],
    }),
  },
  {
    id: "scheduled_healthcheck",
    title: "Scheduled health check",
    description: "Ping an endpoint on a cron and alert a webhook on failure.",
    definition: def("scheduled_healthcheck", {
      trigger: { type: "cron", cron: "*/15 * * * *" },
      context: { url: "https://example.com/health" },
      notifications: [{ on: "failed", type: "webhook", url: "https://hooks.example.com/alerts" }],
      jobs: [
        { id: "ping", type: "rest", with: { method: "GET", url: "{{ context.url }}", expect_status: [200] } },
      ],
    }),
  },
  {
    id: "all_job_types",
    title: "Every job type (learning demo)",
    description: "rest → transform → command → sql, plus a file_transfer snapshot.",
    definition: def("all_job_types_demo", {
      trigger: { type: "manual" },
      context: { endpoint: "http://host.docker.internal:8000/health/" },
      jobs: [
        { id: "health", type: "rest", with: { method: "GET", url: "{{ context.endpoint }}", expect_status: [200] } },
        { id: "snapshot", type: "file_transfer", with: { source: "{{ context.endpoint }}", destination: "artifact://health-snapshot.json" } },
        {
          id: "extract", type: "transform", needs: ["health"],
          with: { format: "json", content: "{{ jobs.health.outputs.body }}" },
          outputs: { status: "$.status", version: "$.version" },
        },
        { id: "notify", type: "command", needs: ["extract"], with: { command: "echo health={{ jobs.extract.outputs.status }} v={{ jobs.extract.outputs.version }}" } },
        { id: "audit", type: "sql", needs: ["notify"], with: { connection: "secret://pg_demo", statement: "SELECT 1" } },
      ],
    }),
  },
];
