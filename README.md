# PrintPUF Backend

PrintPUF is an anti-counterfeiting platform that utilizes Physical Unclonable Functions (PUFs) to authenticate physical products via smartphone cameras. It leverages computer vision techniques (LBP texture extraction, SIFT keypoints) and MobileNetV2 feature extraction to create unique, unclonable digital signatures for physical QR tags.

This repository houses the business logic API layer that sits between the frontend and the core engine.

## Architecture Overview

The PrintPUF system is divided into three main components:

1. **The Core Engine**: Handles all computer vision, feature extraction, vector normalisation, AES-256 encryption, and pgvector cosine similarity queries.
2. **The Backbone (API)**: Built with FastAPI and SQLModel. It handles routing, database schemas, analytics, trust score algorithms, vendor management, and user sync via Clerk webhooks.
3. **The Interface (Frontend)**: A React.js application that provides the consumer scan flow, brand dashboard, and vendor pages.

## Features

- **Anonymous Scan Routing**: Handles scans, routes images to the core engine, computes trust scores, and returns actionable verdicts (AUTHENTIC, SUSPICIOUS, FAKE). Verified scans are appended to audit logs for later review; nothing is deleted on scan.
- **Vendor Trust Algorithm**: Computes dynamic trust scores (0-100) and assigns badge tiers (Gold, Silver, Bronze) based on the ratio of authentic scans to fake attempts. Includes 7-day trend analysis.
- **Brand Analytics**: Aggregates scan events across products to provide brands with insights into authentic rates, fake attempts, and individual vendor performance.
- **Tag Lifecycle Management**: Generates, enrols, verifies, and lists individual PUF tags, with Squad-backed payment verification for tag creation.
- **Clerk Integration**: Seamlessly syncs user creation and deletion from the frontend via webhooks.

## Tech Stack

- **Framework**: FastAPI
- **ORM**: SQLModel (Async SQLAlchemy)
- **Database**: PostgreSQL with `pgvector` extension (Hosted on DigitalOcean)
- **Authentication**: Clerk (via webhooks)
- **Payments**: Squad API
- **Storage**: DigitalOcean Spaces (S3 compatible)

## Setup & Local Development

### Prerequisites

- Python 3.10 or higher
- PostgreSQL database

### Installation & Running Locally

1. **Clone the repository:**

   ```bash
   git clone <repository-url>
   cd PrintPUF
   ```

2. **Create the virtual environment and install the dependencies:**

   ```bash
   python -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```

3. **Configure Environment Variables:**

   ```env
   DATABASE_URL="postgresql://user:pass@host:5432/dbname?sslmode=require"
   CLERK_WEBHOOK_SECRET="whsec_..."
   SQUAD_SECRET_KEY="sandbox_..."
   SQUAD_BASE_URL="https://sandbox-api-d.squadco.com"
   DO_SPACES_KEY="..."
   DO_SPACES_SECRET="..."
   DO_SPACES_ENDPOINT="..."
   DO_SPACES_BUCKET="..."
   ```

   The backend automatically loads `backend/certs/ca-certificate.crt` for Postgres
   connections when `sslmode` is enabled, so you do not need to wire the CA file
   into the connection string manually.

4. **Run the Development Server:**
   ```bash
   fastapi dev --host 127.0.0.1 --port 8000
   ```

### API Documentation

Once the server is running, the interactive Swagger API documentation is available at:
**http://127.0.0.1:8000/docs**

# PrintPUF Engine

Functional engine for PrintPUF tag generation, enrolment, and verification. The engine is intentionally side-effect free: it accepts inputs, processes them, and returns structured results. Storage, APIs, and verdict logic live in the backend.

## Pipeline

The current implementation guide defines 9 stages:

1. QR generation
2. Ed25519 signing
3. Image preprocessing and alignment
4. pHash pre-filter
5. LBP texture extraction
6. SIFT keypoint extraction
7. MobileNetV2 embedding
8. Vector construction and cosine similarity
9. Single-tag orchestration

## Setup

Use the project virtual environment and install dependencies with `pip`:

```bash
source .venv/bin/activate
pip install -r requirements.txt
```

The engine reads Ed25519 key material from environment variables. The canonical names are `PRINTPUF_ED25519_PRIVATE_KEY_PEM` and `PRINTPUF_ED25519_PUBLIC_KEY_PEM`. The shorter `PRINTPUF_PRIVATE_KEY_PEM` and `PRINTPUF_PUBLIC_KEY_PEM` aliases are also accepted.

## CLI

Activate the virtualenv, then use the manual test CLI directly:

```bash
engine --help
engine generate --product-id product-123 --vendor-id vendor-abc --output artifacts/manual/tag.png
engine scan-qr --image artifacts/manual/tag.png
engine enrol \
  --image artifacts/manual/scan1.png \
  --image artifacts/manual/scan2.png \
  --image artifacts/manual/scan3.png \
  --product-id product-123 \
  --vendor-id vendor-abc \
  --output-dir artifacts/manual/enrolments/product-123
engine verify --bundle artifacts/manual/enrolments/product-123/enrolment.json --image artifacts/manual/tag.png
```

`generate` writes a QR PNG, `enrol` expects three scans by default and writes a bundle plus artifacts for that tag, `scan-qr` verifies the QR signature, and `verify` returns a graded `pass` / `suspicious` / `fail` verdict using both the grayscale fingerprint path and a lightweight color signature from the support patches.

## What this repo will contain

- `src/engine/` for the processing pipeline stages
- `tests/` for isolated stage and integration tests
- `test_images/` for the physical tag fixtures used in verification

## Notes

- `opencv-contrib-python` is required because SIFT lives in OpenCV contrib.
- `opencv-contrib-python` is also used for `WeChatQRCode` and `aruco` marker detection in the alignment stack.
- The implementation is expected to stay pure and deterministic.
- The public entry points now include `engine.pipeline.generate_qr_only()`, `engine.pipeline.enrol()`, and `engine.pipeline.extract_features()`.
- Tests seed their own env-backed Ed25519 keypair, so a private local `.env` is not required for `pytest`.
