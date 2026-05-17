"""Notification channel interface."""

from __future__ import annotations

from abc import ABC, abstractmethod


class Notifier(ABC):
    @abstractmethod
    def send(self, title: str, body: str) -> bool:
        """Send notification. Returns True on success."""
