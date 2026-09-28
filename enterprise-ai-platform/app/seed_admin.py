"""Explicit development-only admin account creation/promotion command."""

from __future__ import annotations

import asyncio

from app.auth.password import AuthError, register_user
from app.core.config import settings
from app.core.logging import get_logger
from app.database.database import connect_db, db_session, disconnect_db
from app.database.repositories import AuditLogRepository, UserRepository

logger = get_logger(__name__)


async def seed_admin() -> str:
    if settings.APP_ENV != "development":
        raise RuntimeError("Admin seeding is allowed only when APP_ENV=development.")
    if not settings.ADMIN_EMAIL.strip():
        raise RuntimeError("Set ADMIN_EMAIL in the backend environment before seeding.")

    await connect_db()
    async with db_session() as db:
        repo = UserRepository(db)
        existing = await repo.get_by_email(settings.ADMIN_EMAIL)
        if existing is not None:
            if existing.role in {"ADMIN", "SUPER_ADMIN"}:
                if not existing.is_active:
                    raise RuntimeError("The configured admin account exists but is disabled.")
                return "Configured admin account already exists; no changes made."
            if not settings.ADMIN_PROMOTE_EXISTING:
                raise RuntimeError(
                    "The configured email belongs to a non-admin account. "
                    "Set ADMIN_PROMOTE_EXISTING=true explicitly to promote it in development."
                )
            if not existing.is_active:
                raise RuntimeError("The configured account is disabled; refusing to promote it.")
            previous_role = existing.role
            await repo.update(existing.id, role="ADMIN")
            await repo.revoke_all_sessions(existing.id)
            await AuditLogRepository(db).log(
                action="development_admin_promoted",
                user_id=existing.id,
                resource_type="user",
                resource_id=existing.id,
                metadata={"old_role": previous_role, "new_role": "ADMIN"},
            )
            return "Existing account promoted to ADMIN; sign in again to refresh the session."

        if not settings.ADMIN_PASSWORD:
            raise RuntimeError("Set ADMIN_PASSWORD in the backend environment before creating an admin.")
        try:
            user = await register_user(
                db,
                name=settings.ADMIN_NAME,
                email=settings.ADMIN_EMAIL,
                password=settings.ADMIN_PASSWORD,
                role="ADMIN",
            )
        except AuthError as exc:
            raise RuntimeError(str(exc)) from exc

        await AuditLogRepository(db).log(
            action="development_admin_created",
            user_id=user.id,
            resource_type="user",
            resource_id=user.id,
            metadata={"role": "ADMIN"},
        )
        return "Development ADMIN account created. The password was not logged."


async def main() -> None:
    try:
        message = await seed_admin()
        print(message)
    finally:
        await disconnect_db()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except RuntimeError as exc:
        raise SystemExit(str(exc)) from exc