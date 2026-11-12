"""Header maps for the professional personnel individual-staff workbooks.

PDE republishes the same 35 fields under different column names. Each school
year is assigned a layout here. A new file whose headers do not match its
year's layout fails the load instead of being guessed.

Headers are compared after stripping and collapsing internal whitespace, so
`FTE% ` and `School Location  Number` match the names below.
"""

from __future__ import annotations

CANONICAL_FIELDS = (
    "school_year_label",
    "snapshot_date",
    "public_id",
    "last_name",
    "first_name",
    "middle_name",
    "suffix",
    "gender",
    "race",
    "annual_salary",
    "degree_code",
    "degree_description",
    "years_in_education",
    "years_in_lea",
    "status",
    "aun",
    "lea_name",
    "lea_type",
    "county_code",
    "county",
    "school_number",
    "school_name",
    "iu_code",
    "iu_name",
    "time_status",
    "job_class",
    "primary_assignment",
    "assignment_code",
    "assignment_description",
    "position_code",
    "position_description",
    "edf_code",
    "edf_category",
    "category_description",
    "fte_percent",
)

# Published LEA type text, after whitespace is collapsed, to the short code
# used by the enrollment tables. Unlisted text is kept and left uncoded.
LEA_TYPE_CODES = {
    "school district": "SD",
    "charter school": "CS",
    "cyber charter school": "Cyber CS",
    "intermediate unit": "IU",
    "career and technical center": "CTC",
    "career and technical center ctc": "CTC",
    "state juvenile correctional inst": "SJCI",
    "approved private school": "APS",
    "private residential rehabilitation institution": "PRRI",
}


def _layout(pairs: list[tuple[str, str]]) -> dict[str, str]:
    mapping = dict(pairs)
    missing = [name for name in CANONICAL_FIELDS if name not in mapping.values()]
    extra = [name for name in mapping.values() if name not in CANONICAL_FIELDS]
    if missing or extra or len(mapping) != len(pairs):
        raise RuntimeError(f"bad personnel layout missing={missing} extra={extra}")
    return mapping


def compact_2007() -> dict[str, str]:
    """2007-08. Race is `Race/Ethnicity`. Primary assignment is unpublished."""
    return _layout([
        ("SY", "school_year_label"),
        ("Staff Snapshot Date", "snapshot_date"),
        ("PublicID", "public_id"),
        ("Last name", "last_name"),
        ("First Name", "first_name"),
        ("Middle Name", "middle_name"),
        ("Suffix", "suffix"),
        ("Gender", "gender"),
        ("Race/Ethnicity", "race"),
        ("AnnualSalary", "annual_salary"),
        ("DegreeCode", "degree_code"),
        ("DegreeDescription", "degree_description"),
        ("YearsInED", "years_in_education"),
        ("YearsInLEA", "years_in_lea"),
        ("Status", "status"),
        ("AUN", "aun"),
        ("LEAName", "lea_name"),
        ("LEATypeDescription", "lea_type"),
        ("LEACountyCd", "county_code"),
        ("LEACounty", "county"),
        ("SchNum", "school_number"),
        ("School", "school_name"),
        ("IU", "iu_code"),
        ("IUName", "iu_name"),
        ("FT/PT", "time_status"),
        ("JobClass", "job_class"),
        ("PrimaryAssignment", "primary_assignment"),
        ("AssignCd", "assignment_code"),
        ("Assignment Description", "assignment_description"),
        ("PosNum", "position_code"),
        ("PositionDesc", "position_description"),
        ("EDFNum", "edf_code"),
        ("EDF Category", "edf_category"),
        ("Category Description", "category_description"),
        ("FTE%", "fte_percent"),
    ])


def compact_2008() -> dict[str, str]:
    """2008-09 through 2011-12. Descriptions are abbreviated (`CategoryDesc`)."""
    return _layout([
        ("SY", "school_year_label"),
        ("Staff Snapshot Date", "snapshot_date"),
        ("PublicID", "public_id"),
        ("Last name", "last_name"),
        ("First Name", "first_name"),
        ("Middle Name", "middle_name"),
        ("Suffix", "suffix"),
        ("Gender", "gender"),
        ("Race", "race"),
        ("AnnualSalary", "annual_salary"),
        ("DegreeCode", "degree_code"),
        ("DegreeDescription", "degree_description"),
        ("YearsInED", "years_in_education"),
        ("YearsInLEA", "years_in_lea"),
        ("Status", "status"),
        ("AUN", "aun"),
        ("LEAName", "lea_name"),
        ("LEATypeDescription", "lea_type"),
        ("LEACountyCd", "county_code"),
        ("LEACounty", "county"),
        ("SchNum", "school_number"),
        ("School", "school_name"),
        ("IU", "iu_code"),
        ("IUName", "iu_name"),
        ("FT/PT", "time_status"),
        ("JobClass", "job_class"),
        ("PrimaryAssignment", "primary_assignment"),
        ("AssignCd", "assignment_code"),
        ("AssignmentDesc", "assignment_description"),
        ("PosNum", "position_code"),
        ("PositionDesc", "position_description"),
        ("EDFNum", "edf_code"),
        ("EDFCategory", "edf_category"),
        ("CategoryDesc", "category_description"),
        ("FTE%", "fte_percent"),
    ])


def spaced_2012() -> dict[str, str]:
    """2012-13 through 2016-17, and again in 2020-21, 2024-25, and 2025-26.

    School is `School Location Number`.
    """
    return _layout([
        ("SY", "school_year_label"),
        ("Staff Snapshot Date", "snapshot_date"),
        ("Public ID", "public_id"),
        ("Last Name", "last_name"),
        ("First Name", "first_name"),
        ("Middle Name", "middle_name"),
        ("Suffix", "suffix"),
        ("Gender", "gender"),
        ("Race With Description", "race"),
        ("Annual Salary", "annual_salary"),
        ("Degree Code", "degree_code"),
        ("Degree Description", "degree_description"),
        ("Years In ED", "years_in_education"),
        ("Years In LEA", "years_in_lea"),
        ("Status", "status"),
        ("AUN", "aun"),
        ("LEAName", "lea_name"),
        ("LEAType Description", "lea_type"),
        ("LEACounty Code", "county_code"),
        ("LEACounty", "county"),
        ("School Location Number", "school_number"),
        ("School", "school_name"),
        ("IU", "iu_code"),
        ("IUName", "iu_name"),
        ("FT/PT", "time_status"),
        ("Job Class", "job_class"),
        ("Primary Assignment", "primary_assignment"),
        ("Assign Code", "assignment_code"),
        ("Assignment Description", "assignment_description"),
        ("Position Number", "position_code"),
        ("Position Description", "position_description"),
        ("EDF Number", "edf_code"),
        ("EDF Category", "edf_category"),
        ("Category Description", "category_description"),
        ("FTE%", "fte_percent"),
    ])


def compact_2017() -> dict[str, str]:
    """2017-18 through 2019-20. Last name is capitalized; descriptions are abbreviated."""
    return _layout([
        ("SY", "school_year_label"),
        ("Staff Snapshot Date", "snapshot_date"),
        ("PublicID", "public_id"),
        ("Last Name", "last_name"),
        ("First Name", "first_name"),
        ("Middle Name", "middle_name"),
        ("Suffix", "suffix"),
        ("Gender", "gender"),
        ("Race", "race"),
        ("AnnualSalary", "annual_salary"),
        ("DegreeCode", "degree_code"),
        ("DegreeDescription", "degree_description"),
        ("YearsInED", "years_in_education"),
        ("YearsInLEA", "years_in_lea"),
        ("Status", "status"),
        ("AUN", "aun"),
        ("LEAName", "lea_name"),
        ("LEATypeDescription", "lea_type"),
        ("LEACountyCd", "county_code"),
        ("LEACounty", "county"),
        ("SchNum", "school_number"),
        ("School", "school_name"),
        ("IU", "iu_code"),
        ("IUName", "iu_name"),
        ("FT/PT", "time_status"),
        ("JobClass", "job_class"),
        ("PrimaryAssignment", "primary_assignment"),
        ("AssignCd", "assignment_code"),
        ("AssignmentDesc", "assignment_description"),
        ("PosNum", "position_code"),
        ("PositionDesc", "position_description"),
        ("EDFNum", "edf_code"),
        ("EDFCategory", "edf_category"),
        ("CategoryDesc", "category_description"),
        ("FTE%", "fte_percent"),
    ])


def compact_2021() -> dict[str, str]:
    """2021-22 only. Category column keeps the `2017-` suffix from the data dictionary."""
    return _layout([
        ("SY", "school_year_label"),
        ("Staff Snapshot Date", "snapshot_date"),
        ("PublicID", "public_id"),
        ("Last Name", "last_name"),
        ("First Name", "first_name"),
        ("Middle Name", "middle_name"),
        ("Suffix", "suffix"),
        ("Gender", "gender"),
        ("Race/Ethnicity", "race"),
        ("AnnualSalary", "annual_salary"),
        ("DegreeCode", "degree_code"),
        ("DegreeDescription", "degree_description"),
        ("YearsInED", "years_in_education"),
        ("YearsInLEA", "years_in_lea"),
        ("Status", "status"),
        ("AUN", "aun"),
        ("LEAName", "lea_name"),
        ("LEATypeDescription", "lea_type"),
        ("LEACountyCd", "county_code"),
        ("LEACounty", "county"),
        ("SchNum", "school_number"),
        ("School", "school_name"),
        ("IU", "iu_code"),
        ("IUName", "iu_name"),
        ("FT/PT", "time_status"),
        ("JobClass", "job_class"),
        ("Primary Assignment", "primary_assignment"),
        ("AssignCd", "assignment_code"),
        ("Assignment Description", "assignment_description"),
        ("PosNum", "position_code"),
        ("PositionDesc", "position_description"),
        ("EDFNum", "edf_code"),
        ("EDF Category", "edf_category"),
        ("Category Description 2017-", "category_description"),
        ("FTE%", "fte_percent"),
    ])


def compact_2022() -> dict[str, str]:
    """2022-23 only. Same abbreviated names as 2017-19, but race is `Race/Ethnicity`."""
    return _layout([
        ("SY", "school_year_label"),
        ("Staff Snapshot Date", "snapshot_date"),
        ("PublicID", "public_id"),
        ("Last Name", "last_name"),
        ("First Name", "first_name"),
        ("Middle Name", "middle_name"),
        ("Suffix", "suffix"),
        ("Gender", "gender"),
        ("Race/Ethnicity", "race"),
        ("AnnualSalary", "annual_salary"),
        ("DegreeCode", "degree_code"),
        ("DegreeDescription", "degree_description"),
        ("YearsInED", "years_in_education"),
        ("YearsInLEA", "years_in_lea"),
        ("Status", "status"),
        ("AUN", "aun"),
        ("LEAName", "lea_name"),
        ("LEATypeDescription", "lea_type"),
        ("LEACountyCd", "county_code"),
        ("LEACounty", "county"),
        ("SchNum", "school_number"),
        ("School", "school_name"),
        ("IU", "iu_code"),
        ("IUName", "iu_name"),
        ("FT/PT", "time_status"),
        ("JobClass", "job_class"),
        ("PrimaryAssignment", "primary_assignment"),
        ("AssignCd", "assignment_code"),
        ("AssignmentDesc", "assignment_description"),
        ("PosNum", "position_code"),
        ("PositionDesc", "position_description"),
        ("EDFNum", "edf_code"),
        ("EDFCategory", "edf_category"),
        ("CategoryDesc", "category_description"),
        ("FTE%", "fte_percent"),
    ])


def spaced_2023() -> dict[str, str]:
    """2023-24 only. Same spaced names as 2012, except the school column is `School Number`."""
    return _layout([
        ("SY", "school_year_label"),
        ("Staff Snapshot Date", "snapshot_date"),
        ("Public ID", "public_id"),
        ("Last Name", "last_name"),
        ("First Name", "first_name"),
        ("Middle Name", "middle_name"),
        ("Suffix", "suffix"),
        ("Gender", "gender"),
        ("Race With Description", "race"),
        ("Annual Salary", "annual_salary"),
        ("Degree Code", "degree_code"),
        ("Degree Description", "degree_description"),
        ("Years In ED", "years_in_education"),
        ("Years In LEA", "years_in_lea"),
        ("Status", "status"),
        ("AUN", "aun"),
        ("LEAName", "lea_name"),
        ("LEAType Description", "lea_type"),
        ("LEACounty Code", "county_code"),
        ("LEACounty", "county"),
        ("School Number", "school_number"),
        ("School", "school_name"),
        ("IU", "iu_code"),
        ("IUName", "iu_name"),
        ("FT/PT", "time_status"),
        ("Job Class", "job_class"),
        ("Primary Assignment", "primary_assignment"),
        ("Assign Code", "assignment_code"),
        ("Assignment Description", "assignment_description"),
        ("Position Number", "position_code"),
        ("Position Description", "position_description"),
        ("EDF Number", "edf_code"),
        ("EDF Category", "edf_category"),
        ("Category Description", "category_description"),
        ("FTE%", "fte_percent"),
    ])


LAYOUTS = {
    "compact_2007": compact_2007(),
    "compact_2008": compact_2008(),
    "spaced_2012": spaced_2012(),
    "compact_2017": compact_2017(),
    "compact_2021": compact_2021(),
    "compact_2022": compact_2022(),
    "spaced_2023": spaced_2023(),
}

# Every published year points at one layout. Add a year here when PDE posts a new file.
YEAR_LAYOUT = {
    2007: "compact_2007",
    2008: "compact_2008",
    2009: "compact_2008",
    2010: "compact_2008",
    2011: "compact_2008",
    2012: "spaced_2012",
    2013: "spaced_2012",
    2014: "spaced_2012",
    2015: "spaced_2012",
    2016: "spaced_2012",
    2017: "compact_2017",
    2018: "compact_2017",
    2019: "compact_2017",
    2020: "spaced_2012",
    2021: "compact_2021",
    2022: "compact_2022",
    2023: "spaced_2023",
    2024: "spaced_2012",
    2025: "spaced_2012",
}
