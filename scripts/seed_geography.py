"""Re-runnable seed for the 109-Kandukur constituency geography.

Mirrors seed_geography.sql exactly (5 mandals, every village) but is
idempotent — safe to run again on an already-seeded database via
`ON CONFLICT DO NOTHING` on the unique (mandal name) / (mandal_id, name)
constraints.

Usage:
    python -m scripts.seed_geography
"""

import asyncio

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.core.database import AsyncSessionLocal
from app.models.geography import Mandal, Village

MANDAL_VILLAGES: dict[str, list[str]] = {
    "Kandukur": [
        "Anandapuram", "Anantha Sagaram", "Donda Padu", "G.Meka Padu", "Jillelamudi",
        "Kancharagunta", "Kondamudusu Palem", "Kandukur", "Kovur", "Machavaram",
        "Madanagopalapuram", "Mahadevapuram", "Mopadu", "Muppalakesaram", "Ogur",
        "Palukur", "Palur", "Pandalapadu", "Vikkiralapeta",
    ],
    "Lingasamudram": [
        "Anneboinapalle", "Cheemalapenta", "Chinapavani", "Gangapalem",
        "Jagamreddi Khandrika", "Lingasamudram", "Malakondarayunipalem",
        "Mogilicherla", "Mukteswaram", "Mutyalapadu", "Narasimhapuram", "Pentrala",
        "Racheruvurajupalem", "Rallapadu", "Thimmareddypalem", "Thunugunta",
        "Thurpu Rajupalem", "Veeraraghavunikota", "Vengalapuram", "Viswanadhapuram",
    ],
    "Gudluru": [
        "Ammavaripalem", "Basireddypalem", "Chevuru", "Chinalatrapi", "Dappalampadu",
        "Darakanipadu", "Gudluru", "Gundlapalem", "Kothapeta", "Mocherla",
        "Nayudupalem", "Parakondapadu Agraharam", "Parakondapadu", "Potluru",
        "Puretipalle", "Ravur", "Swarnajipuram", "Venkampeta",
    ],
    "Ulavapadu": [
        "Atmakur", "Baddepudi", "Bheemavaram", "Chagallu", "Chaki Cherla",
        "K. Rajupalem", "Karedu", "Kollurupadu", "Krishnapuram", "Manneti Kota",
        "Ramayapatnam", "Veerepalle",
    ],
    "Voletivaripalem": [
        "Ayyavaripalle", "Chundi", "East Polineni Palem", "Kakutur", "Kalavalla",
        "Kondareddipalem", "Kondasamudram", "Naladalapur", "Nawabpalem",
        "Nekunam Puram K.Kandrika", "Nekunampuram @ Pokur", "Nukavaram",
        "Polineni Cheruvu", "Ramachandrapuram", "Ramalingapuram", "Sakhavaram",
        "Sameerapalem", "Singamnenipalle", "Veeranna Palem", "Voletivaripalem",
        "Z. Uppalapadu",
    ],
}


async def seed() -> None:
    async with AsyncSessionLocal() as db:
        for mandal_name in MANDAL_VILLAGES:
            stmt = pg_insert(Mandal).values(name=mandal_name).on_conflict_do_nothing(index_elements=["name"])
            await db.execute(stmt)
        await db.commit()

        mandal_ids = {
            name: mandal_id
            for name, mandal_id in (await db.execute(select(Mandal.name, Mandal.id))).all()
        }

        for mandal_name, villages in MANDAL_VILLAGES.items():
            mandal_id = mandal_ids[mandal_name]
            for village_name in villages:
                stmt = (
                    pg_insert(Village)
                    .values(mandal_id=mandal_id, name=village_name)
                    .on_conflict_do_nothing(index_elements=["mandal_id", "name"])
                )
                await db.execute(stmt)
        await db.commit()

        total_mandals = (await db.execute(select(Mandal.id))).all()
        total_villages = (await db.execute(select(Village.id))).all()
        print(f"Seeded geography: {len(total_mandals)} mandals, {len(total_villages)} villages.")


if __name__ == "__main__":
    asyncio.run(seed())
