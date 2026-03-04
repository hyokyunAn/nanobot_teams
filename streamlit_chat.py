"""Simple Streamlit chat UI for nanobot relay (/internal/inbound)."""

from __future__ import annotations

import os
import time
from urllib.parse import urlsplit, urlunsplit
from uuid import uuid4

import httpx
import streamlit as st


def _load_local_env() -> None:
    """Load simple KEY=VALUE pairs from .env (if present)."""
    env_path = os.environ.get("NANOBOT_ENV_FILE", ".env")
    if not os.path.exists(env_path):
        return
    try:
        with open(env_path, encoding="utf-8") as f:
            for raw in f:
                line = raw.strip()
                if not line or line.startswith("#"):
                    continue
                if line.startswith("export "):
                    line = line[len("export "):].strip()
                if "=" not in line:
                    continue
                key, value = line.split("=", 1)
                key = key.strip()
                value = value.strip().strip("'").strip('"')
                if key and key not in os.environ:
                    os.environ[key] = value
    except Exception:
        # Fall back to process env only.
        return


_load_local_env()


DEFAULT_INBOUND_URL = os.environ.get(
    "NANOBOT_INBOUND_URL", ""
)
DEFAULT_INBOUND_HOST = os.environ.get("NANOBOT_INBOUND_HOST", "")
DEFAULT_INTERNAL_TOKEN = os.environ.get("INTERNAL_TOKEN", "")
DEFAULT_TIMEOUT_SEC = 120.0
DEFAULT_POLL_INTERVAL_SEC = 5


def _new_chat_id() -> str:
    return f"web-{uuid4().hex[:12]}"


def _poll_url_from_inbound(inbound_url: str) -> str:
    parsed = urlsplit(inbound_url)
    path = parsed.path or ""
    if path.endswith("/internal/inbound"):
        path = path[: -len("/internal/inbound")] + "/internal/web/poll"
    elif path.endswith("/"):
        path = path + "internal/web/poll"
    else:
        path = path + "/internal/web/poll"
    return urlunsplit((parsed.scheme, parsed.netloc, path, "", ""))


def _send_message(
    *,
    inbound_url: str,
    inbound_host: str,
    internal_token: str,
    timeout_sec: float,
    chat_id: str,
    sender_id: str,
    content: str,
) -> tuple[str, str, str]:
    """Return (status, content, request_id)."""
    request_id = f"req_{uuid4().hex}"
    payload = {
        "request_id": request_id,
        "chat_id": chat_id,
        "sender_id": sender_id,
        "content": content,
        "metadata": {"channel": "web"},
    }

    headers = {"content-type": "application/json"}
    if inbound_host:
        headers["host"] = inbound_host
        headers["x-forwarded-host"] = inbound_host
    if internal_token:
        headers["x-internal-token"] = internal_token

    with httpx.Client(timeout=timeout_sec) as client:
        resp = client.post(inbound_url, json=payload, headers=headers)
        resp.raise_for_status()
        data = resp.json()

    return (
        str(data.get("status", "ok")),
        str(data.get("content", "")),
        str(data.get("request_id", request_id)),
    )


def _poll_messages(
    *,
    inbound_url: str,
    inbound_host: str,
    internal_token: str,
    timeout_sec: float,
    chat_id: str,
    limit: int = 20,
) -> list[dict]:
    poll_url = _poll_url_from_inbound(inbound_url)
    headers: dict[str, str] = {}
    if inbound_host:
        headers["host"] = inbound_host
        headers["x-forwarded-host"] = inbound_host
    if internal_token:
        headers["x-internal-token"] = internal_token
    with httpx.Client(timeout=timeout_sec) as client:
        resp = client.get(poll_url, params={"chat_id": chat_id, "limit": limit}, headers=headers)
        resp.raise_for_status()
        data = resp.json()
    return data.get("messages", []) if isinstance(data, dict) else []


def main() -> None:
    st.set_page_config(page_title="nanobot web chat", page_icon=":speech_balloon:", layout="centered")
    st.title("nanobot Web Chat")
    st.caption("Teams relay replacement for quick local/server testing")

    if "messages" not in st.session_state:
        st.session_state.messages = []
    if "chat_id" not in st.session_state:
        st.session_state.chat_id = _new_chat_id()
    if "seen_web_message_ids" not in st.session_state:
        st.session_state.seen_web_message_ids = set()

    with st.sidebar:
        st.subheader("Connection")
        inbound_url = st.text_input("Inbound URL", value=DEFAULT_INBOUND_URL)
        inbound_host = st.text_input("Inbound Host Header", value=DEFAULT_INBOUND_HOST)
        internal_token = st.text_input("Internal Token", value=DEFAULT_INTERNAL_TOKEN, type="password")
        timeout_sec = st.number_input("Timeout (sec)", min_value=5.0, max_value=600.0, value=DEFAULT_TIMEOUT_SEC, step=5.0)
        auto_poll = st.checkbox("Auto Poll", value=True)
        poll_interval_sec = st.number_input(
            "Poll interval (sec)",
            min_value=2,
            max_value=60,
            value=DEFAULT_POLL_INTERVAL_SEC,
            step=1,
            disabled=not auto_poll,
        )
        poll_clicked = st.button("Fetch New Messages")
        sender_id = st.text_input("Sender ID", value="streamlit-user")
        chat_id = st.text_input("Chat ID", value=st.session_state.chat_id)

        if st.button("New Chat ID"):
            st.session_state.chat_id = _new_chat_id()
            st.rerun()
        if st.button("Clear Messages"):
            st.session_state.messages = []
            st.rerun()

    st.session_state.chat_id = chat_id.strip() or st.session_state.chat_id

    def _consume_polled_messages() -> int:
        try:
            polled = _poll_messages(
                inbound_url=inbound_url,
                inbound_host=inbound_host.strip(),
                internal_token=internal_token,
                timeout_sec=float(timeout_sec),
                chat_id=st.session_state.chat_id,
                limit=50,
            )
        except Exception:
            return 0

        new_count = 0
        for item in polled:
            msg_id = str(item.get("id", "")).strip() or f"webmsg_{uuid4().hex}"
            if msg_id in st.session_state.seen_web_message_ids:
                continue
            st.session_state.seen_web_message_ids.add(msg_id)
            content = str(item.get("content", "")).strip()
            if not content:
                continue
            st.session_state.messages.append({"role": "assistant", "content": content})
            new_count += 1
        return new_count

    if poll_clicked:
        new_count = _consume_polled_messages()
        if new_count:
            st.sidebar.success(f"{new_count} new message(s)")
        else:
            st.sidebar.info("No new messages")
    elif auto_poll:
        _consume_polled_messages()

    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    prompt = st.chat_input("Ask nanobot...")
    if prompt:
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        with st.chat_message("assistant"):
            with st.spinner("Waiting for nanobot..."):
                try:
                    status, content, request_id = _send_message(
                        inbound_url=inbound_url,
                        inbound_host=inbound_host.strip(),
                        internal_token=internal_token,
                        timeout_sec=float(timeout_sec),
                        chat_id=st.session_state.chat_id,
                        sender_id=sender_id.strip() or "streamlit-user",
                        content=prompt,
                    )
                except Exception as e:
                    error_msg = f"Request failed: {e}"
                    st.error(error_msg)
                    st.session_state.messages.append({"role": "assistant", "content": error_msg})
                    status = "error"
                    request_id = ""
                    content = ""

            if status == "ok":
                reply = content or "(empty response)"
                st.markdown(reply)
                st.session_state.messages.append({"role": "assistant", "content": reply})
            elif status == "accepted":
                accepted_msg = (
                    "Response is still processing (accepted). "
                    f"request_id=`{request_id}`\n\n"
                    "Web polling will fetch it when ready."
                )
                st.warning(accepted_msg)
                st.session_state.messages.append({"role": "assistant", "content": accepted_msg})
            elif status != "error":
                fallback = f"Unexpected status: {status} (request_id={request_id})"
                st.error(fallback)
                st.session_state.messages.append({"role": "assistant", "content": fallback})

    if auto_poll:
        time.sleep(float(poll_interval_sec))
        st.rerun()


if __name__ == "__main__":
    main()
