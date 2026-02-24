#!/usr/bin/env python3
"""YouTube transcript + summary MCP server."""

from __future__ import annotations

import html
import json
import math
import os
import re
from collections import Counter
from dataclasses import dataclass
from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

import httpx
from mcp.server.fastmcp import FastMCP


DEFAULT_TIMEOUT_SECONDS = 25.0
MAX_ERROR_BODY_CHARS = 1000
VIDEO_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")
TOKEN_RE = re.compile(r"[A-Za-z0-9가-힣']+")

STOPWORDS = {
    "the", "a", "an", "and", "or", "to", "in", "on", "for", "with", "of", "is", "are",
    "was", "were", "be", "been", "this", "that", "it", "as", "at", "by", "from", "we",
    "you", "your", "our", "they", "their", "he", "she", "i", "me", "my", "mine",
    "은", "는", "이", "가", "을", "를", "에", "에서", "의", "와", "과", "그리고", "또는",
    "하다", "합니다", "있다", "입니다", "그", "저", "것", "수", "등", "더", "좀",
}


class YouTubeError(RuntimeError):
    """Raised when YouTube data fetch/parsing fails."""


@dataclass
class TranscriptTrack:
    base_url: str
    language_code: str
    language_name: str
    is_auto: bool


@dataclass
class TranscriptData:
    video_id: str
    title: str
    channel: str
    duration_seconds: int
    track: TranscriptTrack
    segments: list[dict[str, Any]]


def _timeout_seconds() -> float:
    raw = (os.getenv("YOUTUBE_MCP_TIMEOUT_SECONDS") or "").strip()
    if not raw:
        return DEFAULT_TIMEOUT_SECONDS
    try:
        return max(1.0, float(raw))
    except ValueError:
        return DEFAULT_TIMEOUT_SECONDS


def _user_agent() -> str:
    custom = (os.getenv("YOUTUBE_MCP_USER_AGENT") or "").strip()
    if custom:
        return custom
    return (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    )


def _truncate(text: str, max_chars: int) -> tuple[str, bool]:
    if len(text) <= max_chars:
        return text, False
    return text[:max_chars], True


def _extract_video_id(video: str) -> str:
    value = video.strip()
    if not value:
        raise YouTubeError("video parameter is empty.")

    if VIDEO_ID_RE.fullmatch(value):
        return value

    parsed = urlparse(value)
    host = parsed.netloc.lower()
    path = parsed.path.strip("/")
    query = parse_qs(parsed.query)

    if host in {"youtu.be", "www.youtu.be"} and path:
        candidate = path.split("/", 1)[0]
        if VIDEO_ID_RE.fullmatch(candidate):
            return candidate

    if "youtube.com" in host:
        if path == "watch":
            candidate = (query.get("v") or [""])[0]
            if VIDEO_ID_RE.fullmatch(candidate):
                return candidate
        if path.startswith("embed/"):
            candidate = path.split("/", 1)[1].split("/", 1)[0]
            if VIDEO_ID_RE.fullmatch(candidate):
                return candidate
        if path.startswith("shorts/"):
            candidate = path.split("/", 1)[1].split("/", 1)[0]
            if VIDEO_ID_RE.fullmatch(candidate):
                return candidate
        candidate = (query.get("v") or [""])[0]
        if VIDEO_ID_RE.fullmatch(candidate):
            return candidate

    raise YouTubeError("Could not parse a valid YouTube video id.")


def _extract_json_object(text: str, anchor: str) -> dict[str, Any] | None:
    anchor_idx = text.find(anchor)
    if anchor_idx < 0:
        return None

    start = text.find("{", anchor_idx)
    if start < 0:
        return None

    depth = 0
    in_string = False
    escaped = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            continue

        if ch == '"':
            in_string = True
            continue
        if ch == "{":
            depth += 1
            continue
        if ch == "}":
            depth -= 1
            if depth == 0:
                raw = text[start : i + 1]
                try:
                    return json.loads(raw)
                except json.JSONDecodeError:
                    return None
    return None


def _extract_player_response(html_text: str) -> dict[str, Any]:
    anchors = [
        "ytInitialPlayerResponse = ",
        "var ytInitialPlayerResponse = ",
        "ytInitialPlayerResponse=",
    ]
    for anchor in anchors:
        obj = _extract_json_object(html_text, anchor)
        if obj:
            return obj
    raise YouTubeError("Failed to parse YouTube player response from page HTML.")


def _pick_track(
    tracks: list[dict[str, Any]],
    preferred_language: str,
    include_auto_captions: bool,
) -> TranscriptTrack:
    if not tracks:
        raise YouTubeError("No caption tracks available for this video.")

    wanted = preferred_language.lower().strip()
    normalized = []
    for t in tracks:
        normalized.append(
            TranscriptTrack(
                base_url=t.get("baseUrl", ""),
                language_code=(t.get("languageCode") or "").lower(),
                language_name=((t.get("name") or {}).get("simpleText") or ""),
                is_auto=(t.get("kind") == "asr"),
            )
        )

    def _match(exact: bool, allow_auto: bool) -> TranscriptTrack | None:
        for t in normalized:
            if not allow_auto and t.is_auto:
                continue
            if exact:
                if t.language_code == wanted:
                    return t
            elif wanted and t.language_code.startswith(wanted.split("-", 1)[0]):
                return t
        return None

    for exact, allow_auto in [
        (True, False),
        (True, include_auto_captions),
        (False, False),
        (False, include_auto_captions),
    ]:
        candidate = _match(exact=exact, allow_auto=allow_auto)
        if candidate and candidate.base_url:
            return candidate

    for t in normalized:
        if t.base_url and (include_auto_captions or not t.is_auto):
            return t

    raise YouTubeError("No usable caption track found.")


def _json3_url(base_url: str) -> str:
    parsed = urlparse(base_url)
    query = parse_qs(parsed.query, keep_blank_values=True)
    query["fmt"] = ["json3"]
    new_query = urlencode(query, doseq=True)
    return urlunparse(
        (parsed.scheme, parsed.netloc, parsed.path, parsed.params, new_query, parsed.fragment)
    )


def _clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(text.replace("\n", " "))).strip()


def _format_timestamp(ms: int) -> str:
    sec = max(0, ms // 1000)
    h = sec // 3600
    m = (sec % 3600) // 60
    s = sec % 60
    if h > 0:
        return f"{h:02d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


def _format_duration(seconds: int) -> str:
    if seconds <= 0:
        return "00:00"
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    if h > 0:
        return f"{h:02d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


def _tokenize(text: str) -> list[str]:
    tokens = []
    for raw in TOKEN_RE.findall(text.lower()):
        if len(raw) < 2:
            continue
        if raw in STOPWORDS:
            continue
        tokens.append(raw)
    return tokens


def _segment_score(text: str, keyword_weights: Counter[str]) -> float:
    tokens = _tokenize(text)
    if not tokens:
        return 0.0
    score = sum(keyword_weights.get(t, 0) for t in tokens) / math.sqrt(len(tokens))
    return score + min(len(text) / 120.0, 1.5)


def _build_summary_points(segments: list[dict[str, Any]], max_points: int) -> list[dict[str, Any]]:
    all_tokens = []
    for seg in segments:
        all_tokens.extend(_tokenize(seg["text"]))
    keywords = Counter(all_tokens)

    scored: list[dict[str, Any]] = []
    for seg in segments:
        score = _segment_score(seg["text"], keywords)
        if score > 0:
            scored.append({**seg, "_score": score})

    if not scored:
        return segments[: max(1, min(max_points, len(segments)))]

    scored.sort(key=lambda x: x["_score"], reverse=True)

    total_ms = (segments[-1]["start_ms"] + segments[-1]["duration_ms"]) if segments else 0
    if total_ms <= 0:
        min_gap_ms = 45_000
    else:
        min_gap_ms = max(25_000, min(120_000, total_ms // max(4, max_points * 2)))

    chosen: list[dict[str, Any]] = []
    for candidate in scored:
        if any(abs(candidate["start_ms"] - c["start_ms"]) < min_gap_ms for c in chosen):
            continue
        chosen.append(candidate)
        if len(chosen) >= max_points:
            break

    if not chosen:
        chosen = scored[:max_points]
    chosen.sort(key=lambda x: x["start_ms"])
    return chosen


async def _fetch_transcript_data(
    video: str,
    language: str,
    include_auto_captions: bool,
) -> TranscriptData:
    video_id = _extract_video_id(video)
    watch_url = f"https://www.youtube.com/watch?v={video_id}"

    async with httpx.AsyncClient(timeout=_timeout_seconds(), follow_redirects=True) as client:
        watch_response = await client.get(watch_url, headers={"User-Agent": _user_agent()})
        if watch_response.status_code >= 400:
            body, truncated = _truncate(watch_response.text, MAX_ERROR_BODY_CHARS)
            suffix = " (truncated)" if truncated else ""
            raise YouTubeError(f"Failed to fetch watch page: HTTP {watch_response.status_code}: {body}{suffix}")

        player = _extract_player_response(watch_response.text)
        video_details = player.get("videoDetails") or {}
        captions = (((player.get("captions") or {}).get("playerCaptionsTracklistRenderer")) or {})
        tracks = captions.get("captionTracks") or []
        chosen = _pick_track(tracks, preferred_language=language, include_auto_captions=include_auto_captions)

        transcript_url = _json3_url(chosen.base_url)
        transcript_response = await client.get(transcript_url, headers={"User-Agent": _user_agent()})
        if transcript_response.status_code >= 400:
            body, truncated = _truncate(transcript_response.text, MAX_ERROR_BODY_CHARS)
            suffix = " (truncated)" if truncated else ""
            raise YouTubeError(
                f"Failed to fetch transcript track: HTTP {transcript_response.status_code}: {body}{suffix}"
            )

    try:
        transcript_json = transcript_response.json()
    except Exception as exc:
        raise YouTubeError(f"Transcript payload is not JSON: {exc}") from exc

    segments: list[dict[str, Any]] = []
    for event in transcript_json.get("events", []):
        segs = event.get("segs")
        if not segs:
            continue
        text = "".join((seg.get("utf8") or "") for seg in segs)
        text = _clean_text(text)
        if not text:
            continue
        start_ms = int(event.get("tStartMs") or 0)
        duration_ms = int(event.get("dDurationMs") or 0)
        if segments and segments[-1]["text"] == text and abs(start_ms - segments[-1]["start_ms"]) < 300:
            continue
        segments.append({"start_ms": start_ms, "duration_ms": duration_ms, "text": text})

    if not segments:
        raise YouTubeError("Transcript is empty or unavailable.")

    title = video_details.get("title") or ""
    channel = video_details.get("author") or ""
    try:
        duration_seconds = int(video_details.get("lengthSeconds") or 0)
    except ValueError:
        duration_seconds = 0

    return TranscriptData(
        video_id=video_id,
        title=title,
        channel=channel,
        duration_seconds=duration_seconds,
        track=chosen,
        segments=segments,
    )


def _as_json(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2)


def _as_error(exc: Exception) -> str:
    if isinstance(exc, YouTubeError):
        return f"Error: {exc}"
    return f"Error: Unexpected failure: {exc}"


mcp = FastMCP(
    name="youtube-summary",
    instructions=(
        "Summarize YouTube videos from captions. "
        "Works best when captions are available."
    ),
)


@mcp.tool()
async def health() -> str:
    """Basic health check for the MCP server."""
    return _as_json(
        {
            "ok": True,
            "service": "youtube-summary",
            "note": "Network/API checks run when transcript tools are called.",
        }
    )


@mcp.tool()
async def fetch_transcript(
    video: str,
    language: str = "en",
    include_auto_captions: bool = True,
    include_timestamps: bool = True,
    max_chars: int = 120000,
) -> str:
    """Fetch transcript for a YouTube video URL or id."""
    try:
        data = await _fetch_transcript_data(
            video=video,
            language=language,
            include_auto_captions=include_auto_captions,
        )
        lines = []
        for seg in data.segments:
            if include_timestamps:
                lines.append(f"[{_format_timestamp(seg['start_ms'])}] {seg['text']}")
            else:
                lines.append(seg["text"])
        transcript_text = "\n".join(lines)
        clipped, truncated = _truncate(transcript_text, max(500, max_chars))
        return _as_json(
            {
                "videoId": data.video_id,
                "url": f"https://www.youtube.com/watch?v={data.video_id}",
                "title": data.title,
                "channel": data.channel,
                "duration": _format_duration(data.duration_seconds),
                "language": data.track.language_code,
                "languageName": data.track.language_name,
                "autoCaption": data.track.is_auto,
                "segmentCount": len(data.segments),
                "transcriptLength": len(transcript_text),
                "transcriptTruncated": truncated,
                "transcript": clipped,
            }
        )
    except Exception as exc:
        return _as_error(exc)


@mcp.tool()
async def summarize_video(
    video: str,
    language: str = "en",
    include_auto_captions: bool = True,
    max_points: int = 8,
    include_timestamps: bool = True,
) -> str:
    """Summarize a YouTube video from its transcript."""
    try:
        n_points = max(3, min(max_points, 15))
        data = await _fetch_transcript_data(
            video=video,
            language=language,
            include_auto_captions=include_auto_captions,
        )
        points = _build_summary_points(data.segments, max_points=n_points)

        lines = [
            f"# {data.title or 'YouTube Video Summary'}",
            "",
            f"- Channel: {data.channel or '(unknown)'}",
            f"- Duration: {_format_duration(data.duration_seconds)}",
            f"- Captions: {data.track.language_code} ({'auto' if data.track.is_auto else 'manual'})",
            f"- URL: https://www.youtube.com/watch?v={data.video_id}",
            "",
            "## Key Points",
        ]
        for point in points:
            prefix = f"[{_format_timestamp(point['start_ms'])}] " if include_timestamps else ""
            lines.append(f"- {prefix}{point['text']}")

        return "\n".join(lines)
    except Exception as exc:
        return _as_error(exc)


if __name__ == "__main__":
    mcp.run("stdio")
