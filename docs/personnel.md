# Personnel salaries

> Still used for the Staff tab on the site, but loaded through the SQLite path (`python -m pa_edu.personnel`), not yet a refined Parquet family. New finance / enrollment / assessment sources should not copy this pattern — use [`refined-pipeline.md`](refined-pipeline.md).


`python -m pa_edu.personnel` downloads the individual professional-staff workbooks and writes two tables in `data/pde.db`.

Source page: [Professional and Support Personnel](https://www.pa.gov/agencies/education/data-and-reporting/school-staff/professional-and-support-personnel). Files are cached in `data/raw/personnel/`. The notes workbook and the assignment-code crosswalk are not loaded. Support staff are not in these files; PDE publishes those only as counts.

## Tables

`professional_assignment` is one row per person, LEA, school year, and assignment. `annual_salary` is the person's total pay at that LEA and is copied onto every assignment. Summing it on this table double-counts people who hold more than one assignment.

`professional_staff` is one row per `public_id`, `aun`, and `school_year`. Salary can be summed here. `row_rule` is `primary_assignment` when PDE marked a primary row, and `highest_fte` when they did not. `assignment_count` is how many assignment rows were collapsed.

Through 2014-15 the primary-assignment column is present and empty, so those years use `highest_fte`. From 2015-16 on, PDE fills Yes or No. A few people have two rows marked Yes, and a few have none; the person table still keeps one row, preferring a Yes and then the highest FTE.

`public_id` is PDE's stable person id, stored as text, including the negative ids in the files. `school_year` is the four-digit start year. `fte_percent` is the published percent (`100` is full time). `source_layout` and `source_file` record which header map and workbook produced the row.

`lea_type` is the published label. `lea_type_code` is the short code used elsewhere in this database (`SD`, `CS`, `IU`, `CTC`, `SJCI`, `APS`, `PRRI`) when the label is one of those. An unrecognized label is kept and `lea_type_code` is left null; the load prints it. Cyber charters are published as Charter School in these files, so they are `CS` here. `lea_info.lea_type` is where `Cyber CS` is distinguished; join on `aun`.

## Year layouts

The column names change. Each year is listed in `pa_edu/personnel_layouts.py`. A file whose headers do not match that year's layout stops the load.

| Years | Layout | What is different |
| --- | --- | --- |
| 2007 | `compact_2007` | `Race/Ethnicity`, `Category Description` |
| 2008–2011 | `compact_2008` | `Race`, `CategoryDesc` |
| 2012–2016, 2020, 2024–2025 | `spaced_2012` | Spaced names, school column is `School Location Number` |
| 2017–2019 | `compact_2017` | Abbreviated names, `Last Name` |
| 2021 | `compact_2021` | Category column is `Category Description 2017-` |
| 2022 | `compact_2022` | Abbreviated names, race is `Race/Ethnicity` |
| 2023 | `spaced_2023` | Spaced names, school column is `School Number` |
