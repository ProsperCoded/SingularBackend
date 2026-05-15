from sqlmodel import select, func
from sqlmodel.ext.asyncio.session import AsyncSession
from datetime import datetime, timedelta
from models.scan_event import ScanEvent


def get_badge_tier(score: float) -> str:
    """Map a trust score (0-100) to a badge tier."""
    if score >= 90:
        return "Gold"
    elif score >= 70:
        return "Silver"
    return "Bronze"


async def compute_trust_score(
    session: AsyncSession, vendor_id: str
) -> tuple[float, str, dict]:
    """
    Compute a vendor's trust score from their scan event history.

    Returns:
        (trust_score, badge_tier, stats_dict) where stats_dict has keys:
        total_scans, authentic_scans, fake_attempts, suspicious_scans
    """

    # Count scans by verdict for this vendor
    statement = (
        select(ScanEvent.verdict, func.count(ScanEvent.id))
        .where(ScanEvent.vendor_id == vendor_id)
        .group_by(ScanEvent.verdict)
    )
    results = await session.exec(statement)
    counts = {row[0]: row[1] for row in results.all()}

    authentic = counts.get("AUTHENTIC", 0)
    fake = counts.get("FAKE", 0)
    suspicious = counts.get("SUSPICIOUS", 0)
    total = authentic + fake + suspicious

    # Trust score starts at 50.0. 
    # We use a prior of 10 total scans (5 authentic, 5 non-authentic) to provide 
    # a balanced starting point that moves as real data arrives.
    prior_authentic = 5
    prior_total = 10
    
    trust_score = round(((authentic + prior_authentic) / (total + prior_total)) * 100, 2)

    badge_tier = get_badge_tier(trust_score)

    stats = {
        "total_scans": total,
        "authentic_scans": authentic,
        "fake_attempts": fake,
        "suspicious_scans": suspicious,
    }

    return trust_score, badge_tier, stats


async def compute_score_trend(session: AsyncSession, vendor_id: str) -> str:
    """
    Compare the trust score over the last 7 days vs the previous 7 days.
    Returns 'up', 'down', or 'stable'.
    """

    now = datetime.utcnow()
    seven_days_ago = now - timedelta(days=7)
    fourteen_days_ago = now - timedelta(days=14)

    async def _score_for_period(start: datetime, end: datetime) -> float | None:
        statement = (
            select(ScanEvent.verdict, func.count(ScanEvent.id))
            .where(
                ScanEvent.vendor_id == vendor_id,
                ScanEvent.scanned_at >= start,
                ScanEvent.scanned_at < end,
            )
            .group_by(ScanEvent.verdict)
        )
        results = await session.exec(statement)
        counts = {row[0]: row[1] for row in results.all()}
        total = sum(counts.values())
        if total == 0:
            return None
        return (counts.get("AUTHENTIC", 0) / total) * 100

    recent_score = await _score_for_period(seven_days_ago, now)
    previous_score = await _score_for_period(fourteen_days_ago, seven_days_ago)

    # If either period has no data, we can't determine a trend
    if recent_score is None or previous_score is None:
        return "stable"

    diff = recent_score - previous_score
    if diff > 2:
        return "up"
    elif diff < -2:
        return "down"
    return "stable"
