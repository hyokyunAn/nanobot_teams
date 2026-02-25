#!/usr/bin/env python3
"""Jira Data Center MCP server (Bearer/PAT authentication)."""

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


class JiraApiError(RuntimeError):
    """Raised when a Jira API request fails."""


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
    return _require_env("JIRA_BASE_URL").rstrip("/")


def _headers() -> dict[str, str]:
    token = (os.getenv("JIRA_BEARER_TOKEN") or "").strip()
    if not token:
        token = (os.getenv("JIRA_PAT") or "").strip()
    if not token:
        raise ConfigError("Missing required environment variable: JIRA_BEARER_TOKEN (or JIRA_PAT)")
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }


def _timeout_seconds() -> float:
    raw = (os.getenv("JIRA_TIMEOUT_SECONDS") or "").strip()
    if not raw:
        return DEFAULT_TIMEOUT_SECONDS
    try:
        return max(1.0, float(raw))
    except ValueError:
        return DEFAULT_TIMEOUT_SECONDS


def _verify_ssl() -> bool:
    return _to_bool(os.getenv("JIRA_VERIFY_SSL"), default=True)


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
    allow_empty_response: bool = False,
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
        raise JiraApiError(
            f"{method} {path} failed with HTTP {response.status_code}: {body}{trunc_note}"
        )

    if allow_empty_response and (response.status_code == 204 or not response.content):
        return {}

    try:
        return response.json()
    except Exception as exc:
        if allow_empty_response:
            return {}
        raise JiraApiError(f"{method} {path} returned non-JSON response: {exc}") from exc


def _friendly_error(exc: Exception) -> str:
    if isinstance(exc, (ConfigError, JiraApiError)):
        return f"Error: {exc}"
    return f"Error: Unexpected failure: {exc}"


def _browse_url(issue_key: str) -> str:
    return f"{_base_url()}/browse/{issue_key}"


def _issue_summary(issue: dict[str, Any]) -> dict[str, Any]:
    fields = issue.get("fields") or {}
    status = fields.get("status") or {}
    issue_type = fields.get("issuetype") or {}
    assignee = fields.get("assignee") or {}
    reporter = fields.get("reporter") or {}
    priority = fields.get("priority") or {}
    project = fields.get("project") or {}
    return {
        "id": issue.get("id"),
        "key": issue.get("key"),
        "summary": fields.get("summary"),
        "description": fields.get("description"),
        "status": status.get("name"),
        "issueType": issue_type.get("name"),
        "priority": priority.get("name"),
        "project": project.get("key"),
        "assignee": assignee.get("displayName") or assignee.get("name"),
        "reporter": reporter.get("displayName") or reporter.get("name"),
        "labels": fields.get("labels") or [],
        "updated": fields.get("updated"),
        "created": fields.get("created"),
        "url": _browse_url(str(issue.get("key") or "")),
    }


def _build_fields_payload(
    *,
    summary: str | None = None,
    description: str | None = None,
    assignee_name: str | None = None,
    assignee_account_id: str | None = None,
    priority_name: str | None = None,
    labels: list[str] | None = None,
    custom_fields: dict[str, Any] | None = None,
) -> dict[str, Any]:
    fields: dict[str, Any] = {}
    if summary is not None:
        fields["summary"] = summary
    if description is not None:
        fields["description"] = description
    if assignee_account_id:
        fields["assignee"] = {"accountId": assignee_account_id}
    elif assignee_name:
        fields["assignee"] = {"name": assignee_name}
    if priority_name:
        fields["priority"] = {"name": priority_name}
    if labels is not None:
        fields["labels"] = labels
    if custom_fields:
        fields.update(custom_fields)
    return fields


mcp = FastMCP(
    name="jira-datacenter",
    instructions=(
        "Jira Data Center MCP tools using Bearer/PAT authentication. "
        "Set JIRA_BASE_URL and JIRA_BEARER_TOKEN before starting."
    ),
)


@mcp.tool()
async def health() -> str:
    """Verify Jira auth and API reachability."""
    try:
        me = await _request_json("GET", "/rest/api/2/myself")
        return _as_json_text(
            {
                "ok": True,
                "account": me.get("name") or me.get("key") or me.get("displayName"),
                "displayName": me.get("displayName"),
                "message": "Jira API is reachable and token is accepted.",
            }
        )
    except Exception as exc:
        return _friendly_error(exc)


@mcp.tool()
async def get_issue(
    issue_key: str,
    include_comments: bool = True,
    max_comments: int = 20,
) -> str:
    """Read a Jira issue/ticket by key (e.g., GENAI-123)."""
    try:
        key = issue_key.strip().upper()
        if not key:
            return "Error: issue_key is required."

        issue = await _request_json("GET", f"/rest/api/2/issue/{key}")
        out = {"issue": _issue_summary(issue)}

        if include_comments:
            n = max(1, min(max_comments, 100))
            comments = await _request_json(
                "GET",
                f"/rest/api/2/issue/{key}/comment",
                params={"startAt": 0, "maxResults": n},
            )
            out["comments"] = [
                {
                    "id": item.get("id"),
                    "author": ((item.get("author") or {}).get("displayName")),
                    "created": item.get("created"),
                    "updated": item.get("updated"),
                    "body": item.get("body"),
                }
                for item in comments.get("comments", [])
            ]
            out["commentCount"] = len(out["comments"])
        return _as_json_text(out)
    except Exception as exc:
        return _friendly_error(exc)


@mcp.tool()
async def search_issues(
    jql: str,
    max_results: int = 20,
    start_at: int = 0,
) -> str:
    """Search Jira issues using JQL."""
    try:
        if not jql.strip():
            return "Error: jql is required."
        n = max(1, min(max_results, 100))
        s = max(0, start_at)
        data = await _request_json(
            "GET",
            "/rest/api/2/search",
            params={
                "jql": jql.strip(),
                "startAt": s,
                "maxResults": n,
                "fields": "summary,status,issuetype,priority,project,assignee,reporter,labels,updated,created",
            },
        )
        issues = [_issue_summary(item) for item in data.get("issues", [])]
        return _as_json_text(
            {
                "jql": jql.strip(),
                "startAt": s,
                "maxResults": n,
                "total": data.get("total"),
                "count": len(issues),
                "issues": issues,
            }
        )
    except Exception as exc:
        return _friendly_error(exc)


@mcp.tool()
async def create_issue(
    project_key: str,
    summary: str,
    issue_type: str = "Task",
    description: str = "",
    assignee_name: str = "",
    assignee_account_id: str = "",
    priority_name: str = "",
    labels: list[str] | None = None,
    custom_fields: dict[str, Any] | None = None,
) -> str:
    """Create a new Jira issue/ticket."""
    try:
        if not project_key.strip():
            return "Error: project_key is required."
        if not summary.strip():
            return "Error: summary is required."

        fields = _build_fields_payload(
            summary=summary.strip(),
            description=description if description else None,
            assignee_name=assignee_name.strip() or None,
            assignee_account_id=assignee_account_id.strip() or None,
            priority_name=priority_name.strip() or None,
            labels=labels,
            custom_fields=custom_fields,
        )
        fields["project"] = {"key": project_key.strip().upper()}
        fields["issuetype"] = {"name": issue_type.strip() or "Task"}

        created = await _request_json(
            "POST",
            "/rest/api/2/issue",
            payload={"fields": fields},
        )
        key = str(created.get("key") or "")
        return _as_json_text(
            {
                "id": created.get("id"),
                "key": key,
                "url": _browse_url(key) if key else "",
                "message": "Issue created.",
            }
        )
    except Exception as exc:
        return _friendly_error(exc)


@mcp.tool()
async def update_issue(
    issue_key: str,
    summary: str = "",
    description: str = "",
    assignee_name: str = "",
    assignee_account_id: str = "",
    priority_name: str = "",
    labels: list[str] | None = None,
    custom_fields: dict[str, Any] | None = None,
) -> str:
    """Update Jira issue fields (summary/description/assignee/priority/labels/custom fields)."""
    try:
        key = issue_key.strip().upper()
        if not key:
            return "Error: issue_key is required."

        fields = _build_fields_payload(
            summary=summary if summary else None,
            description=description if description else None,
            assignee_name=assignee_name.strip() or None,
            assignee_account_id=assignee_account_id.strip() or None,
            priority_name=priority_name.strip() or None,
            labels=labels,
            custom_fields=custom_fields,
        )
        if not fields:
            return "Error: No fields to update."

        await _request_json(
            "PUT",
            f"/rest/api/2/issue/{key}",
            payload={"fields": fields},
            allow_empty_response=True,
        )
        return _as_json_text(
            {
                "key": key,
                "url": _browse_url(key),
                "updatedFields": sorted(fields.keys()),
                "message": "Issue updated.",
            }
        )
    except Exception as exc:
        return _friendly_error(exc)


@mcp.tool()
async def list_transitions(issue_key: str) -> str:
    """List available status transitions for an issue."""
    try:
        key = issue_key.strip().upper()
        if not key:
            return "Error: issue_key is required."
        data = await _request_json("GET", f"/rest/api/2/issue/{key}/transitions")
        transitions = data.get("transitions", [])
        return _as_json_text(
            {
                "key": key,
                "count": len(transitions),
                "transitions": [
                    {
                        "id": t.get("id"),
                        "name": t.get("name"),
                        "toStatus": ((t.get("to") or {}).get("name")),
                    }
                    for t in transitions
                ],
            }
        )
    except Exception as exc:
        return _friendly_error(exc)


@mcp.tool()
async def transition_issue(
    issue_key: str,
    transition_id: str = "",
    transition_name: str = "",
    comment: str = "",
) -> str:
    """Update Jira issue status using transition id or transition name."""
    try:
        key = issue_key.strip().upper()
        if not key:
            return "Error: issue_key is required."
        tid = transition_id.strip()
        tname = transition_name.strip().lower()
        if not tid and not tname:
            return "Error: Provide transition_id or transition_name."

        if not tid:
            data = await _request_json("GET", f"/rest/api/2/issue/{key}/transitions")
            for t in data.get("transitions", []):
                if str(t.get("name") or "").strip().lower() == tname:
                    tid = str(t.get("id") or "")
                    break
            if not tid:
                return f"Error: transition_name '{transition_name}' not found for issue {key}."

        payload: dict[str, Any] = {"transition": {"id": tid}}
        if comment.strip():
            payload["update"] = {"comment": [{"add": {"body": comment.strip()}}]}

        await _request_json(
            "POST",
            f"/rest/api/2/issue/{key}/transitions",
            payload=payload,
            allow_empty_response=True,
        )

        return _as_json_text(
            {
                "key": key,
                "transitionId": tid,
                "url": _browse_url(key),
                "message": "Issue transitioned (status updated).",
            }
        )
    except Exception as exc:
        return _friendly_error(exc)


@mcp.tool()
async def add_comment(issue_key: str, body: str) -> str:
    """Add a comment to a Jira issue."""
    try:
        key = issue_key.strip().upper()
        if not key:
            return "Error: issue_key is required."
        if not body.strip():
            return "Error: body is required."

        created = await _request_json(
            "POST",
            f"/rest/api/2/issue/{key}/comment",
            payload={"body": body},
        )
        return _as_json_text(
            {
                "key": key,
                "commentId": created.get("id"),
                "created": created.get("created"),
                "url": _browse_url(key),
                "message": "Comment added.",
            }
        )
    except Exception as exc:
        return _friendly_error(exc)


if __name__ == "__main__":
    mcp.run("stdio")
