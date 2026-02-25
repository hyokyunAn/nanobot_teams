#!/usr/bin/env python3
"""Atlassian Confluence MCP server (PAT authentication)."""

from __future__ import annotations

import json
import os
from typing import Any

import httpx
from mcp.server.fastmcp import FastMCP


DEFAULT_TIMEOUT_SECONDS = 30.0
MAX_ERROR_BODY_CHARS = 1200


class ConfigError(RuntimeError):
    """Raised when required environment configuration is missing."""


class ConfluenceApiError(RuntimeError):
    """Raised when a Confluence API request fails."""


def _to_bool(value: str | None, default: bool = True) -> bool:
    if value is None:
        return default
    return value.strip().lower() not in {"0", "false", "no", "off"}


def _require_env(name: str) -> str:
    value = (os.getenv(name) or "").strip()
    if not value:
        raise ConfigError(f"Missing required environment variable: {name}")
    return value


def _base_url() -> str:
    return _require_env("CONFLUENCE_BASE_URL").rstrip("/")


def _headers() -> dict[str, str]:
    pat = (os.getenv("CONFLUENCE_BEARER_TOKEN") or "").strip()
    if not pat:
        pat = (os.getenv("CONFLUENCE_PAT") or "").strip()
    if not pat:
        raise ConfigError(
            "Missing required environment variable: CONFLUENCE_BEARER_TOKEN (or CONFLUENCE_PAT)"
        )
    return {
        "Authorization": f"Bearer {pat}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }


def _timeout_seconds() -> float:
    raw = (os.getenv("CONFLUENCE_TIMEOUT_SECONDS") or "").strip()
    if not raw:
        return DEFAULT_TIMEOUT_SECONDS
    try:
        return max(1.0, float(raw))
    except ValueError:
        return DEFAULT_TIMEOUT_SECONDS


def _verify_ssl() -> bool:
    return _to_bool(os.getenv("CONFLUENCE_VERIFY_SSL"), default=True)


def _truncate(text: str, max_chars: int) -> tuple[str, bool]:
    if len(text) <= max_chars:
        return text, False
    return text[:max_chars], True


def _as_json_text(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2)


async def _request_json(
    method: str,
    path: str,
    *,
    params: dict[str, Any] | None = None,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    url = f"{_base_url()}{path}"
    async with httpx.AsyncClient(timeout=_timeout_seconds(), verify=_verify_ssl()) as client:
        response = await client.request(
            method=method,
            url=url,
            headers=_headers(),
            params=params,
            json=payload,
        )

    if response.status_code >= 400:
        body = response.text or "(empty)"
        body, truncated = _truncate(body, MAX_ERROR_BODY_CHARS)
        trunc_note = " (truncated)" if truncated else ""
        raise ConfluenceApiError(
            f"{method} {path} failed with HTTP {response.status_code}: {body}{trunc_note}"
        )

    try:
        return response.json()
    except Exception as exc:
        raise ConfluenceApiError(f"{method} {path} returned non-JSON response: {exc}") from exc


def _friendly_error(exc: Exception) -> str:
    if isinstance(exc, (ConfigError, ConfluenceApiError)):
        return f"Error: {exc}"
    return f"Error: Unexpected failure: {exc}"


def _search_cql_from_query(query: str) -> str:
    # Escape double quotes for a safe CQL phrase query.
    safe = query.replace("\\", "\\\\").replace('"', '\\"')
    return f'type=page AND text ~ "{safe}" ORDER BY lastmodified DESC'


def _extract_page_summary(item: dict[str, Any]) -> dict[str, Any]:
    links = item.get("_links") or {}
    return {
        "id": item.get("id"),
        "title": item.get("title"),
        "type": item.get("type"),
        "status": item.get("status"),
        "space": ((item.get("space") or {}).get("key")),
        "version": ((item.get("version") or {}).get("number")),
        "webui": links.get("webui"),
    }


def _extract_comment_summary(item: dict[str, Any], *, include_body: bool, max_body_chars: int) -> dict[str, Any]:
    links = item.get("_links") or {}
    out = {
        "id": item.get("id"),
        "type": item.get("type"),
        "status": item.get("status"),
        "version": ((item.get("version") or {}).get("number")),
        "webui": links.get("webui"),
    }
    if include_body:
        body = (((item.get("body") or {}).get("storage") or {}).get("value")) or ""
        clipped, truncated = _truncate(body, max(100, max_body_chars))
        out["bodyStorage"] = clipped
        out["bodyTruncated"] = truncated
        out["bodyLength"] = len(body)
    return out


mcp = FastMCP(
    name="atlassian-confluence",
    instructions=(
        "Confluence MCP tools using Personal Access Token (PAT). "
        "Set CONFLUENCE_BASE_URL and CONFLUENCE_BEARER_TOKEN before starting. "
        "Legacy variable CONFLUENCE_PAT is also supported."
    ),
)


@mcp.tool()
async def health() -> str:
    """Verify Confluence PAT auth and API reachability."""
    try:
        data = await _request_json("GET", "/rest/api/space", params={"limit": 1})
        result = {
            "ok": True,
            "spacesFetched": len(data.get("results", [])),
            "message": "Confluence API is reachable and PAT is accepted.",
        }
        return _as_json_text(result)
    except Exception as exc:
        return _friendly_error(exc)


@mcp.tool()
async def list_spaces(limit: int = 25, start: int = 0) -> str:
    """List Confluence spaces available to the PAT user."""
    try:
        n = max(1, min(limit, 100))
        s = max(0, start)
        data = await _request_json("GET", "/rest/api/space", params={"limit": n, "start": s})
        spaces = []
        for item in data.get("results", []):
            spaces.append(
                {
                    "key": item.get("key"),
                    "name": item.get("name"),
                    "type": item.get("type"),
                }
            )
        return _as_json_text(
            {
                "count": len(spaces),
                "limit": n,
                "start": s,
                "spaces": spaces,
            }
        )
    except Exception as exc:
        return _friendly_error(exc)


@mcp.tool()
async def search_pages(
    query: str = "",
    cql: str = "",
    limit: int = 10,
    start: int = 0,
) -> str:
    """Search Confluence pages via CQL or text query."""
    try:
        n = max(1, min(limit, 50))
        s = max(0, start)
        cql_value = (cql or "").strip()
        if not cql_value:
            if not query.strip():
                return "Error: Provide either query or cql."
            cql_value = _search_cql_from_query(query.strip())

        data = await _request_json(
            "GET",
            "/rest/api/content/search",
            params={"cql": cql_value, "limit": n, "start": s},
        )
        results = [_extract_page_summary(item) for item in data.get("results", [])]
        return _as_json_text(
            {
                "cql": cql_value,
                "count": len(results),
                "limit": n,
                "start": s,
                "results": results,
            }
        )
    except Exception as exc:
        return _friendly_error(exc)


@mcp.tool()
async def get_page(
    page_id: str,
    include_body: bool = True,
    max_body_chars: int = 100000,
) -> str:
    """Get page metadata and storage body by page id."""
    try:
        if not page_id.strip():
            return "Error: page_id is required."

        data = await _request_json(
            "GET",
            f"/rest/api/content/{page_id}",
            params={"expand": "version,space,body.storage"},
        )

        out: dict[str, Any] = {
            "id": data.get("id"),
            "title": data.get("title"),
            "type": data.get("type"),
            "status": data.get("status"),
            "space": ((data.get("space") or {}).get("key")),
            "version": ((data.get("version") or {}).get("number")),
            "webui": ((data.get("_links") or {}).get("webui")),
        }

        if include_body:
            body = (((data.get("body") or {}).get("storage") or {}).get("value")) or ""
            body_max = max(100, max_body_chars)
            clipped, truncated = _truncate(body, body_max)
            out["bodyStorage"] = clipped
            out["bodyTruncated"] = truncated
            out["bodyLength"] = len(body)

        return _as_json_text(out)
    except Exception as exc:
        return _friendly_error(exc)


@mcp.tool()
async def create_page(
    space_key: str,
    title: str,
    body_storage: str,
    parent_id: str = "",
) -> str:
    """Create a Confluence page in storage format."""
    try:
        if not space_key.strip():
            return "Error: space_key is required."
        if not title.strip():
            return "Error: title is required."
        if not body_storage.strip():
            return "Error: body_storage is required."

        payload: dict[str, Any] = {
            "type": "page",
            "title": title,
            "space": {"key": space_key},
            "body": {"storage": {"value": body_storage, "representation": "storage"}},
        }
        if parent_id.strip():
            payload["ancestors"] = [{"id": parent_id.strip()}]

        created = await _request_json("POST", "/rest/api/content", payload=payload)
        return _as_json_text(
            {
                "id": created.get("id"),
                "title": created.get("title"),
                "space": ((created.get("space") or {}).get("key")),
                "webui": ((created.get("_links") or {}).get("webui")),
                "message": "Page created.",
            }
        )
    except Exception as exc:
        return _friendly_error(exc)


@mcp.tool()
async def update_page(
    page_id: str,
    body_storage: str,
    title: str = "",
    minor_edit: bool = False,
    version_message: str = "",
) -> str:
    """Update an existing Confluence page (increments version automatically)."""
    try:
        if not page_id.strip():
            return "Error: page_id is required."
        if not body_storage.strip():
            return "Error: body_storage is required."

        current = await _request_json(
            "GET",
            f"/rest/api/content/{page_id}",
            params={"expand": "version,space"},
        )

        current_version = int(((current.get("version") or {}).get("number")) or 0)
        if current_version <= 0:
            return "Error: Could not read current page version."

        new_title = title.strip() or (current.get("title") or "")
        if not new_title:
            return "Error: Could not determine page title for update."

        version_payload: dict[str, Any] = {
            "number": current_version + 1,
            "minorEdit": bool(minor_edit),
        }
        if version_message.strip():
            version_payload["message"] = version_message.strip()

        payload: dict[str, Any] = {
            "id": str(current.get("id") or page_id),
            "type": current.get("type") or "page",
            "title": new_title,
            "version": version_payload,
            "body": {"storage": {"value": body_storage, "representation": "storage"}},
        }

        updated = await _request_json("PUT", f"/rest/api/content/{page_id}", payload=payload)
        return _as_json_text(
            {
                "id": updated.get("id"),
                "title": updated.get("title"),
                "newVersion": ((updated.get("version") or {}).get("number")),
                "space": ((updated.get("space") or {}).get("key")),
                "webui": ((updated.get("_links") or {}).get("webui")),
                "message": "Page updated.",
            }
        )
    except Exception as exc:
        return _friendly_error(exc)


@mcp.tool()
async def list_page_comments(
    page_id: str,
    limit: int = 25,
    start: int = 0,
    include_body: bool = True,
    max_body_chars: int = 100000,
) -> str:
    """List comments of a Confluence page."""
    try:
        if not page_id.strip():
            return "Error: page_id is required."

        n = max(1, min(limit, 200))
        s = max(0, start)
        data = await _request_json(
            "GET",
            f"/rest/api/content/{page_id}/child/comment",
            params={
                "limit": n,
                "start": s,
                "expand": "version,body.storage",
            },
        )
        comments = [
            _extract_comment_summary(
                item,
                include_body=include_body,
                max_body_chars=max_body_chars,
            )
            for item in data.get("results", [])
        ]
        return _as_json_text(
            {
                "pageId": page_id,
                "count": len(comments),
                "limit": n,
                "start": s,
                "comments": comments,
            }
        )
    except Exception as exc:
        return _friendly_error(exc)


@mcp.tool()
async def add_page_comment(
    page_id: str,
    body_storage: str,
) -> str:
    """Create a comment on a page (storage format)."""
    try:
        if not page_id.strip():
            return "Error: page_id is required."
        if not body_storage.strip():
            return "Error: body_storage is required."

        payload = {
            "type": "comment",
            "container": {"type": "page", "id": page_id.strip()},
            "body": {"storage": {"value": body_storage, "representation": "storage"}},
        }
        created = await _request_json("POST", "/rest/api/content", payload=payload)
        out = _extract_comment_summary(created, include_body=False, max_body_chars=0)
        out["pageId"] = page_id.strip()
        out["message"] = "Comment created."
        return _as_json_text(out)
    except Exception as exc:
        return _friendly_error(exc)


@mcp.tool()
async def list_child_pages(
    page_id: str,
    recursive: bool = False,
    limit: int = 25,
    start: int = 0,
    max_pages: int = 300,
) -> str:
    """List child pages of a parent page. Supports recursive traversal."""
    try:
        if not page_id.strip():
            return "Error: page_id is required."

        parent_id = page_id.strip()
        page_size = max(1, min(limit, 100))

        if not recursive:
            data = await _request_json(
                "GET",
                f"/rest/api/content/{parent_id}/child/page",
                params={"limit": page_size, "start": max(0, start), "expand": "version,space"},
            )
            children = [_extract_page_summary(item) for item in data.get("results", [])]
            return _as_json_text(
                {
                    "parentId": parent_id,
                    "recursive": False,
                    "count": len(children),
                    "limit": page_size,
                    "start": max(0, start),
                    "children": children,
                }
            )

        cap = max(1, min(max_pages, 2000))
        queue = [parent_id]
        seen: set[str] = set()
        out: list[dict[str, Any]] = []

        while queue and len(out) < cap:
            current_parent = queue.pop(0)
            child_start = 0

            while len(out) < cap:
                data = await _request_json(
                    "GET",
                    f"/rest/api/content/{current_parent}/child/page",
                    params={"limit": page_size, "start": child_start, "expand": "version,space"},
                )
                batch = data.get("results", [])
                if not batch:
                    break

                for item in batch:
                    child_id = str(item.get("id") or "").strip()
                    if not child_id or child_id in seen:
                        continue
                    seen.add(child_id)

                    summary = _extract_page_summary(item)
                    summary["parentId"] = current_parent
                    out.append(summary)
                    queue.append(child_id)
                    if len(out) >= cap:
                        break

                if len(batch) < page_size:
                    break
                child_start += page_size

        return _as_json_text(
            {
                "parentId": parent_id,
                "recursive": True,
                "count": len(out),
                "maxPages": cap,
                "children": out,
            }
        )
    except Exception as exc:
        return _friendly_error(exc)


if __name__ == "__main__":
    mcp.run("stdio")
