"""Auth errors mapped to the API error envelope (kept separate to avoid coupling)."""

from __future__ import annotations


class AuthError(Exception):
    def __init__(self, status_code: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
