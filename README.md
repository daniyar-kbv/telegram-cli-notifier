# Telegram CLI Notifier

Small Telegram notification helper for local scripts and automations.

It is intentionally narrow:

- It sends Telegram messages through the official Bot API.
- It can read message text from a command-line argument or stdin.
- It keeps bot secrets out of Git.

## Setup

1. In Telegram, message `@BotFather`.
2. Create a bot with `/newbot`.
3. Copy the bot token.
4. Send any message to the new bot from the Telegram account that should receive alerts.
5. Copy `.env.example` to `.env` and fill in `TELEGRAM_BOT_TOKEN`.
6. Run the updates command to find your chat id:

```bash
python3 telegram_notify.py --get-updates
```

7. Add the printed chat id to `.env` as `TELEGRAM_CHAT_ID`.
8. Send a test notification:

```bash
python3 telegram_notify.py --message "Telegram alert test"
```

## Preferred Secret Location

For automation, prefer storing secrets outside this repo:

```bash
mkdir -p ~/.config/telegram-cli-notifier
cp .env.example ~/.config/telegram-cli-notifier/.env
```

Then edit `~/.config/telegram-cli-notifier/.env`.

The script loads config in this order:

1. `--env-file <path>`
2. `TELEGRAM_CLI_NOTIFIER_CONFIG`
3. `~/.config/telegram-cli-notifier/.env`
4. local repo `.env`

## Pipe Usage

Any local script can pipe text into Telegram:

```bash
printf '%s\n' 'Alert message ...' | python3 telegram_notify.py --stdin
```

Use Telegram only as an alert channel. Keep secrets in environment variables or ignored config files.
