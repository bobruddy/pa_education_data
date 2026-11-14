CREATE OR REPLACE VIEW document AS
SELECT * FROM read_parquet('data/refined/document.parquet');

CREATE OR REPLACE VIEW lea AS
SELECT * FROM read_parquet('data/refined/lea.parquet');

CREATE OR REPLACE VIEW lea_year AS
SELECT * FROM read_parquet('data/refined/lea_year.parquet');

CREATE OR REPLACE VIEW school AS
SELECT * FROM read_parquet('data/refined/school.parquet');

CREATE OR REPLACE VIEW grade AS
SELECT * FROM read_parquet('data/refined/grade.parquet');

CREATE OR REPLACE VIEW account AS
SELECT * FROM read_parquet('data/refined/account.parquet');

CREATE OR REPLACE VIEW gfb_expenditure AS
SELECT * FROM read_parquet('data/refined/gfb_expenditure.parquet');

CREATE OR REPLACE VIEW afr_expenditure AS
SELECT * FROM read_parquet('data/refined/afr_expenditure.parquet');

CREATE OR REPLACE VIEW afr_expenditure_school AS
SELECT * FROM read_parquet('data/refined/afr_expenditure_school.parquet');

CREATE OR REPLACE VIEW afr_revenue AS
SELECT * FROM read_parquet('data/refined/afr_revenue.parquet');

CREATE OR REPLACE VIEW gfb_revenue AS
SELECT * FROM read_parquet('data/refined/gfb_revenue.parquet');

CREATE OR REPLACE VIEW revenue_account AS
SELECT * FROM read_parquet('data/refined/revenue_account.parquet');

CREATE OR REPLACE VIEW chart_description AS
SELECT * FROM read_parquet('data/refined/chart_description.parquet');

CREATE OR REPLACE VIEW enrollment AS
SELECT * FROM read_parquet('data/refined/enrollment.parquet');

CREATE OR REPLACE VIEW enrollment_gender AS
SELECT * FROM read_parquet('data/refined/enrollment_gender.parquet');

CREATE OR REPLACE VIEW enrollment_race AS
SELECT * FROM read_parquet('data/refined/enrollment_race.parquet');

CREATE OR REPLACE VIEW enrollment_low_income AS
SELECT * FROM read_parquet('data/refined/enrollment_low_income.parquet');

CREATE OR REPLACE VIEW enrollment_iep AS
SELECT * FROM read_parquet('data/refined/enrollment_iep.parquet');

CREATE OR REPLACE VIEW assessment_result AS
SELECT * FROM read_parquet('data/refined/assessment_result.parquet');

CREATE OR REPLACE VIEW act1_index AS
SELECT * FROM read_parquet('data/refined/act1_index.parquet');

CREATE OR REPLACE VIEW act1_base AS
SELECT * FROM read_parquet('data/refined/act1_base.parquet');

CREATE OR REPLACE VIEW real_estate_tax AS
SELECT * FROM read_parquet('data/refined/real_estate_tax.parquet');

CREATE OR REPLACE VIEW charter_adm AS
SELECT * FROM read_parquet('data/refined/charter_adm.parquet');

CREATE OR REPLACE VIEW home_education AS
SELECT * FROM read_parquet('data/refined/home_education.parquet');

CREATE OR REPLACE VIEW cohort_graduation AS
SELECT * FROM read_parquet('data/refined/cohort_graduation.parquet');

CREATE OR REPLACE VIEW cohort_graduation_group AS
SELECT * FROM read_parquet('data/refined/cohort_graduation_group.parquet');

CREATE OR REPLACE VIEW professional_assignment AS
SELECT * FROM read_parquet('data/refined/professional_assignment.parquet');

CREATE OR REPLACE VIEW professional_staff AS
SELECT * FROM read_parquet('data/refined/professional_staff.parquet');

CREATE OR REPLACE VIEW afr_general_fund AS
SELECT * FROM afr_expenditure WHERE fund_code = '10';
