"""
Interactive one-time Telegram session setup.
Creates a session file that main.py uses for auth on subsequent runs.

Run with an interactive terminal:
    docker compose run --rm -it telegram-ingester python setup_session.py

The session file is saved to TELEGRAM_SESSION_PATH (default: /app/sessions/osint_monitor)
and persisted in the telegram_sessions Docker volume.
"""

import asyncio

from telethon import TelegramClient

from config import settings


async def setup() -> None:
    print(f"Creating Telegram session at: {settings.telegram_session_path}")
    print("You will be prompted for your phone number and the verification code.\n")

    client = TelegramClient(
        settings.telegram_session_path,
        settings.telegram_api_id,
        settings.telegram_api_hash,
    )

    await client.start()
    me = await client.get_me()
    print(f"\nAuthenticated as: {me.first_name} (@{me.username})")
    print("Session saved. You can now run the ingester normally.")
    await client.disconnect()


if __name__ == "__main__":
    asyncio.run(setup())
