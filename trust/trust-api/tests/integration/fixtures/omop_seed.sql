-- Copyright (c) 2026 Guy's and St Thomas' NHS Foundation Trust & King's College London
-- Licensed under the Apache License, Version 2.0 (the "License");
-- you may not use this file except in compliance with the License.
-- You may obtain a copy of the License at
--     http://www.apache.org/licenses/LICENSE-2.0
-- Unless required by applicable law or agreed to in writing, software
-- distributed under the License is distributed on an "AS IS" BASIS,
-- WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
-- See the License for the specific language governing permissions and
-- limitations under the License.

-- Minimal OMOP fixture for trust-api / data-access-api integration tests (B3, issue #369).
-- Only the columns the cohort-query code path actually touches are modelled — kept small
-- so a regression in the SQL templates or in query plumbing is easy to diagnose. Counts
-- below are asserted directly in test_cohort_query.py; do not change without updating both.
--
-- Person totals: 16 rows. gender_source_value split: M 8, F 8.
--
-- Radiology totals: 24 rows. Distributions:
--   modality     -> CT 12, MR 8, XR 4
--   manufacturer -> GE 10, Siemens 8, Philips 4, Toshiba 2
-- Persons 1-12 each appear in radiology_occurrence (twice for persons 1-12; persons
-- 13-16 have no imaging — useful for joins that must drop those rows).

CREATE SCHEMA IF NOT EXISTS omop;

CREATE TABLE omop.person (
    person_id           BIGINT PRIMARY KEY,
    gender_concept_id   INTEGER,
    year_of_birth       INTEGER NOT NULL,
    birth_datetime      TIMESTAMP,
    gender_source_value VARCHAR(50),
    person_source_value VARCHAR(50)
);

CREATE TABLE omop.radiology_occurrence (
    radiology_occurrence_id BIGINT PRIMARY KEY,
    person_id               BIGINT NOT NULL REFERENCES omop.person(person_id),
    modality                VARCHAR(50),
    manufacturer            VARCHAR(100),
    accession_id            VARCHAR(50),
    protocol_source_value   VARCHAR(100)
);

INSERT INTO omop.person (person_id, gender_concept_id, year_of_birth, birth_datetime, gender_source_value, person_source_value) VALUES
    (1,  8507, 1948, '1948-03-15 00:00:00', 'M', 'P001'),
    (2,  8532, 1952, '1952-07-22 00:00:00', 'F', 'P002'),
    (3,  8507, 1958, '1958-01-10 00:00:00', 'M', 'P003'),
    (4,  8532, 1962, '1962-11-05 00:00:00', 'F', 'P004'),
    (5,  8507, 1968, '1968-08-30 00:00:00', 'M', 'P005'),
    (6,  8532, 1971, '1971-04-12 00:00:00', 'F', 'P006'),
    (7,  8507, 1974, '1974-09-25 00:00:00', 'M', 'P007'),
    (8,  8532, 1978, '1978-06-18 00:00:00', 'F', 'P008'),
    (9,  8507, 1982, '1982-12-03 00:00:00', 'M', 'P009'),
    (10, 8532, 1985, '1985-02-28 00:00:00', 'F', 'P010'),
    (11, 8507, 1988, '1988-10-14 00:00:00', 'M', 'P011'),
    (12, 8532, 1991, '1991-05-20 00:00:00', 'F', 'P012'),
    (13, 8507, 1994, '1994-03-08 00:00:00', 'M', 'P013'),
    (14, 8532, 1997, '1997-07-11 00:00:00', 'F', 'P014'),
    (15, 8507, 2000, '2000-11-29 00:00:00', 'M', 'P015'),
    (16, 8532, 2002, '2002-04-04 00:00:00', 'F', 'P016');

INSERT INTO omop.radiology_occurrence (radiology_occurrence_id, person_id, modality, manufacturer, accession_id, protocol_source_value) VALUES
    -- CT: 12 rows (5 GE, 4 Siemens, 2 Philips, 1 Toshiba)
    (1001, 1,  'CT', 'GE',      'ACC-1001', 'CT_HEAD'),
    (1002, 2,  'CT', 'GE',      'ACC-1002', 'CT_CHEST'),
    (1003, 3,  'CT', 'GE',      'ACC-1003', 'CT_ABDOMEN'),
    (1004, 4,  'CT', 'GE',      'ACC-1004', 'CT_PELVIS'),
    (1005, 5,  'CT', 'GE',      'ACC-1005', 'CT_HEAD'),
    (1006, 6,  'CT', 'Siemens', 'ACC-1006', 'CT_CHEST'),
    (1007, 7,  'CT', 'Siemens', 'ACC-1007', 'CT_ABDOMEN'),
    (1008, 8,  'CT', 'Siemens', 'ACC-1008', 'CT_HEAD'),
    (1009, 9,  'CT', 'Siemens', 'ACC-1009', 'CT_NECK'),
    (1010, 10, 'CT', 'Philips', 'ACC-1010', 'CT_HEAD'),
    (1011, 11, 'CT', 'Philips', 'ACC-1011', 'CT_THORAX'),
    (1012, 12, 'CT', 'Toshiba', 'ACC-1012', 'CT_HEAD'),
    -- MR: 8 rows (5 GE, 3 Siemens)
    (1013, 1,  'MR', 'GE',      'ACC-1013', 'MR_BRAIN'),
    (1014, 2,  'MR', 'GE',      'ACC-1014', 'MR_SPINE'),
    (1015, 3,  'MR', 'GE',      'ACC-1015', 'MR_BRAIN'),
    (1016, 4,  'MR', 'GE',      'ACC-1016', 'MR_KNEE'),
    (1017, 5,  'MR', 'GE',      'ACC-1017', 'MR_BRAIN'),
    (1018, 6,  'MR', 'Siemens', 'ACC-1018', 'MR_LIVER'),
    (1019, 7,  'MR', 'Siemens', 'ACC-1019', 'MR_BRAIN'),
    (1020, 8,  'MR', 'Siemens', 'ACC-1020', 'MR_SHOULDER'),
    -- XR: 4 rows (1 Siemens, 2 Philips, 1 Toshiba)
    (1021, 9,  'XR', 'Siemens', 'ACC-1021', 'XR_CHEST'),
    (1022, 10, 'XR', 'Philips', 'ACC-1022', 'XR_LIMB'),
    (1023, 11, 'XR', 'Philips', 'ACC-1023', 'XR_PELVIS'),
    (1024, 12, 'XR', 'Toshiba', 'ACC-1024', 'XR_CHEST');
