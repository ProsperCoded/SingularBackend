from __future__ import annotations

import os
import sys
import types


def _install_lightweight_engine_stubs() -> None:
    pipeline = types.ModuleType("services.engine.pipeline")
    pipeline.DEFAULT_ENROLMENT_SCAN_COUNT = 3
    pipeline.GenerateResult = object
    pipeline.EnrolResult = object
    pipeline.ImageSource = object
    pipeline.generate_qr_only = lambda *args, **kwargs: None
    pipeline.enrol = lambda *args, **kwargs: None

    bundle = types.ModuleType("services.engine.bundle")
    bundle.serialize_enrolment_bundle = lambda enrolment_result, vendor_id=None: {
        "product_id": getattr(enrolment_result, "product_id", None),
        "vendor_id": vendor_id,
    }
    bundle.map_engine_verdict_to_backend = lambda verdict: verdict
    bundle.verify_enrolment_bundle = lambda *args, **kwargs: None

    sys.modules["services.engine.pipeline"] = pipeline
    sys.modules["services.engine.bundle"] = bundle


if os.environ.get("PRINTPUF_TEST_LIGHTWEIGHT_ENGINE") == "1":
    _install_lightweight_engine_stubs()


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
    os.environ[key] = value
