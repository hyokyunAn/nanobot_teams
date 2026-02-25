"""Simple Streamlit chat UI for nanobot relay (/internal/inbound)."""

from __future__ import annotations

import os
from uuid import uuid4

import httpx
import streamlit as st


DEFAULT_INBOUND_URL = os.environ.get(
    "NANOBOT_INBOUND_URL",
    "http://127.0.0.1:18800/internal/inbound",
)
DEFAULT_INTERNAL_TOKEN = os.environ.get("INTERNAL_TOKEN", "")
DEFAULT_TIMEOUT_SEC = 120.0


def _new_chat_id() -> str:
    return f"web-{uuid4().hex[:12]}"


def _send_message(
    *,
    inbound_url: str,
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


def main() -> None:
    st.set_page_config(page_title="nanobot web chat", page_icon=":speech_balloon:", layout="centered")
    st.title("nanobot Web Chat")
    st.caption("Teams relay replacement for quick local/server testing")

    if "messages" not in st.session_state:
        st.session_state.messages = []
    if "chat_id" not in st.session_state:
        st.session_state.chat_id = _new_chat_id()

    with st.sidebar:
        st.subheader("Connection")
        inbound_url = st.text_input("Inbound URL", value=DEFAULT_INBOUND_URL)
        internal_token = st.text_input("Internal Token", value=DEFAULT_INTERNAL_TOKEN, type="password")
        timeout_sec = st.number_input("Timeout (sec)", min_value=5.0, max_value=600.0, value=DEFAULT_TIMEOUT_SEC, step=5.0)
        sender_id = st.text_input("Sender ID", value="streamlit-user")
        chat_id = st.text_input("Chat ID", value=st.session_state.chat_id)

        if st.button("New Chat ID"):
            st.session_state.chat_id = _new_chat_id()
            st.rerun()
        if st.button("Clear Messages"):
            st.session_state.messages = []
            st.rerun()

    st.session_state.chat_id = chat_id.strip() or st.session_state.chat_id

    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    prompt = st.chat_input("Ask nanobot...")
    if not prompt:
        return

    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        with st.spinner("Waiting for nanobot..."):
            try:
                status, content, request_id = _send_message(
                    inbound_url=inbound_url,
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
                return

        if status == "ok":
            reply = content or "(empty response)"
            st.markdown(reply)
            st.session_state.messages.append({"role": "assistant", "content": reply})
            return

        if status == "accepted":
            accepted_msg = (
                "Response is still processing (accepted). "
                f"request_id=`{request_id}`\n\n"
                "Increase relay `--inbound-timeout` if you want synchronous replies."
            )
            st.warning(accepted_msg)
            st.session_state.messages.append({"role": "assistant", "content": accepted_msg})
            return

        fallback = f"Unexpected status: {status} (request_id={request_id})"
        st.error(fallback)
        st.session_state.messages.append({"role": "assistant", "content": fallback})


if __name__ == "__main__":
    main()
