"""Re-runnable seed for the 109-Kandukur constituency geography.

Mirrors seed_geography.sql exactly (5 mandals, every village), prunes
villages renamed/removed by the latest update (see PRUNED_VILLAGES), and is
idempotent — safe to run again on an already-seeded database via
`ON CONFLICT DO NOTHING` on the unique (mandal name) / (mandal_id, name)
constraints.

Usage:
    python -m scripts.seed_geography
"""

import asyncio

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.core.database import AsyncSessionLocal
from app.models.geography import Mandal, Village

MANDAL_VILLAGES: dict[str, list[str]] = {
    "Kandukur": [
        "Anandapuram", "Anantha Sagaram", "Donda Padu", "G. Meka Padu", "Jillelamudi",
        "Kancharagunta", "Kondamudusu Palem", "Kondikandukur", "Kovur", "Machavaram",
        "Madanagopalapuram", "Mahadevapuram (R)", "Mopadu", "Muppalakesaram", "Ogur",
        "Palukur", "Palur", "Pandalapadu", "Vikkiralapeta", "Balijapalem", "Ganikunta",
        "Guthikondavaripalem", "Kammavaripalem", "Narisettivaripalem",
    ],
    "Lingasamudram": [
        "Anneboinapalle", "Cheemalapenta", "Chinapavani", "Gangapalem",
        "Jagamreddi Khandrika", "Lingasamudram", "Mala Konda Rayunipalem",
        "Mogilicherla", "Mukteswaram", "Mutyalapadu", "Narasimhapuram", "Pentrala",
        "Racheruvurajupalem", "Rallapadu", "Thimmareddy Palem", "Thunugunta",
        "Thurpurajupalem", "Veera Raghavuni Kota", "Vengalapuram", "Viswanadhapuram",
        "Agnirekulapadu", "Medarametlapalem", "Muttvaripalem H/O mutyalapadu",
        "Pedapavni H/O mutyalapadu", "satyanarayanapuram H/O pedapavani",
        "Vakamllavaripalem H/O lingasamudram", "Yerrareddipalem",
    ],
    "Gudluru": [
        "Ammavari Palem", "Basireddy Palem", "Chevuru", "Chinala Trapi", "Dappalampadu",
        "Darakanipadu", "Gudluru", "Gundlapalem", "Kothapeta", "Mocherla",
        "Nayudupalem", "Parakonda Paduagraharam", "Parakondapadu", "Potluru",
        "Puretipalle", "Ravur", "Swarnajipuram", "Venkam Peta", "Avulavaripalem",
        "Chimidithapadu", "Mogalluru", "Pajerla", "Puretipalli", "RR colony",
        "RC Agraharam", "Rajupalem", "Rallapadu H/O basireddypalem",
        "Tettu H/O mocherla", "Venkateswarapuram H/O dappalmpadu",
        "yellurupadu H/O chevuru",
    ],
    "Ulavapadu": [
        "Alagyapalem H/O karedu", "Atmakuru", "Baddepudi", "Beemavaram", "Chagollu",
        "Chakicherla", "K rajuplalem", "karedu", "Korrupadu rajupalem",
        "Krinshnapuram", "Mannetikota", "Peddapatupalem H/O chakicherla",
        "Peddapalem H/O karedu", "Ramayapatnam", "Ulavapadu",
        "Urrapalem H/O karedu", "Verepalli",
    ],
    "Voletivaripalem": [
        "Ammapalem H/O chundi", "Ankhabhupalapalem", "Ayyivaripalem", "Badevaripalem",
        "Bangarakkaplem H/O chundi", "Cherlopalem H/O kakuturu", "Chundi",
        "Garukapalem H/O polini cheruvu", "kakarlapalem H/O chundi", "Kakuturu",
        "Kalavalla", "Kondareddypalem", "Kondasamudram", "Kummarapalem H/O pokuru",
        "Lingapalem", "Malakonda", "Ramalingapuram", "Nalandapuru",
        "Nekunampuram H/O pokuru", "Nukavaram", "Peddammapalem", "Pokuru",
        "Polini cheruvu", "Polinenipalem", "Sakhavaram", "Samirapalem",
        "Sigamanenipalli", "Voletivaripalem", "Z uppalapadu",
    ],
}

# Villages renamed or dropped by the most recent update. Deleting them is
# safe to re-run; if a village here still has booths attached, the FK
# RESTRICT on booths.village_id will surface as an IntegrityError until
# those booths are reassigned.
PRUNED_VILLAGES: dict[str, list[str]] = {
    "Kandukur": ["G.Meka Padu", "Kandukur", "Mahadevapuram"],
    "Lingasamudram": ["Malakondarayunipalem", "Thimmareddypalem", "Thurpu Rajupalem", "Veeraraghavunikota"],
    "Gudluru": ["Ammavaripalem", "Basireddypalem", "Chinalatrapi", "Parakondapadu Agraharam", "Venkampeta"],
    "Ulavapadu": [
        "Atmakur", "Bheemavaram", "Chagallu", "Chaki Cherla", "K. Rajupalem",
        "Karedu", "Kollurupadu", "Krishnapuram", "Manneti Kota", "Veerepalle",
    ],
    "Voletivaripalem": [
        "Ayyavaripalle", "East Polineni Palem", "Kakutur", "Kondareddipalem", "Naladalapur",
        "Nawabpalem", "Nekunam Puram K.Kandrika", "Nekunampuram @ Pokur", "Polineni Cheruvu",
        "Ramachandrapuram", "Sameerapalem", "Singamnenipalle", "Veeranna Palem", "Z. Uppalapadu",
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

        for mandal_name, pruned_names in PRUNED_VILLAGES.items():
            mandal_id = mandal_ids[mandal_name]
            stmt = delete(Village).where(Village.mandal_id == mandal_id, Village.name.in_(pruned_names))
            await db.execute(stmt)
        await db.commit()

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
