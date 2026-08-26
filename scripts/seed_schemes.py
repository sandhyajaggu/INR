"""Re-runnable seed for the 7 welfare schemes (the beneficiary_scheme_router
factory looks each one up by scheme_code, so every per-scheme endpoint needs
its row to exist here first).

Usage:
    python -m scripts.seed_schemes
"""

import asyncio

from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.core.database import AsyncSessionLocal
from app.models.schemes import Scheme

SCHEMES = [
    {"scheme_code": "cmrf", "scheme_name": "CM Relief Fund", "category": "Relief Fund"},
    {"scheme_code": "aadabidda_nidhi", "scheme_name": "Aadabidda Nidhi", "category": "Welfare"},
    {"scheme_code": "thalliki_vandanam", "scheme_name": "Thalliki Vandanam", "category": "Education"},
    {"scheme_code": "deepam_scheme", "scheme_name": "Deepam Gas Scheme", "category": "Welfare"},
    {"scheme_code": "maha_shakthi", "scheme_name": "Maha Shakthi (Free Bus Travel)", "category": "Transport"},
    {"scheme_code": "annadata_sukhibhava", "scheme_name": "Annadata Sukhibhava", "category": "Agriculture"},
    {"scheme_code": "yuvagalam", "scheme_name": "Yuvagalam", "category": "Employment"},
]


async def seed() -> None:
    async with AsyncSessionLocal() as db:
        for scheme in SCHEMES:
            stmt = (
                pg_insert(Scheme)
                .values(**scheme, status="active")
                .on_conflict_do_nothing(index_elements=["scheme_code"])
            )
            await db.execute(stmt)
        await db.commit()
        print(f"Seeded {len(SCHEMES)} schemes.")


if __name__ == "__main__":
    asyncio.run(seed())
