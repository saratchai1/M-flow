from __future__ import annotations

import logging
from dataclasses import dataclass

import requests

from .config import Settings

log = logging.getLogger(__name__)


class Notifier:
    name = "notifier"
    def send(self, message: str) -> None:
        raise NotImplementedError


@dataclass
class LineNotifier(Notifier):
    token: str
    recipient: str
    name = "line"
    def send(self, message: str) -> None:
        response = requests.post(
            "https://api.line.me/v2/bot/message/push",
            headers={"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"},
            json={"to": self.recipient, "messages": [{"type": "text", "text": message[:5000]}]},
            timeout=15,
        )
        response.raise_for_status()


@dataclass
class TelegramNotifier(Notifier):
    token: str
    chat_id: str
    name = "telegram"
    def send(self, message: str) -> None:
        response = requests.post(
            f"https://api.telegram.org/bot{self.token}/sendMessage",
            json={"chat_id": self.chat_id, "text": message, "disable_web_page_preview": False},
            timeout=15,
        )
        response.raise_for_status()


@dataclass
class SlackNotifier(Notifier):
    webhook_url: str
    name = "slack"
    def send(self, message: str) -> None:
        response = requests.post(self.webhook_url, json={"text": message}, timeout=15)
        response.raise_for_status()


class MultiNotifier:
    def __init__(self, notifiers: list[Notifier]):
        self.notifiers = notifiers

    @property
    def enabled(self) -> bool:
        return bool(self.notifiers)

    def send(self, message: str) -> list[str]:
        if not self.notifiers:
            return ["no notification channel configured"]
        errors: list[str] = []
        for notifier in self.notifiers:
            try:
                notifier.send(message)
            except Exception as exc:
                error = f"{notifier.name}: {type(exc).__name__}: {exc}"
                log.exception("Notification failed via %s", notifier.name)
                errors.append(error)
        return errors


def build_notifier(settings: Settings) -> MultiNotifier:
    notifiers: list[Notifier] = []
    if settings.line_channel_access_token and settings.line_to:
        notifiers.append(LineNotifier(settings.line_channel_access_token, settings.line_to))
    if settings.telegram_bot_token and settings.telegram_chat_id:
        notifiers.append(TelegramNotifier(settings.telegram_bot_token, settings.telegram_chat_id))
    if settings.slack_webhook_url:
        notifiers.append(SlackNotifier(settings.slack_webhook_url))
    return MultiNotifier(notifiers)
