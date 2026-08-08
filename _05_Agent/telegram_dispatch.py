"""
_05_Agent/telegram_dispatch.py
Real Telegram dispatcher using python-telegram-bot or raw requests.
Called by AlertAgent via Open-Claw Protocol.
"""
import json, logging, os, requests
from datetime import datetime, timezone

log = logging.getLogger("TELEGRAM")

def send_alert(message: str, urgency: str = "warning") -> dict:
    token   = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")

    if not token or not chat_id:
        log.warning("TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID not set — alert logged only")
        log.info("ALERT [%s]: %s", urgency, message)
        return {"status": "logged_only", "reason": "no_credentials"}

    prefix = {"info": "ℹ️", "warning": "⚠️", "critical": "🚨"}.get(urgency, "📢")
    text   = f"{prefix} *[AURA P-GRAP]* {message}\n_{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}_"

    try:
        r = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": text, "parse_mode": "Markdown"},
            timeout=10,
        )
        r.raise_for_status()
        log.info("Telegram sent (%s): %s", urgency, message[:60])
        return {"status": "sent", "message_id": r.json().get("result", {}).get("message_id")}
    except Exception as exc:
        log.error("Telegram failed: %s", exc)
        return {"status": "error", "reason": str(exc)}
