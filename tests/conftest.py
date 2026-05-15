from __future__ import annotations

import os


_DEFAULT_ENV = {
    "DATABASE_URL": "sqlite+aiosqlite:///./test_printpuf.db",
    "JWT_SECRET_KEY": "test_jwt_secret",
    "SQUAD_SECRET_KEY": "test_squad_secret",
    "SQUAD_BASE_URL": "https://squad.example.test",
    "DO_SPACES_REGION": "fra1",
    "DO_SPACES_KEY": "test_key",
    "DO_SPACES_SECRET": "test_secret",
    "DO_SPACES_BUCKET": "printpuf-test",
}

for key, value in _DEFAULT_ENV.items():
    os.environ.setdefault(key, value)
