-- ============================================================================
-- Seed: 109-Kandukur constituency — 5 mandals, all villages
-- Run after schema.sql
-- ============================================================================

INSERT INTO mandals (name) VALUES
    ('Kandukur'),
    ('Lingasamudram'),
    ('Gudluru'),
    ('Ulavapadu'),
    ('Voletivaripalem');

-- Prune villages renamed or dropped by this update (safe no-op on a fresh DB).
-- If a village here still has booths attached, the FK RESTRICT on
-- booths.village_id will block the delete until those booths are reassigned.
DELETE FROM villages
USING mandals
WHERE villages.mandal_id = mandals.id
  AND (
    (mandals.name = 'Kandukur' AND villages.name IN ('G.Meka Padu', 'Kandukur', 'Mahadevapuram'))
    OR (mandals.name = 'Lingasamudram' AND villages.name IN ('Malakondarayunipalem', 'Thimmareddypalem', 'Thurpu Rajupalem', 'Veeraraghavunikota'))
    OR (mandals.name = 'Gudluru' AND villages.name IN ('Ammavaripalem', 'Basireddypalem', 'Chinalatrapi', 'Parakondapadu Agraharam', 'Venkampeta'))
    OR (mandals.name = 'Ulavapadu' AND villages.name IN ('Atmakur', 'Bheemavaram', 'Chagallu', 'Chaki Cherla', 'K. Rajupalem', 'Karedu', 'Kollurupadu', 'Krishnapuram', 'Manneti Kota', 'Veerepalle'))
    OR (mandals.name = 'Voletivaripalem' AND villages.name IN ('Ayyavaripalle', 'East Polineni Palem', 'Kakutur', 'Kondareddipalem', 'Naladalapur', 'Nawabpalem', 'Nekunam Puram K.Kandrika', 'Nekunampuram @ Pokur', 'Polineni Cheruvu', 'Ramachandrapuram', 'Sameerapalem', 'Singamnenipalle', 'Veeranna Palem', 'Z. Uppalapadu'))
  );

-- Kandukur
INSERT INTO villages (mandal_id, name)
SELECT id, v FROM mandals, UNNEST(ARRAY[
    'Anandapuram','Anantha Sagaram','Donda Padu','G. Meka Padu','Jillelamudi',
    'Kancharagunta','Kondamudusu Palem','Kondikandukur','Kovur','Machavaram',
    'Madanagopalapuram','Mahadevapuram (R)','Mopadu','Muppalakesaram','Ogur',
    'Palukur','Palur','Pandalapadu','Vikkiralapeta','Balijapalem','Ganikunta',
    'Guthikondavaripalem','Kammavaripalem','Narisettivaripalem','Kandukur Municipality'
]) AS v
WHERE mandals.name = 'Kandukur';

-- Lingasamudram
INSERT INTO villages (mandal_id, name)
SELECT id, v FROM mandals, UNNEST(ARRAY[
    'Anneboinapalle','Cheemalapenta','Chinapavani','Gangapalem',
    'Jagamreddi Khandrika','Lingasamudram','Mala Konda Rayunipalem',
    'Mogilicherla','Mukteswaram','Mutyalapadu','Narasimhapuram','Pentrala',
    'Racheruvurajupalem','Rallapadu','Thimmareddy Palem','Thunugunta',
    'Thurpurajupalem','Veera Raghavuni Kota','Vengalapuram','Viswanadhapuram',
    'Agnirekulapadu','Medarametlapalem','Muttvaripalem H/O mutyalapadu',
    'Pedapavni H/O mutyalapadu','satyanarayanapuram H/O pedapavani',
    'Vakamllavaripalem H/O lingasamudram','Yerrareddipalem'
]) AS v
WHERE mandals.name = 'Lingasamudram';

-- Gudluru
INSERT INTO villages (mandal_id, name)
SELECT id, v FROM mandals, UNNEST(ARRAY[
    'Ammavari Palem','Basireddy Palem','Chevuru','Chinala Trapi','Dappalampadu',
    'Darakanipadu','Gudluru','Gundlapalem','Kothapeta','Mocherla',
    'Nayudupalem','Parakonda Paduagraharam','Parakondapadu','Potluru',
    'Puretipalle','Ravur','Swarnajipuram','Venkam Peta','Avulavaripalem',
    'Chimidithapadu','Mogalluru','Pajerla','Puretipalli','RR colony',
    'RC Agraharam','Rajupalem','Rallapadu H/O basireddypalem',
    'Tettu H/O mocherla','Venkateswarapuram H/O dappalmpadu',
    'yellurupadu H/O chevuru'
]) AS v
WHERE mandals.name = 'Gudluru';

-- Ulavapadu
INSERT INTO villages (mandal_id, name)
SELECT id, v FROM mandals, UNNEST(ARRAY[
    'Alagyapalem H/O karedu','Atmakuru','Baddepudi','Beemavaram','Chagollu',
    'Chakicherla','K rajuplalem','karedu','Korrupadu rajupalem',
    'Krinshnapuram','Mannetikota','Peddapatupalem H/O chakicherla',
    'Peddapalem H/O karedu','Ramayapatnam','Ulavapadu',
    'Urrapalem H/O karedu','Verepalli'
]) AS v
WHERE mandals.name = 'Ulavapadu';

-- Voletivaripalem
INSERT INTO villages (mandal_id, name)
SELECT id, v FROM mandals, UNNEST(ARRAY[
    'Ammapalem H/O chundi','Ankhabhupalapalem','Ayyivaripalem','Badevaripalem',
    'Bangarakkaplem H/O chundi','Cherlopalem H/O kakuturu','Chundi',
    'Garukapalem H/O polini cheruvu','kakarlapalem H/O chundi','Kakuturu',
    'Kalavalla','Kondareddypalem','Kondasamudram','Kummarapalem H/O pokuru',
    'Lingapalem','Malakonda','Ramalingapuram','Nalandapuru',
    'Nekunampuram H/O pokuru','Nukavaram','Peddammapalem','Pokuru',
    'Polini cheruvu','Polinenipalem','Sakhavaram','Samirapalem',
    'Sigamanenipalli','Voletivaripalem','Z uppalapadu'
]) AS v
WHERE mandals.name = 'Voletivaripalem';

-- Sanity check
-- SELECT m.name, COUNT(vl.id) AS village_count
-- FROM mandals m LEFT JOIN villages vl ON vl.mandal_id = m.id
-- GROUP BY m.name ORDER BY m.name;
