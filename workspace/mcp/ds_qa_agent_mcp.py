#!/usr/bin/env python3
"""DS QA Agent MCP server backed by Confluence Data Center pages."""

from __future__ import annotations

import html
import json
import os
import re
import time
from dataclasses import dataclass
from typing import Any

import httpx
from mcp.server.fastmcp import FastMCP


DEFAULT_TIMEOUT_SECONDS = 30.0
DEFAULT_CACHE_TTL_SECONDS = 300.0
DEFAULT_MAX_PAGES = 300
MAX_ERROR_BODY_CHARS = 1200
TOKEN_RE = re.compile(r"[A-Za-z0-9가-힣_]{2,}")
PAGE_ID_RE = re.compile(r"/pages/(\d+)")

STOPWORDS = {
    "the", "and", "for", "with", "that", "this", "from", "have", "has",
    "are", "was", "were", "you", "your", "about", "into", "using",
    "은", "는", "이", "가", "을", "를", "에", "의", "와", "과", "그리고",
    "또는", "에서", "하다", "합니다", "있다", "없다", "하는", "대한",
}


class ConfigError(RuntimeError):
    """Raised when required environment configuration is missing."""


class ConfluenceApiError(RuntimeError):
    """Raised when a Confluence API request fails."""


@dataclass
class CachedDoc:
    id: str
    title: str
    space: str
    webui: str
    text: str
    token_freq: dict[str, int]


_CACHE: dict[str, Any] = {
    "loaded_at": 0.0,
    "prompt_page": None,
    "db_root_page": None,
    "docs": [],
}


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


def _bearer_token() -> str:
    token = (os.getenv("CONFLUENCE_BEARER_TOKEN") or "").strip()
    if not token:
        token = (os.getenv("CONFLUENCE_PAT") or "").strip()
    if not token:
        raise ConfigError(
            "Missing required env: CONFLUENCE_BEARER_TOKEN (or legacy CONFLUENCE_PAT)"
        )
    return token


def _headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {_bearer_token()}",
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


def _cache_ttl_seconds() -> float:
    raw = (os.getenv("DS_QA_CACHE_TTL_SECONDS") or "").strip()
    if not raw:
        return DEFAULT_CACHE_TTL_SECONDS
    try:
        return max(10.0, float(raw))
    except ValueError:
        return DEFAULT_CACHE_TTL_SECONDS


def _max_pages() -> int:
    raw = (os.getenv("DS_QA_MAX_PAGES") or "").strip()
    if not raw:
        return DEFAULT_MAX_PAGES
    try:
        return max(1, min(int(raw), 2000))
    except ValueError:
        return DEFAULT_MAX_PAGES


def _truncate(text: str, max_chars: int) -> tuple[str, bool]:
    if len(text) <= max_chars:
        return text, False
    return text[:max_chars], True


def _as_json_text(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2)


def _extract_page_id_from_url(url: str) -> str:
    m = PAGE_ID_RE.search(url)
    if not m:
        raise ConfigError(f"Failed to parse page id from URL: {url}")
    return m.group(1)


def _resolve_page_id(*, id_env: str, url_env: str, default_url: str) -> str:
    direct = (os.getenv(id_env) or "").strip()
    if direct:
        return direct
    url = (os.getenv(url_env) or default_url).strip()
    if not url:
        raise ConfigError(f"Missing required env: {id_env} or {url_env}")
    return _extract_page_id_from_url(url)


def _clean_storage_to_text(storage: str) -> str:
    text = storage
    text = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", text)
    text = re.sub(r"(?i)<br\s*/?>", "\n", text)
    text = re.sub(r"(?i)</(p|div|h1|h2|h3|h4|h5|h6|tr|li|ul|ol|table)>", "\n", text)
    text = re.sub(r"(?i)<li[^>]*>", "\n- ", text)
    text = re.sub(r"(?is)<[^>]+>", " ", text)
    text = html.unescape(text)
    text = re.sub(r"\r\n?", "\n", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _tokenize(text: str) -> list[str]:
    tokens = []
    for token in TOKEN_RE.findall(text.lower()):
        if token in STOPWORDS:
            continue
        tokens.append(token)
    return tokens


def _token_freq(text: str) -> dict[str, int]:
    out: dict[str, int] = {}
    for t in _tokenize(text):
        out[t] = out.get(t, 0) + 1
    return out


def _best_snippet(text: str, query_tokens: list[str], max_chars: int = 100000) -> str:
    if not text:
        return ""

    lower = text.lower()
    idx = -1
    for token in query_tokens:
        pos = lower.find(token.lower())
        if pos >= 0 and (idx < 0 or pos < idx):
            idx = pos

    if idx < 0:
        return _truncate(text, max_chars)[0]

    start = max(0, idx - max_chars // 3)
    end = min(len(text), start + max_chars)
    snippet = text[start:end]
    if start > 0:
        snippet = "..." + snippet
    if end < len(text):
        snippet = snippet + "..."
    return snippet


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


async def _fetch_page_with_body(page_id: str) -> dict[str, Any]:
    return await _request_json(
        "GET",
        f"/rest/api/content/{page_id}",
        params={"expand": "version,space,body.storage"},
    )


async def _fetch_children(parent_id: str, limit: int = 100) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    start = 0
    n = max(1, min(limit, 100))
    while True:
        data = await _request_json(
            "GET",
            f"/rest/api/content/{parent_id}/child/page",
            params={"start": start, "limit": n, "expand": "version,space,body.storage"},
        )
        batch = data.get("results", [])
        if not batch:
            break
        out.extend(batch)
        if len(batch) < n:
            break
        start += n
    return out


async def _fetch_descendants_with_bodies(root_page_id: str, max_pages: int) -> list[dict[str, Any]]:
    queue = [root_page_id]
    seen: set[str] = {root_page_id}
    docs: list[dict[str, Any]] = []

    while queue and len(docs) < max_pages:
        parent = queue.pop(0)
        children = await _fetch_children(parent, limit=100)
        for child in children:
            child_id = str(child.get("id") or "").strip()
            if not child_id or child_id in seen:
                continue
            seen.add(child_id)
            docs.append(child)
            queue.append(child_id)
            if len(docs) >= max_pages:
                break
    return docs


def _page_to_cached_doc(item: dict[str, Any]) -> CachedDoc:
    storage = (((item.get("body") or {}).get("storage") or {}).get("value")) or ""
    text = _clean_storage_to_text(storage)
    links = item.get("_links") or {}
    return CachedDoc(
        id=str(item.get("id") or ""),
        title=str(item.get("title") or ""),
        space=str(((item.get("space") or {}).get("key")) or ""),
        webui=str(links.get("webui") or ""),
        text=text,
        token_freq=_token_freq(f"{item.get('title') or ''}\n{text}"),
    )


def _score_doc(question_tokens: list[str], question_lower: str, doc: CachedDoc) -> float:
    score = 0.0
    title_lower = doc.title.lower()
    for token in question_tokens:
        tf = doc.token_freq.get(token, 0)
        if tf:
            score += 2.0 + min(tf, 6) * 0.6
        if token in title_lower:
            score += 2.5
    if question_lower in (doc.text.lower()[:100000]):
        score += 5.0
    return score


def _friendly_error(exc: Exception) -> str:
    if isinstance(exc, (ConfigError, ConfluenceApiError)):
        return f"Error: {exc}"
    return f"Error: Unexpected failure: {exc}"


async def _load_cache(force: bool = False) -> dict[str, Any]:
    now = time.time()
    if not force and _CACHE["docs"] and now - float(_CACHE["loaded_at"]) < _cache_ttl_seconds():
        return _CACHE

    prompt_page_id = _resolve_page_id(
        id_env="DS_QA_PROMPT_PAGE_ID",
        url_env="DS_QA_PROMPT_PAGE_URL",
        default_url="https://dt-confluence.mobis.com/spaces/GENAI/pages/133776732/프롬프트",
    )
    db_root_page_id = _resolve_page_id(
        id_env="DS_QA_DB_PAGE_ID",
        url_env="DS_QA_DB_PAGE_URL",
        default_url="https://dt-confluence.mobis.com/spaces/GENAI/pages/133776732/DB",
    )

    prompt_page = await _fetch_page_with_body(prompt_page_id)
    db_root_page = await _fetch_page_with_body(db_root_page_id)
    descendants = await _fetch_descendants_with_bodies(db_root_page_id, max_pages=_max_pages())

    docs: list[CachedDoc] = [_page_to_cached_doc(db_root_page)]
    docs.extend(_page_to_cached_doc(item) for item in descendants)

    _CACHE["loaded_at"] = now
    _CACHE["prompt_page"] = prompt_page
    _CACHE["db_root_page"] = db_root_page
    _CACHE["docs"] = docs
    return _CACHE


mcp = FastMCP(
    name="ds-qa-agent",
    instructions=(
        "DS QA Agent over Confluence pages. "
        "Reads instruction prompt from DS_QA_PROMPT_PAGE_URL/ID and uses "
        "DS_QA_DB_PAGE_URL/ID plus descendants as knowledge base. "
        "Use this MCP for data-science/DS questions and GENAI space knowledge lookup."
    ),
)


@mcp.tool()
async def health() -> str:
    """Check Confluence auth and DS QA page accessibility."""
    try:
        cache = await _load_cache(force=False)
        prompt = cache["prompt_page"] or {}
        db_root = cache["db_root_page"] or {}
        docs: list[CachedDoc] = cache["docs"] or []
        return _as_json_text(
            {
                "ok": True,
                "promptPage": {"id": prompt.get("id"), "title": prompt.get("title")},
                "dbRootPage": {"id": db_root.get("id"), "title": db_root.get("title")},
                "indexedPages": len(docs),
                "cacheTtlSeconds": _cache_ttl_seconds(),
                "loadedAtEpoch": _CACHE["loaded_at"],
            }
        )
    except Exception as exc:
        return _friendly_error(exc)


@mcp.tool()
async def refresh_index() -> str:
    """Force refresh DS QA Confluence cache."""
    try:
        cache = await _load_cache(force=True)
        prompt = cache["prompt_page"] or {}
        db_root = cache["db_root_page"] or {}
        docs: list[CachedDoc] = cache["docs"] or []
        return _as_json_text(
            {
                "ok": True,
                "message": "DS QA index refreshed.",
                "promptPage": {"id": prompt.get("id"), "title": prompt.get("title")},
                "dbRootPage": {"id": db_root.get("id"), "title": db_root.get("title")},
                "indexedPages": len(docs),
            }
        )
    except Exception as exc:
        return _friendly_error(exc)


@mcp.tool()
async def list_db_pages(limit: int = 200) -> str:
    """List indexed DB pages from the DS QA cache."""
    try:
        cache = await _load_cache(force=False)
        docs: list[CachedDoc] = cache["docs"] or []
        n = max(1, min(limit, 2000))
        rows = [
            {"id": d.id, "title": d.title, "space": d.space, "webui": d.webui}
            for d in docs[:n]
        ]
        return _as_json_text(
            {
                "count": len(rows),
                "totalIndexed": len(docs),
                "pages": rows,
            }
        )
    except Exception as exc:
        return _friendly_error(exc)


@mcp.tool()
async def ask_ds_qa(
    question: str,
    top_k: int = 6,
    include_prompt: bool = True,
    max_prompt_chars: int = 100000,
    max_ref_chars: int = 100000,
) -> str:
    """
    Answer a DS QA question using Confluence prompt + DB tree references.

    Use this for data-science team questions (DS process, prompt guide, DB docs,
    GENAI space knowledge, internal procedure lookup).

    Returns structured JSON containing the prompt, ranked references, and an answer draft.
    """
    try:
        q = question.strip()
        if not q:
            return "Error: question is required."

        cache = await _load_cache(force=False)
        prompt_page = cache["prompt_page"] or {}
        docs: list[CachedDoc] = cache["docs"] or []
        if not docs:
            return "Error: No DB pages indexed."

        q_tokens = _tokenize(q)
        q_lower = q.lower()
        scored: list[tuple[float, CachedDoc]] = []
        for doc in docs:
            score = _score_doc(q_tokens, q_lower, doc)
            if score > 0:
                scored.append((score, doc))
        scored.sort(key=lambda x: x[0], reverse=True)

        k = max(1, min(top_k, 20))
        selected = scored[:k] if scored else []
        refs = []
        for score, doc in selected:
            refs.append(
                {
                    "id": doc.id,
                    "title": doc.title,
                    "space": doc.space,
                    "webui": doc.webui,
                    "score": round(score, 3),
                    "snippet": _best_snippet(doc.text, q_tokens, max_chars=max_ref_chars),
                }
            )

        prompt_storage = (((prompt_page.get("body") or {}).get("storage") or {}).get("value")) or ""
        prompt_text = _clean_storage_to_text(prompt_storage)
        prompt_text = _truncate(prompt_text, max(500, max_prompt_chars))[0]

        if refs:
            lines = ["질문과 가장 관련된 Confluence 근거는 아래와 같습니다."]
            for i, ref in enumerate(refs, start=1):
                lines.append(f"{i}. [{ref['title']}] {ref['snippet']}")
            lines.append(
                "위 근거를 기반으로, 필요한 경우 정책/절차/제약사항을 먼저 요약하고 답변을 작성하세요."
            )
            answer_draft = "\n".join(lines)
        else:
            answer_draft = (
                "관련 문서를 찾지 못했습니다. DB 루트/하위 페이지 내용이 최신인지 먼저 확인하세요."
            )

        out: dict[str, Any] = {
            "question": q,
            "referencesCount": len(refs),
            "references": refs,
            "answerDraft": answer_draft,
        }
        if include_prompt:
            out["promptInstruction"] = {
                "id": prompt_page.get("id"),
                "title": prompt_page.get("title"),
                "text": prompt_text,
            }
        return _as_json_text(out)
    except Exception as exc:
        return _friendly_error(exc)


@mcp.tool()
async def ask_data_science_qa(
    question: str,
    top_k: int = 6,
) -> str:
    """
    Preferred DS query entry point.

    Trigger this when the user asks about Data Science team docs, GENAI wiki,
    prompt standards, DB hierarchy, or internal guidance stored in Confluence.
    """
    return await ask_ds_qa(question=question, top_k=top_k, include_prompt=True)


if __name__ == "__main__":
    mcp.run("stdio")
