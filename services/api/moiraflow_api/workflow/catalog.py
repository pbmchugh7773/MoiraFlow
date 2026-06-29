"""Machine-readable catalog of built-in job types (AI First — docs 04 §A.6).

Each entry's `input_schema` is the JSON Schema for that job type's `with` block.
The future MoiraFlow Architect reasons over this + the workflow schema to generate
valid definitions; it never touches internal tables.
"""

from __future__ import annotations

from typing import Any

JOB_TYPES: list[dict[str, Any]] = [
    {
        "type": "command",
        "description": "Run a shell command (server-side or on an agent).",
        "input_schema": {
            "type": "object",
            "required": ["command"],
            "additionalProperties": False,
            "properties": {
                "command": {"type": "string", "description": "Shell command to run."},
                "env": {"type": "object", "additionalProperties": {"type": "string"}},
                "working_dir": {"type": "string"},
                "artifacts": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "File paths to upload to object storage after the command.",
                },
            },
        },
        "output_schema": {"type": "object", "description": "Declared outputs (user-defined)."},
    },
    {
        "type": "rest",
        "description": "Perform an HTTP request and assert the response status.",
        "input_schema": {
            "type": "object",
            "required": ["method", "url"],
            "additionalProperties": False,
            "properties": {
                "method": {"enum": ["GET", "POST", "PUT", "DELETE"]},
                "url": {"type": "string"},
                "headers": {"type": "object", "additionalProperties": {"type": "string"}},
                "body": {},
                "expect_status": {"type": "array", "items": {"type": "integer"}},
            },
        },
        "output_schema": {"type": "object", "description": "Declared outputs (user-defined)."},
    },
    {
        "type": "sql",
        "description": "Run a SQL statement against a connection (DSN or secret://key).",
        "input_schema": {
            "type": "object",
            "required": ["connection", "statement"],
            "additionalProperties": False,
            "properties": {
                "connection": {"type": "string", "description": "DSN or secret://<key>."},
                "statement": {"type": "string"},
                "params": {"type": "object"},
            },
        },
        "output_schema": {"type": "object", "description": "Declared outputs (user-defined)."},
    },
    {
        "type": "transform",
        "description": (
            "Parse a csv/json/xml payload and extract values into outputs. Each declared "
            "output is a path expression (e.g. `$.length`, `$[0].email`, `items[*].name`)."
        ),
        "input_schema": {
            "type": "object",
            "required": ["format"],
            "additionalProperties": False,
            "properties": {
                "format": {"enum": ["csv", "json", "xml"]},
                "content": {
                    "description": "Inline data to parse (often templated from a prior job).",
                },
                "url": {"type": "string", "description": "Download the data from this URL."},
            },
        },
        "output_schema": {
            "type": "object",
            "description": "Each value is a path expression evaluated against the parsed data.",
        },
    },
    {
        "type": "file_transfer",
        "description": (
            "Move a file between a source and destination. Schemes: https://, "
            "s3://bucket/key, artifact://key, sftp://host/path. An artifact:// destination "
            "becomes a downloadable execution artifact; SFTP credentials come from secret://."
        ),
        "input_schema": {
            "type": "object",
            "required": ["source", "destination"],
            "additionalProperties": False,
            "properties": {
                "source": {"type": "string", "description": "Source URI."},
                "destination": {"type": "string", "description": "Destination URI."},
                "credentials": {"type": "string", "description": "secret://<key> for SFTP."},
                "source_credentials": {"type": "string"},
                "destination_credentials": {"type": "string"},
            },
        },
        "output_schema": {
            "type": "object",
            "description": "size (bytes) and, for an artifact:// destination, artifact_key.",
        },
    },
]


def job_types_catalog() -> list[dict[str, Any]]:
    return JOB_TYPES
