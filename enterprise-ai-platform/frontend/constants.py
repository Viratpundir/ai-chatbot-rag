"""Shared navigation and Streamlit session defaults."""

PAGES = ["Dashboard", "Documents", "AI Chat", "AI Guide", "History"]
ADMIN_PAGE = "Admin Dashboard"
SESSION_DEFAULTS = {
    "token": None, "refresh_token": None, "user": None, "messages": [],
    "conversation_id": None, "otp_requested": False, "guide_result": None,
    "theme": "light", "nav": PAGES[0],
}
