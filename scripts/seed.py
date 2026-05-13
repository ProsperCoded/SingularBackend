"""
Demo seed script for PrintPUF.
Populates the database with realistic data for demo day.

Usage: uv run python scripts/seed.py
"""

import asyncio
import uuid
import random
from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

from core.config import settings
from models.user import User, UserRole
from models.batch import Batch
from models.product import Product
from models.scan_event import ScanEvent

# SEED DATA
BRAND_USER = User(
    id="brand_demo_001",
    email="brand@printpuf-demo.com",
    role=UserRole.BRAND,
)

VENDOR_USERS = [
    User(
        id="vendor_demo_001",
        email="vendor1@printpuf-demo.com",
        role=UserRole.VENDOR,
        vendor_id="swift-mango-lagos",
    ),
    User(
        id="vendor_demo_002",
        email="vendor2@printpuf-demo.com",
        role=UserRole.VENDOR,
        vendor_id="bold-eagle-abuja",
    ),
]

BATCHES = [
    Batch(
        id="batch_demo_001",
        brand_id=BRAND_USER.id,
        vendor_id="swift-mango-lagos",
        product_type="Sneakers",
        quantity=5,
        transaction_ref="SQUAD-DEMO-TXN-001",
        download_urls=["https://spaces.example.com/demo/batch_001.pdf"],
    ),
    Batch(
        id="batch_demo_002",
        brand_id=BRAND_USER.id,
        vendor_id="bold-eagle-abuja",
        product_type="Handbags",
        quantity=5,
        transaction_ref="SQUAD-DEMO-TXN-002",
        download_urls=["https://spaces.example.com/demo/batch_002.pdf"],
    ),
]


def _generate_products() -> list[Product]:
    """Generate 5 products per batch (10 total)."""
    products = []
    for batch in BATCHES:
        for i in range(batch.quantity):
            products.append(
                Product(
                    id=f"{batch.id}-product-{i+1:03d}",
                    batch_id=batch.id,
                    product_type=batch.product_type,
                    vendor_id=batch.vendor_id,
                    brand_id=batch.brand_id,
                )
            )
    return products


def _generate_scan_events(products: list[Product]) -> list[ScanEvent]:
    """
    Generate 30 scan events with a realistic mix:
    - Vendor 1 (swift-mango-lagos): mostly AUTHENTIC → Gold badge (>90%)
    - Vendor 2 (bold-eagle-abuja): moderate mix → Silver badge (~75%)
    """
    events = []
    now = datetime.utcnow()

    # Vendor 1 products: 14 AUTHENTIC, 1 FAKE = 93.3% → Gold
    vendor1_products = [p for p in products if p.vendor_id == "swift-mango-lagos"]
    vendor1_verdicts = (["AUTHENTIC"] * 14) + (["FAKE"] * 1)
    random.shuffle(vendor1_verdicts)

    for i, verdict in enumerate(vendor1_verdicts):
        product = random.choice(vendor1_products)
        score = random.uniform(0.92, 0.99) if verdict == "AUTHENTIC" else random.uniform(0.30, 0.60)
        events.append(
            ScanEvent(
                id=uuid.uuid4().hex,
                product_id=product.id,
                vendor_id=product.vendor_id,
                verdict=verdict,
                score=round(score, 4),
                device_hash=f"device-{random.randint(1000, 9999)}",
                scanned_at=now - timedelta(days=random.randint(0, 13), hours=random.randint(0, 23)),
            )
        )

    # Vendor 2 products: 11 AUTHENTIC, 2 FAKE, 2 SUSPICIOUS = 73.3% → Silver
    vendor2_products = [p for p in products if p.vendor_id == "bold-eagle-abuja"]
    vendor2_verdicts = (["AUTHENTIC"] * 11) + (["FAKE"] * 2) + (["SUSPICIOUS"] * 2)
    random.shuffle(vendor2_verdicts)

    for i, verdict in enumerate(vendor2_verdicts):
        product = random.choice(vendor2_products)
        if verdict == "AUTHENTIC":
            score = random.uniform(0.92, 0.99)
        elif verdict == "SUSPICIOUS":
            score = random.uniform(0.75, 0.91)
        else:
            score = random.uniform(0.30, 0.60)
        events.append(
            ScanEvent(
                id=uuid.uuid4().hex,
                product_id=product.id,
                vendor_id=product.vendor_id,
                verdict=verdict,
                score=round(score, 4),
                device_hash=f"device-{random.randint(1000, 9999)}",
                scanned_at=now - timedelta(days=random.randint(0, 13), hours=random.randint(0, 23)),
            )
        )

    return events


async def seed():
    engine = create_async_engine(settings.DATABASE_URL, echo=False)

    # Ensure tables exist
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    products = _generate_products()
    scan_events = _generate_scan_events(products)

    async with async_session() as session:
        # Users
        session.add(BRAND_USER)
        for vendor in VENDOR_USERS:
            session.add(vendor)

        # Batches
        for batch in BATCHES:
            session.add(batch)

        # Products
        for product in products:
            session.add(product)

        # Scan events
        for event in scan_events:
            session.add(event)

        await session.commit()

    await engine.dispose()

    print("   Seed complete!")
    print(f"  Users:       1 brand + {len(VENDOR_USERS)} vendors")
    print(f"  Batches:     {len(BATCHES)}")
    print(f"  Products:    {len(products)}")
    print(f"  Scan events: {len(scan_events)}")
    print()
    print("  Vendor 1 (swift-mango-lagos): ~93% authentic → Gold")
    print("  Vendor 2 (bold-eagle-abuja):  ~73% authentic → Silver")


if __name__ == "__main__":
    asyncio.run(seed())
