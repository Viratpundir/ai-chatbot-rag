"""
app/api/v1/conversations.py
----------------------------
Dedicated conversation endpoints (mirrors chat.py conversation routes
but under /conversations/ prefix for REST clarity).

Stage 11: Full implementation.
"""

from fastapi import APIRouter

# Re-export conversation sub-router from chat.py for cleaner main.py wiring.
# Stage 11 will split these into their own DB-backed implementations.
router = APIRouter(prefix="/conversations", tags=["Conversations"])
