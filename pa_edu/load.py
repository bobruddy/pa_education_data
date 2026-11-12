"""Download enrollment and budget data into data/pde.db."""

from __future__ import annotations

from pa_edu.budget import load_budget
from pa_edu.common import DB_PATH
from pa_edu.enrollment import load_enrollment
from pa_edu.personnel import load_personnel
from pa_edu.tuition import load_tuition


def main() -> None:
    load_enrollment()
    load_budget()
    load_tuition()
    load_personnel()
    print(f"wrote {DB_PATH}")


if __name__ == "__main__":
    main()
