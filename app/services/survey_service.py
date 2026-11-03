"""Voter survey lookups shared with other modules."""

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession


async def latest_survey_by_voter(db: AsyncSession, voter_ids: list[int]) -> dict[int, dict[str, Any]]:
    """Latest voter survey per voter id. Voters with no survey are absent from the result."""
    return {}


async def surveyed_counts_by_booth(db: AsyncSession, booth_ids: list[int]) -> dict[int, int]:
    """Number of distinct surveyed voters per booth id."""
    return {}
