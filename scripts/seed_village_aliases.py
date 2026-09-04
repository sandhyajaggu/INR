"""Re-runnable seed for known alternate spellings of seeded village names.

Real electoral-roll sheets use inconsistent spellings of village names
(ALL CAPS, missing spaces, transliteration variants) that don't match
db/seed_geography.sql's canonical villages.name. Rather than renaming every
uploaded sheet, each known variant is registered here so bulk-import
resolves either spelling to the same village_id — voters aren't split
across duplicate village records depending on which spelling their sheet
happened to use.

Idempotent — safe to run again via `ON CONFLICT DO NOTHING` on the unique
(mandal_id, alias) constraint. Sourced from a fuzzy-match diff of a real
~235k-row voters sheet against the seeded village list, keeping only
matches with similarity >= 0.85.

Usage:
    python -m scripts.seed_village_aliases
"""

import asyncio

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.core.database import AsyncSessionLocal
from app.models.geography import Mandal, Village, VillageAlias

MANDAL_VILLAGE_ALIASES: dict[str, list[tuple[str, str]]] = {
    "Gudluru": [
        ("CHINALATRAPI", "Chinala Trapi"),
        ("BASIREDDYPALEM", "Basireddy Palem"),
        ("RAVURU", "Ravur"),
        ("YELURUPADU H/O.CHEVURU", "yellurupadu H/O chevuru"),
        ("NAIDUPALEM", "Nayudupalem"),
        ("TETTU H /O MOCHERLA", "Tettu H/O mocherla"),
        ("TETTU H/O.MOCHERLA", "Tettu H/O mocherla"),
        ("AMMAVARIPALEM", "Ammavari Palem"),
        ("RALLAPADU H/O.BASIREDDIPALEM", "Rallapadu H/O basireddypalem"),
        ("CHIMIDITHIPADU", "Chimidithapadu"),
        ("VENKATESWARAPURAM H/O.DAPPALAMPADU", "Venkateswarapuram H/O dappalmpadu"),
        ("R.C.AGRAHARAM", "RC Agraharam"),
    ],
    "Kandukur": [
        ("KANDUKURU MUNICIPALITY", "Kandukur Municipality"),
        ("PALUKURU", "Palukur"),
        ("OGURU", "Ogur"),
        ("KONDAMUDUSUPALEM", "Kondamudusu Palem"),
        ("PALURU", "Palur"),
        ("MAHADEVAPURAM", "Mahadevapuram (R)"),
        ("G.MEKAPADU", "G. Meka Padu"),
        ("KOVURU", "Kovur"),
        ("KONDI KANDUKUR", "Kondikandukur"),
        ("ANANTHASAGARAM", "Anantha Sagaram"),
        ("JILLELLAMUDI", "Jillelamudi"),
    ],
    "Lingasamudram": [
        ("VEERARAGHAVUNIKOTA", "Veera Raghavuni Kota"),
        ("PEDAPAVANI H/O MUTYALAPADU", "Pedapavni H/O mutyalapadu"),
        ("VAKAMALLAVARIPALEM H/O LINGASAMUDRAM", "Vakamllavaripalem H/O lingasamudram"),
        ("PEDAPAVANI H/O.MUTHYALAPADU", "Pedapavni H/O mutyalapadu"),
        ("THIMMAREDDIPALEM", "Thimmareddy Palem"),
        ("MUTHYALAPADU", "Mutyalapadu"),
        ("MALAKONDARAYUNIPALEM", "Mala Konda Rayunipalem"),
        ("ANGIREKULAPADU", "Agnirekulapadu"),
        ("THIMMAREDDYPALEM", "Thimmareddy Palem"),
        ("PEDAPAVANI H/O.MUTYALAPADU", "Pedapavni H/O mutyalapadu"),
        ("RACHERUVU RAJUPALEM", "Racheruvurajupalem"),
        ("PEDAPAVANI H/O. MUTHYALAPADU", "Pedapavni H/O mutyalapadu"),
        ("SATYANARAYANAPURAM H/O.PEDAPAVANI", "satyanarayanapuram H/O pedapavani"),
        ("MEDARAMETLAPALEM H/O.MUTHYALAPADU", "Medarametlapalem"),
    ],
    "Ulavapadu": [
        ("BHEEMAVARAM", "Beemavaram"),
        ("BADDIPUDI", "Baddepudi"),
        ("VEEREPALLI", "Verepalli"),
        ("PEDA PATTAPUPALEM H/O.CHAKICHERLA", "Peddapatupalem H/O chakicherla"),
        ("PEDA PATTAPUPALEM H/O CHAKICHERLA", "Peddapatupalem H/O chakicherla"),
        ("UPPARAPALEM H/O.KAREDU", "Urrapalem H/O karedu"),
        ("KRISHNAPURAM", "Krinshnapuram"),
        ("PEDAPALLEPALEM H/O. KAREDU", "Peddapalem H/O karedu"),
        ("ALAGAYAPALEM H/O.KAREDU", "Alagyapalem H/O karedu"),
        ("ALAGAYA PALEM H/O KAREDU", "Alagyapalem H/O karedu"),
        ("ALAGAYAPALEM H/O. KAREDU", "Alagyapalem H/O karedu"),
        ("KOLLURUPADU RAJUPALEM", "Korrupadu rajupalem"),
        ("K RAJUPALEM", "K rajuplalem"),
    ],
    "Voletivaripalem": [
        ("AYYAVARIPALLI", "Ayyivaripalem"),
        ("MALAKONDA,RAMALINGAPURAM H/O AYYAVAR IPALLI", "Malakonda"),
        ("NALADALPURU", "Nalandapuru"),
        ("ANKABHUPALAPURAM", "Ankhabhupalapalem"),
        ("SINGAMANENIPALLI", "Sigamanenipalli"),
        ("POLINENI CHERUVU", "Polini cheruvu"),
        ("KAKARLA PALEM H/O CHUNDI", "kakarlapalem H/O chundi"),
        ("PEDDA AMMA PALEM", "Peddammapalem"),
        ("BANGARA KKAPALEM H/O CHUNDI", "Bangarakkaplem H/O chundi"),
        ("KUMMARA PALEM H/O POKURU", "Kummarapalem H/O pokuru"),
        ("GARUKUPALEM H/O POLINENI CHERUVU", "Garukapalem H/O polini cheruvu"),
    ],
}


async def seed() -> None:
    async with AsyncSessionLocal() as db:
        mandal_ids = {
            name: mandal_id
            for name, mandal_id in (await db.execute(select(Mandal.name, Mandal.id))).all()
        }
        village_ids = {
            (mandal_id, name): village_id
            for village_id, mandal_id, name in (
                await db.execute(select(Village.id, Village.mandal_id, Village.name))
            ).all()
        }

        inserted = 0
        for mandal_name, aliases in MANDAL_VILLAGE_ALIASES.items():
            mandal_id = mandal_ids[mandal_name]
            for alias, canonical_name in aliases:
                village_id = village_ids.get((mandal_id, canonical_name))
                if village_id is None:
                    raise RuntimeError(
                        f"Canonical village '{canonical_name}' not found in mandal '{mandal_name}' "
                        f"(alias '{alias}') — check db/seed_geography.sql is up to date"
                    )
                stmt = (
                    pg_insert(VillageAlias)
                    .values(village_id=village_id, mandal_id=mandal_id, alias=alias)
                    .on_conflict_do_nothing(index_elements=["mandal_id", "alias"])
                )
                result = await db.execute(stmt)
                inserted += result.rowcount
        await db.commit()

        total = (await db.execute(select(VillageAlias.id))).all()
        print(f"Seeded village aliases: {inserted} newly inserted, {len(total)} total.")


if __name__ == "__main__":
    asyncio.run(seed())
