import argparse
import asyncio

from energy_agent.core.config import get_settings
from energy_agent.core.context import ActorRole
from energy_agent.core.ids import new_id
from energy_agent.core.time import utc_now
from energy_agent.persistence.mysql import create_mysql_engine, create_session_factory
from energy_agent.users.password import hash_password, normalize_username
from energy_agent.users.repository import UserRepository


async def bootstrap_admin() -> None:
    settings = get_settings()
    username = settings.bootstrap_admin_username
    password = settings.bootstrap_admin_password
    display_name = settings.bootstrap_admin_display_name
    if not username or not password or not display_name:
        raise SystemExit(
            "BOOTSTRAP_ADMIN_USERNAME, BOOTSTRAP_ADMIN_PASSWORD and "
            "BOOTSTRAP_ADMIN_DISPLAY_NAME are required"
        )
    engine = create_mysql_engine(settings.mysql_dsn)
    try:
        users = UserRepository(create_session_factory(engine))
        if await users.active_admin_count():
            raise SystemExit("An ACTIVE admin already exists; no changes made")
        now = utc_now()
        profile = await users.create(
            {
                "user_id": new_id(),
                "username": username.strip(),
                "username_normalized": normalize_username(username),
                "display_name": display_name.strip(),
                "email": settings.bootstrap_admin_email or None,
                "role": ActorRole.ADMIN.value,
                "status": "ACTIVE",
                "password_hash": hash_password(password, username),
                "must_change_password": True,
                "token_version": 1,
                "failed_login_count": 0,
                "created_by": None,
                "created_at": now,
                "updated_at": now,
            }
        )
        print(f"Bootstrap admin created: {profile.username} ({profile.user_id})")
    finally:
        await engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["bootstrap-admin"])
    args = parser.parse_args()
    if args.command == "bootstrap-admin":
        asyncio.run(bootstrap_admin())


if __name__ == "__main__":
    main()
