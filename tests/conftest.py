from __future__ import annotations

import os


_DEFAULT_ENV = {
    "DATABASE_URL": "postgresql+asyncpg://user:pass@localhost/printpuf_test",
    "CLERK_WEBHOOK_SECRET": "test_webhook_secret",
    "CLERK_FRONTEND_API_URL": "https://clerk.example.test",
    "SQUAD_SECRET_KEY": "test_squad_secret",
    "SQUAD_BASE_URL": "https://squad.example.test",
    "DO_SPACES_REGION": "fra1",
    "DO_SPACES_KEY": "test_key",
    "DO_SPACES_SECRET": "test_secret",
    "DO_SPACES_BUCKET": "printpuf-test",
}

for key, value in _DEFAULT_ENV.items():
    os.environ.setdefault(key, value)

