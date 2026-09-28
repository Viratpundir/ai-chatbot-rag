"""FastAPI client and response helpers for the Streamlit frontend."""

import base64
import json
import os
from urllib.parse import urlsplit

import requests
import streamlit as st

API_BASE_URL = os.getenv("API_BASE_URL", "").rstrip("/")
REQUEST_TIMEOUT = 30


def api_call(method: str, path: str, **kwargs):
    """Low-level request wrapper. Returns the Response, or None if unreachable."""
    api_base = API_BASE_URL
    if not api_base:
        try:
            request_headers = st.context.headers
            request_host = urlsplit(f"//{request_headers.get('Host', '')}").hostname
            scheme = request_headers.get("X-Forwarded-Proto", "http").split(",")[0].strip()
            if request_host:
                formatted_host = f"[{request_host}]" if ":" in request_host else request_host
                api_base = f"{scheme}://{formatted_host}:8000"
        except Exception:
            api_base = ""
    if not api_base:
        return None
    headers = {"Accept": "application/json"}
    if st.session_state.token:
        headers["Authorization"] = f"Bearer {st.session_state.token}"
    try:
        return requests.request(method, f"{api_base}{path}", headers=headers, timeout=REQUEST_TIMEOUT, **kwargs)
    except requests.RequestException:
        return None


def api_error(response, default: str) -> str:
    try:
        body = response.json()
        if body.get("detail"):
            return str(body["detail"])
        error = body.get("error")
        if isinstance(error, dict) and error.get("message"):
            return str(error["message"])
        if isinstance(error, str):
            return error
        return default
    except Exception:
        return default


def backend_is_online() -> bool:
    response = api_call("get", "/api/v1/health")
    return response is not None and response.status_code == 200


def decode_jwt(token: str) -> dict:
    try:
        payload = token.split(".")[1]
        return json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
    except Exception:
        return {}


def start_session(auth_response: dict) -> None:
    """Store the token and build a full user profile from whatever the API gave us."""
    st.session_state.token = auth_response.get("access_token") or auth_response.get("token")
    st.session_state.refresh_token = auth_response.get("refresh_token")
    user = dict(auth_response.get("user") or auth_response.get("data") or {})

    if not (user.get("name") or user.get("full_name")):
        response = api_call("get", "/api/v1/auth/me")
        if response is not None and response.status_code == 200:
            try:
                user.update(response.json())
            except Exception:
                pass

    claims = decode_jwt(st.session_state.token or "")
    subject = str(claims.get("sub", ""))
    user["email"] = user.get("email") or claims.get("email") or (subject if "@" in subject else "")
    user["role"] = user.get("role") or claims.get("role") or "EMPLOYEE"
    user["name"] = (
        user.get("name") or user.get("full_name") or claims.get("name")
        or (user["email"].split("@")[0].replace(".", " ").title() if user["email"] else "User")
    )
    st.session_state.user = user


def try_auth(path: str, payload: dict, fail_message: str):
    """POST an auth request; show an error and return None on failure."""
    response = api_call("post", path, json=payload)
    if response is None:
        st.error("Authentication service is offline. Start the FastAPI backend and retry.")
        return None
    if response.status_code not in (200, 201):
        st.error(api_error(response, fail_message))
        return None
    return response


def fetch_documents() -> list:
    documents = []
    page = 1
    while True:
        response = api_call("get", "/api/v1/documents", params={"page": page, "page_size": 100})
        if response is None or response.status_code != 200:
            return documents
        try:
            data = response.json()
            if isinstance(data, list):
                return data
            page_items = data.get("documents", data.get("data", []))
            documents.extend(page_items)
            if len(documents) >= int(data.get("total", len(documents))) or not page_items:
                return documents
            page += 1
        except (ValueError, AttributeError, TypeError):
            return documents


def ask_ai(question: str, document_ids: list, conversation_id: str | None = None):
    payload = {"question": question, "document_ids": document_ids}
    if conversation_id is not None:
        payload["conversation_id"] = conversation_id
    response = api_call("post", "/api/v1/chat/ask", json=payload)
    if response is None:
        return None
    if response.status_code != 200:
        return {"error": api_error(response, "Unable to process the question.")}
    return response.json()


def ask_guide(message: str, document_ids: list):
    response = api_call("post", "/api/v1/chat/agent", json={
        "message": message,
        "document_ids": document_ids,
        "all_authorized": False,
    })
    if response is None:
        return {"error": "AI Guide could not connect to the backend."}
    if response.status_code != 200:
        return {"error": api_error(response, "Unable to generate guidance.")}
    return response.json()


def fetch_chat_stats():
    response = api_call("get", "/api/v1/chat/stats")
    if response is None or response.status_code != 200:
        return None
    try:
        return response.json()
    except ValueError:
        return None


def fetch_history() -> list:
    conversations = []
    page = 1
    while True:
        response = api_call("get", "/api/v1/chat/conversations", params={"page": page, "page_size": 100})
        if response is None or response.status_code != 200:
            return conversations
        try:
            data = response.json()
            page_items = data.get("conversations", [])
            conversations.extend(page_items)
            if len(conversations) >= int(data.get("total", len(conversations))) or not page_items:
                break
            page += 1
        except (ValueError, AttributeError, TypeError):
            return conversations
    records = []
    for conversation in conversations:
        conversation_id = conversation.get("conversation_id")
        if not conversation_id:
            continue
        detail = api_call("get", f"/api/v1/chat/conversations/{conversation_id}")
        if detail is not None and detail.status_code == 200:
            records.append(detail.json())
    return records


def doc_id(document: dict):
    return document.get("id") or document.get("document_id")


def doc_status(document: dict) -> str:
    return str(document.get("status", "UNKNOWN")).upper()


def answer_text(result: dict) -> str:
    return result.get("answer") or result.get("response") or result.get("message") or "No answer returned."
