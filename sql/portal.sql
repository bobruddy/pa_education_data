-- Useful views on top of the refined tables.
-- Each block is one view. publish and the download portal read the markers.

-- view: school_district
-- needs: lea
-- about: School districts on the EdNA directory, open and closed.

CREATE OR REPLACE VIEW school_district AS
SELECT *
FROM lea
WHERE category = 'school_district';

-- view: afr_general_fund
-- needs: afr_expenditure
-- about: Annual Financial Report expenditures in the general fund (fund 10).

CREATE OR REPLACE VIEW afr_general_fund AS
SELECT *
FROM afr_expenditure
WHERE fund_code = '10';

-- view: enrollment_headcount
-- needs: enrollment
-- about: Sum of published grade cells for one AUN, school number, and year.

CREATE OR REPLACE VIEW enrollment_headcount AS
SELECT
    aun,
    school_number,
    school_year,
    any_value(school_name) AS school_name,
    any_value(lea_name) AS lea_name,
    any_value(lea_type) AS lea_type,
    any_value(county) AS county,
    sum(enrollment) AS enrollment
FROM enrollment
GROUP BY aun, school_number, school_year;

-- view: gfb_line
-- needs: gfb_expenditure, lea, account
-- about: Each General Fund Budget amount with the directory name and chart-of-accounts labels.

CREATE OR REPLACE VIEW gfb_line AS
SELECT
    g.aun,
    l.lea_name,
    l.county,
    l.category,
    g.school_year,
    g.function_code,
    a.function_name,
    g.object_code,
    a.object_name,
    g.program_code,
    g.amount,
    g.fund_code,
    g.document_id
FROM gfb_expenditure AS g
LEFT JOIN lea AS l ON g.aun = l.aun
LEFT JOIN account AS a
    ON g.function_code = a.function_code
   AND g.object_code = a.object_code;

-- view: afr_general_fund_line
-- needs: afr_general_fund, lea, account
-- about: Each general-fund actual with the directory name and chart-of-accounts labels.

CREATE OR REPLACE VIEW afr_general_fund_line AS
SELECT
    e.aun,
    l.lea_name,
    l.county,
    l.category,
    e.school_year,
    e.fund_code,
    e.function_code,
    a.function_name,
    e.object_code,
    a.object_name,
    e.program_code,
    e.elementary_amount,
    e.secondary_amount,
    e.federal_amount,
    e.total_amount,
    e.document_id
FROM afr_general_fund AS e
LEFT JOIN lea AS l ON e.aun = l.aun
LEFT JOIN account AS a
    ON e.function_code = a.function_code
   AND e.object_code = a.object_code;

-- view: assessment_all_students
-- needs: assessment_result
-- about: PSSA and Keystone rows for the All Students group.

CREATE OR REPLACE VIEW assessment_all_students AS
SELECT *
FROM assessment_result
WHERE student_group = 'All Students';

-- view: assessment_lea
-- needs: assessment_result, assessment_result_school, lea
-- about: One assessment row per LEA. A school district keeps the district workbook. Any other LEA is copied from its single school row that year.

CREATE OR REPLACE VIEW assessment_lea AS
WITH school_count AS (
    SELECT aun, school_year, count(DISTINCT school_number) AS schools
    FROM assessment_result_school
    GROUP BY aun, school_year
)
SELECT
    r.aun,
    r.school_year,
    r.assessment,
    CAST(NULL AS VARCHAR) AS school_number,
    CAST(NULL AS VARCHAR) AS school_name,
    r.subject,
    r.grade,
    r.student_group,
    r.number_scored,
    r.pct_advanced,
    r.pct_proficient,
    r.pct_basic,
    r.pct_below_basic,
    r.pct_proficient_and_above,
    r.lea_name,
    r.county,
    l.category,
    r.document_id
FROM assessment_result AS r
INNER JOIN lea AS l ON r.aun = l.aun
WHERE l.category = 'school_district'
UNION ALL
SELECT
    s.aun,
    s.school_year,
    s.assessment,
    s.school_number,
    s.school_name,
    s.subject,
    s.grade,
    s.student_group,
    s.number_scored,
    s.pct_advanced,
    s.pct_proficient,
    s.pct_basic,
    s.pct_below_basic,
    s.pct_proficient_and_above,
    s.lea_name,
    s.county,
    l.category,
    s.document_id
FROM assessment_result_school AS s
INNER JOIN lea AS l ON s.aun = l.aun
INNER JOIN school_count AS n
    ON s.aun = n.aun
   AND s.school_year = n.school_year
WHERE l.category <> 'school_district'
  AND n.schools = 1;
