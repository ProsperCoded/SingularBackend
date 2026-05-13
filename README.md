# PrintPUF Backend

PrintPUF is an anti-counterfeiting platform that utilizes Physical Unclonable Functions (PUFs) to authenticate physical products via smartphone cameras. It leverages computer vision techniques (LBP texture extraction, SIFT keypoints) and MobileNetV2 feature extraction to create unique, unclonable digital signatures for physical QR tags.

This repository houses the business logic API layer that sits between the frontend and the core engine.

## Architecture Overview

The PrintPUF system is divided into three main components:

1. **The Core Engine**: Handles all computer vision, feature extraction, vector normalisation, AES-256 encryption, and pgvector cosine similarity queries.
2. **The Backbone (API)**: Built with FastAPI and SQLModel. It handles routing, database schemas, analytics, trust score algorithms, vendor management, and user sync via Clerk webhooks.
3. **The Interface (Frontend)**: A React.js application that provides the consumer scan flow, brand dashboard, and vendor pages.

## Features

- **Anonymous Scan Routing**: Handles scans, routes images to the core engine, computes trust scores, and returns actionable verdicts (AUTHENTIC, SUSPICIOUS, FAKE).
- **Vendor Trust Algorithm**: Computes dynamic trust scores (0-100) and assigns badge tiers (Gold, Silver, Bronze) based on the ratio of authentic scans to fake attempts. Includes 7-day trend analysis.
- **Brand Analytics**: Aggregates scan events across products to provide brands with insights into authentic rates, fake attempts, and individual vendor performance.
- **Batch Management**: Manages the generation of new PUF tag batches, interfacing with Squad for payment verification and DigitalOcean Spaces for secure PDF asset delivery.
- **Clerk Integration**: Seamlessly syncs user creation and deletion from the frontend via webhooks.

## Tech Stack

- **Framework**: FastAPI
- **ORM**: SQLModel (Async SQLAlchemy)
- **Database**: PostgreSQL with `pgvector` extension (Hosted on DigitalOcean)
- **Authentication**: Clerk (via webhooks)
- **Payments**: Squad API
- **Storage**: DigitalOcean Spaces (S3 compatible)

## Setup & Local Development

This project uses `uv`, an extremely fast Python package and project manager written in Rust.

### Prerequisites
- Python 3.10 or higher
- [uv](https://github.com/astral-sh/uv) installed (`curl -LsSf https://astral.sh/uv/install.sh | sh`)
- PostgreSQL database

### Installation & Running Locally

1. **Clone the repository:**
   ```bash
   git clone <repository-url>
   cd PrintPUF
   ```

2. **Sync the project dependencies and create the virtual environment:**
   Using `uv`, this step will automatically create the `.venv` and install the exact dependencies from `uv.lock`.
   ```bash
   uv sync
   ```

3. **Configure Environment Variables:**
   ```env
   DATABASE_URL="postgresql+asyncpg://user:pass@host/dbname?ssl=require"
   CLERK_WEBHOOK_SECRET="whsec_..."
   SQUAD_SECRET_KEY="sandbox_..."
   SQUAD_BASE_URL="https://sandbox-api-d.squadco.com"
   DO_SPACES_KEY="..."
   DO_SPACES_SECRET="..."
   DO_SPACES_ENDPOINT="..."
   DO_SPACES_BUCKET="..."
   ```

4. **Run the Development Server:**
   You can use `uv run` to execute FastAPI directly within the managed environment.
   ```bash
   uv run fastapi dev --host 127.0.0.1 --port 8000
   ```

### API Documentation

Once the server is running, the interactive Swagger API documentation is available at:
**http://127.0.0.1:8000/docs**