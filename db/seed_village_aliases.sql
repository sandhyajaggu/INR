-- ============================================================================
-- Seed: known alternate spellings of seeded village names.
-- Run after seed_geography.sql. Mirrors scripts/seed_village_aliases.py.
--
-- Real electoral-roll sheets use inconsistent spellings of village names
-- (ALL CAPS, missing spaces, transliteration variants) that don't match
-- villages.name. Registering each known variant here lets bulk-import
-- resolve either spelling to the same village_id, instead of every
-- uploaded sheet needing to be renamed to match exactly.
-- ============================================================================

INSERT INTO village_aliases (village_id, mandal_id, alias)
SELECT v.id, v.mandal_id, x.alias
FROM (VALUES
    ('Gudluru', 'Chinala Trapi', 'CHINALATRAPI'),
    ('Gudluru', 'Basireddy Palem', 'BASIREDDYPALEM'),
    ('Gudluru', 'Ravur', 'RAVURU'),
    ('Gudluru', 'yellurupadu H/O chevuru', 'YELURUPADU H/O.CHEVURU'),
    ('Gudluru', 'Nayudupalem', 'NAIDUPALEM'),
    ('Gudluru', 'Tettu H/O mocherla', 'TETTU H /O MOCHERLA'),
    ('Gudluru', 'Tettu H/O mocherla', 'TETTU H/O.MOCHERLA'),
    ('Gudluru', 'Ammavari Palem', 'AMMAVARIPALEM'),
    ('Gudluru', 'Rallapadu H/O basireddypalem', 'RALLAPADU H/O.BASIREDDIPALEM'),
    ('Gudluru', 'Chimidithapadu', 'CHIMIDITHIPADU'),
    ('Gudluru', 'Venkateswarapuram H/O dappalmpadu', 'VENKATESWARAPURAM H/O.DAPPALAMPADU'),
    ('Gudluru', 'RC Agraharam', 'R.C.AGRAHARAM'),
    ('Gudluru', 'Venkam Peta', 'VENKAMPETA H/O.BASIREDDIPALEM'),
    ('Gudluru', 'Avulavaripalem', 'AVULAVARIPALEM H/O. RAVURU'),

    ('Kandukur', 'Kandukur Municipality', 'KANDUKURU MUNICIPALITY'),
    ('Kandukur', 'Palukur', 'PALUKURU'),
    ('Kandukur', 'Ogur', 'OGURU'),
    ('Kandukur', 'Kondamudusu Palem', 'KONDAMUDUSUPALEM'),
    ('Kandukur', 'Palur', 'PALURU'),
    ('Kandukur', 'Mahadevapuram (R)', 'MAHADEVAPURAM'),
    ('Kandukur', 'G. Meka Padu', 'G.MEKAPADU'),
    ('Kandukur', 'Kovur', 'KOVURU'),
    ('Kandukur', 'Kondikandukur', 'KONDI KANDUKUR'),
    ('Kandukur', 'Anantha Sagaram', 'ANANTHASAGARAM'),
    ('Kandukur', 'Jillelamudi', 'JILLELLAMUDI'),

    ('Lingasamudram', 'Veera Raghavuni Kota', 'VEERARAGHAVUNIKOTA'),
    ('Lingasamudram', 'Pedapavni H/O mutyalapadu', 'PEDAPAVANI H/O MUTYALAPADU'),
    ('Lingasamudram', 'Vakamllavaripalem H/O lingasamudram', 'VAKAMALLAVARIPALEM H/O LINGASAMUDRAM'),
    ('Lingasamudram', 'Pedapavni H/O mutyalapadu', 'PEDAPAVANI H/O.MUTHYALAPADU'),
    ('Lingasamudram', 'Thimmareddy Palem', 'THIMMAREDDIPALEM'),
    ('Lingasamudram', 'Mutyalapadu', 'MUTHYALAPADU'),
    ('Lingasamudram', 'Mala Konda Rayunipalem', 'MALAKONDARAYUNIPALEM'),
    ('Lingasamudram', 'Agnirekulapadu', 'ANGIREKULAPADU'),
    ('Lingasamudram', 'Thimmareddy Palem', 'THIMMAREDDYPALEM'),
    ('Lingasamudram', 'Pedapavni H/O mutyalapadu', 'PEDAPAVANI H/O.MUTYALAPADU'),
    ('Lingasamudram', 'Racheruvurajupalem', 'RACHERUVU RAJUPALEM'),
    ('Lingasamudram', 'Pedapavni H/O mutyalapadu', 'PEDAPAVANI H/O. MUTHYALAPADU'),
    ('Lingasamudram', 'satyanarayanapuram H/O pedapavani', 'SATYANARAYANAPURAM H/O.PEDAPAVANI'),
    ('Lingasamudram', 'Medarametlapalem', 'MEDARAMETLAPALEM H/O.MUTHYALAPADU'),
    ('Lingasamudram', 'Muttvaripalem H/O mutyalapadu', 'MUTTAMVARIPALEM'),

    ('Ulavapadu', 'Beemavaram', 'BHEEMAVARAM'),
    ('Ulavapadu', 'Baddepudi', 'BADDIPUDI'),
    ('Ulavapadu', 'Verepalli', 'VEEREPALLI'),
    ('Ulavapadu', 'Peddapatupalem H/O chakicherla', 'PEDA PATTAPUPALEM H/O.CHAKICHERLA'),
    ('Ulavapadu', 'Peddapatupalem H/O chakicherla', 'PEDA PATTAPUPALEM H/O CHAKICHERLA'),
    ('Ulavapadu', 'Urrapalem H/O karedu', 'UPPARAPALEM H/O.KAREDU'),
    ('Ulavapadu', 'Krinshnapuram', 'KRISHNAPURAM'),
    ('Ulavapadu', 'Peddapalem H/O karedu', 'PEDAPALLEPALEM H/O. KAREDU'),
    ('Ulavapadu', 'Alagyapalem H/O karedu', 'ALAGAYAPALEM H/O.KAREDU'),
    ('Ulavapadu', 'Alagyapalem H/O karedu', 'ALAGAYA PALEM H/O KAREDU'),
    ('Ulavapadu', 'Alagyapalem H/O karedu', 'ALAGAYAPALEM H/O. KAREDU'),
    ('Ulavapadu', 'Korrupadu rajupalem', 'KOLLURUPADU RAJUPALEM'),
    ('Ulavapadu', 'K rajuplalem', 'K RAJUPALEM'),

    ('Voletivaripalem', 'Nalandapuru', 'NALADALPURU'),
    ('Voletivaripalem', 'Ankhabhupalapalem', 'ANKABHUPALAPURAM'),
    ('Voletivaripalem', 'Sigamanenipalli', 'SINGAMANENIPALLI'),
    ('Voletivaripalem', 'Polini cheruvu', 'POLINENI CHERUVU'),
    ('Voletivaripalem', 'kakarlapalem H/O chundi', 'KAKARLA PALEM H/O CHUNDI'),
    ('Voletivaripalem', 'Peddammapalem', 'PEDDA AMMA PALEM'),
    ('Voletivaripalem', 'Bangarakkaplem H/O chundi', 'BANGARA KKAPALEM H/O CHUNDI'),
    ('Voletivaripalem', 'Kummarapalem H/O pokuru', 'KUMMARA PALEM H/O POKURU'),
    ('Voletivaripalem', 'Garukapalem H/O polini cheruvu', 'GARUKUPALEM H/O POLINENI CHERUVU')
) AS x(mandal_name, village_name, alias)
JOIN mandals m ON m.name = x.mandal_name
JOIN villages v ON v.mandal_id = m.id AND v.name = x.village_name
ON CONFLICT (mandal_id, alias) DO NOTHING;

-- Sanity check
-- SELECT m.name, COUNT(a.id) AS alias_count
-- FROM mandals m LEFT JOIN village_aliases a ON a.mandal_id = m.id
-- GROUP BY m.name ORDER BY m.name;
