"""Pure parsing + extraction for the `transform` job (csv / json / xml).

Reads a string payload in the given format and pulls values out with a small,
deterministic path mini-language — no `eval`, so it is safe to run on data the
worker doesn't control. XML is parsed with **defusedxml** to block entity-expansion
(billion-laughs) and external-entity (XXE) attacks.

Path mini-language (used in a job's `outputs`):
- `$`              the whole parsed document
- `$.length`       number of items (when applied to a list/string)
- `$.a.b`          nested dict keys
- `$[0]`           list index
- `$[0].name`      index then key
- `items[*].email` project a key across every element of a list
"""

from __future__ import annotations

import csv
import io
import json
import re
from typing import Any

from defusedxml.ElementTree import fromstring as _xml_fromstring  # type: ignore[import-untyped]

_TOKEN = re.compile(r"[^.\[\]]+|\[\d+\]|\[\*\]")


def parse_source(raw: Any, fmt: str) -> Any:
    """Parse a string payload by format; pass already-structured data through (e.g. a
    JSON object handed in from a prior job's output)."""
    if not isinstance(raw, str):
        return raw
    fmt = fmt.lower()
    if fmt == "json":
        return json.loads(raw)
    if fmt == "csv":
        return list(csv.DictReader(io.StringIO(raw)))
    if fmt == "xml":
        return xml_to_obj(_xml_fromstring(raw))
    raise ValueError(f"unsupported format: {fmt!r}")


def xml_to_obj(elem: Any) -> Any:
    """Convert an XML element to nested dicts/lists/strings. Repeated child tags
    collapse into a list; a leaf element becomes its (stripped) text."""
    children = list(elem)
    if not children:
        return (elem.text or "").strip()
    result: dict[str, Any] = {}
    for child in children:
        value = xml_to_obj(child)
        if child.tag in result:
            existing = result[child.tag]
            if isinstance(existing, list):
                existing.append(value)
            else:
                result[child.tag] = [existing, value]
        else:
            result[child.tag] = value
    return result


def extract_path(data: Any, path: str) -> Any:
    """Resolve a path expression against parsed data (see module docstring)."""
    p = path.strip()
    if p in ("", "$"):
        return data
    if p.startswith("$"):
        p = p[1:]
    p = p.lstrip(".")
    return _walk(data, _TOKEN.findall(p))


def _walk(cur: Any, tokens: list[str]) -> Any:
    for i, tok in enumerate(tokens):
        if tok == "[*]":
            return [_walk(item, tokens[i + 1 :]) for item in cur]
        if tok.startswith("["):
            cur = cur[int(tok[1:-1])]
        elif tok == "length" and not (isinstance(cur, dict) and "length" in cur):
            cur = len(cur)
        else:
            cur = cur[tok]
    return cur
