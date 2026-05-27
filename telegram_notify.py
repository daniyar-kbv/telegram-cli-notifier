#!/usr/bin/env python3
"""Send Telegram notifications from local scripts.

Secrets are read from environment variables or a small .env-style config file:

- TELEGRAM_BOT_TOKEN
- TELEGRAM_CHAT_ID
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Iterable


SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_USER_CONFIG = Path.home() / ".config" / "telegram-cli-notifier" / ".env"
DEFAULT_LOCAL_CONFIG = SCRIPT_DIR / ".env"
MAX_TELEGRAM_MESSAGE_LENGTH = 4096


class TelegramConfigError(RuntimeError):
    """Raised when required Telegram config is missing."""


class TelegramRequestError(RuntimeError):
    """Raised when Telegram API returns an error."""


def strip_wrapping_quotes(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def load_env_file(path: Path) -> None:
    if not path.exists():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = strip_wrapping_quotes(value)
        if key and key not in os.environ:
            os.environ[key] = value


def config_paths(explicit_path: str | None) -> Iterable[Path]:
    if explicit_path:
        yield Path(explicit_path).expanduser()
        return

    env_path = os.getenv("TELEGRAM_CLI_NOTIFIER_CONFIG")
    if env_path:
        yield Path(env_path).expanduser()

    yield DEFAULT_USER_CONFIG
    yield DEFAULT_LOCAL_CONFIG


def load_config(explicit_path: str | None) -> None:
    for path in config_paths(explicit_path):
        load_env_file(path)


def read_message(args: argparse.Namespace) -> str:
    if args.message:
        return args.message

    if args.stdin:
        text = sys.stdin.read().strip()
        if text:
            return text

    raise TelegramConfigError("Provide --message or pipe text with --stdin.")


def require_token(args: argparse.Namespace) -> str:
    token = args.token or os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        raise TelegramConfigError("Missing TELEGRAM_BOT_TOKEN.")
    return token


def require_chat_id(args: argparse.Namespace) -> str:
    chat_id = args.chat_id or os.getenv("TELEGRAM_CHAT_ID")
    if not chat_id:
        raise TelegramConfigError("Missing TELEGRAM_CHAT_ID.")
    return chat_id


def telegram_request(token: str, method: str, payload: dict[str, object], timeout: float) -> dict[str, object]:
    url = f"https://api.telegram.org/bot{token}/{method}"
    data = urllib.parse.urlencode(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise TelegramRequestError(f"Telegram HTTP {exc.code}: {body}") from exc
    except urllib.error.URLError as exc:
        raise TelegramRequestError(f"Telegram request failed: {exc.reason}") from exc

    try:
        decoded = json.loads(body)
    except json.JSONDecodeError as exc:
        raise TelegramRequestError(f"Telegram returned non-JSON response: {body}") from exc

    if not decoded.get("ok"):
        raise TelegramRequestError(f"Telegram API error: {body}")

    return decoded


def truncate_message(text: str) -> str:
    if len(text) <= MAX_TELEGRAM_MESSAGE_LENGTH:
        return text

    suffix = "\n\n[truncated]"
    return text[: MAX_TELEGRAM_MESSAGE_LENGTH - len(suffix)] + suffix


def send_message(args: argparse.Namespace) -> None:
    text = truncate_message(read_message(args))

    if args.dry_run:
        print(text)
        return

    token = require_token(args)
    chat_id = require_chat_id(args)

    payload: dict[str, object] = {
        "chat_id": chat_id,
        "text": text,
        "disable_web_page_preview": "true" if args.disable_web_page_preview else "false",
    }
    if args.parse_mode:
        payload["parse_mode"] = args.parse_mode

    telegram_request(token, "sendMessage", payload, args.timeout)
    print("Telegram message sent.")


def print_updates(args: argparse.Namespace) -> None:
    token = require_token(args)
    decoded = telegram_request(token, "getUpdates", {}, args.timeout)
    result = decoded.get("result", [])

    if not result:
        print("No updates found. Send a message to the bot in Telegram, then run this again.")
        return

    seen: set[int] = set()
    for update in result:
        if not isinstance(update, dict):
            continue
        message = update.get("message") or update.get("channel_post")
        if not isinstance(message, dict):
            continue
        chat = message.get("chat")
        if not isinstance(chat, dict):
            continue
        chat_id = chat.get("id")
        if not isinstance(chat_id, int) or chat_id in seen:
            continue

        seen.add(chat_id)
        label = chat.get("title") or chat.get("username") or chat.get("first_name") or "unknown"
        chat_type = chat.get("type", "unknown")
        print(f"{chat_id}\t{chat_type}\t{label}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Send a Telegram notification.")
    parser.add_argument("--message", help="Message text to send.")
    parser.add_argument("--stdin", action="store_true", help="Read message text from stdin.")
    parser.add_argument("--get-updates", action="store_true", help="Print recent Telegram chat ids for this bot.")
    parser.add_argument("--env-file", help="Path to a .env-style config file.")
    parser.add_argument("--token", help="Telegram bot token. Prefer env/config for normal use.")
    parser.add_argument("--chat-id", help="Telegram chat id. Prefer env/config for normal use.")
    parser.add_argument("--parse-mode", choices=("MarkdownV2", "HTML"), help="Optional Telegram parse mode.")
    parser.add_argument("--timeout", type=float, default=15.0, help="Telegram request timeout in seconds.")
    parser.add_argument("--dry-run", action="store_true", help="Print the message without sending it.")
    parser.add_argument(
        "--disable-web-page-preview",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Disable Telegram link previews. Enabled by default.",
    )
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    try:
        load_config(args.env_file)
        if args.get_updates:
            print_updates(args)
        else:
            send_message(args)
        return 0
    except (TelegramConfigError, TelegramRequestError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
