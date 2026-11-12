"""Print workbook links on the PDE index pages that are not in the catalog."""

from __future__ import annotations

from pa_edu.catalog import load_catalog
from pa_edu.common import ROOT, absolute_url, fetch_hrefs

PAGES = [
    "https://www.pa.gov/agencies/education/data-and-reporting/enrollment",
    "https://www.pa.gov/agencies/education/data-and-reporting/high-school-graduation",
    "https://www.pa.gov/agencies/education/programs-and-services/schools/grants-and-funding/school-finances/financial-data/general-fund-budget-gfb-data",
    "https://www.pa.gov/agencies/education/programs-and-services/schools/grants-and-funding/school-finances/financial-data/summary-of-annual-financial-report-data/afr-data-summary-level",
    "https://www.pa.gov/agencies/education/programs-and-services/schools/grants-and-funding/school-finances/financial-data/summary-of-annual-financial-report-data/afr-data-detailed",
    "https://www.pa.gov/agencies/education/data-and-reporting/assessment-reporting",
    "https://www.pa.gov/agencies/education/programs-and-services/schools/grants-and-funding/property-tax-relief/act-1-index",
    "https://www.pa.gov/agencies/education/programs-and-services/schools/grants-and-funding/school-finances/financial-data/financial-data-elements",
    "https://penndata.hbg.psu.edu/Additional-Reports",
]


def main() -> None:
    known = {entry.source_url.rstrip("/") for entry in load_catalog(ROOT / "sources" / "catalog.toml")}
    for page in PAGES:
        print(page)
        for href in fetch_hrefs(page):
            url = absolute_url(href).split("?", 1)[0]
            if not url.lower().endswith((".xls", ".xlsx", ".pdf")):
                continue
            if url.rstrip("/") in known:
                continue
            print(f"  {url}")


if __name__ == "__main__":
    main()
