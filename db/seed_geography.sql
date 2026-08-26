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

-- Kandukur
INSERT INTO villages (mandal_id, name)
SELECT id, v FROM mandals, UNNEST(ARRAY[
    'Anandapuram','Anantha Sagaram','Donda Padu','G.Meka Padu','Jillelamudi',
    'Kancharagunta','Kondamudusu Palem','Kandukur','Kovur','Machavaram',
    'Madanagopalapuram','Mahadevapuram','Mopadu','Muppalakesaram','Ogur',
    'Palukur','Palur','Pandalapadu','Vikkiralapeta'
]) AS v
WHERE mandals.name = 'Kandukur';

-- Lingasamudram
INSERT INTO villages (mandal_id, name)
SELECT id, v FROM mandals, UNNEST(ARRAY[
    'Anneboinapalle','Cheemalapenta','Chinapavani','Gangapalem',
    'Jagamreddi Khandrika','Lingasamudram','Malakondarayunipalem',
    'Mogilicherla','Mukteswaram','Mutyalapadu','Narasimhapuram','Pentrala',
    'Racheruvurajupalem','Rallapadu','Thimmareddypalem','Thunugunta',
    'Thurpu Rajupalem','Veeraraghavunikota','Vengalapuram','Viswanadhapuram'
]) AS v
WHERE mandals.name = 'Lingasamudram';

-- Gudluru
INSERT INTO villages (mandal_id, name)
SELECT id, v FROM mandals, UNNEST(ARRAY[
    'Ammavaripalem','Basireddypalem','Chevuru','Chinalatrapi','Dappalampadu',
    'Darakanipadu','Gudluru','Gundlapalem','Kothapeta','Mocherla',
    'Nayudupalem','Parakondapadu Agraharam','Parakondapadu','Potluru',
    'Puretipalle','Ravur','Swarnajipuram','Venkampeta'
]) AS v
WHERE mandals.name = 'Gudluru';

-- Ulavapadu
INSERT INTO villages (mandal_id, name)
SELECT id, v FROM mandals, UNNEST(ARRAY[
    'Atmakur','Baddepudi','Bheemavaram','Chagallu','Chaki Cherla',
    'K. Rajupalem','Karedu','Kollurupadu','Krishnapuram','Manneti Kota',
    'Ramayapatnam','Veerepalle'
]) AS v
WHERE mandals.name = 'Ulavapadu';

-- Voletivaripalem
INSERT INTO villages (mandal_id, name)
SELECT id, v FROM mandals, UNNEST(ARRAY[
    'Ayyavaripalle','Chundi','East Polineni Palem','Kakutur','Kalavalla',
    'Kondareddipalem','Kondasamudram','Naladalapur','Nawabpalem',
    'Nekunam Puram K.Kandrika','Nekunampuram @ Pokur','Nukavaram',
    'Polineni Cheruvu','Ramachandrapuram','Ramalingapuram','Sakhavaram',
    'Sameerapalem','Singamnenipalle','Veeranna Palem','Voletivaripalem',
    'Z. Uppalapadu'
]) AS v
WHERE mandals.name = 'Voletivaripalem';

-- Sanity check
-- SELECT m.name, COUNT(vl.id) AS village_count
-- FROM mandals m LEFT JOIN villages vl ON vl.mandal_id = m.id
-- GROUP BY m.name ORDER BY m.name;
