# Runtime and gaps

## Running now

The active rebuild is the refined pipeline:

```bash
python3.14 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
python -m pa_edu.refine
python -m pa_edu.check
python -m pa_edu.publish   # builds pde_site/ and rsyncs to elm → https://pdenumbers.org
```

As of November 2026 the PDE pages from 2021 no longer point at the workbooks. Catalog URLs in `sources/catalog.toml` target the current `pa.gov` paths. `pa.gov` returns 403 without the project User-Agent in `pa_edu.common.HEADERS`.

The older SQLite path still works for local Dash / personnel work: `python -m pa_edu.load` writes `data/pde.db`, and `python -m pa_edu.app` serves http://127.0.0.1:8050. Docker and Jenkins are unchanged and are not how the live site is built.

The rest of this page describes the 2021–2022 notebooks and images.

# Original runtime and gaps

## Development image

`docker_files/development/`

`Dockerfile` is `alpine:edge`. It copies the directory to `/build`, runs `install.sh`, sets workdir `/working`, and starts:

```text
jupyter notebook --port=8888 --no-browser --ip=0.0.0.0 --allow-root
```

`install.sh` upgrades Alpine, installs git, vim, a C toolchain, Python 3, pandas, BeautifulSoup, and pyzmq from apk, then `pip3 install -r requirements.txt`. The toolchain and Python headers are removed after the pip install. A commented-out `git clone` of this repo is at the bottom; the image expects the repo to be mounted in.

`requirements.txt` (no pins): `jupyter`, `openpyxl`, `plotly`, `runipy`, `numpy`, `pandas`.

The README in that directory is stale. It says:

```text
docker build -t pa_education .
docker run -p 8888:8888 -v "${PWD}":/home/jovyan/work pa_education
```

That mount path is from the old Jupyter Docker stack (`jovyan`). The image was ported to Alpine on 8 Dec 2021 specifically to shrink it ("1/5 of the size") and to get a Python newer than Alpine 3.5.5, because pickle misbehaved on 3.5.5. The Dockerfile workdir is `/working`, and nothing in the image creates `/home/jovyan`. Ports 8080 and 8050 are declared and unused. Jupyter listens on 8888, which is not in the `EXPOSE` list.

A mount that matches the Dockerfile:

```text
docker build -t pa_education -f docker_files/development/Dockerfile docker_files/development
docker run -p 8888:8888 -v "${PWD}":/working pa_education
```

The notebook paths (`../data/...`, `../lookup_data/...`) assume the kernel's working directory is `data_acquisition/` or `analysis/`. Jupyter's initial directory is `/working`. Start the kernel in the notebook's folder, or the relative paths miss `lookup_data` and `data`.

`runipy` is installed and never called. It looks like a planned way to execute notebooks headlessly.

## Production image and Jenkins

`docker_files/production/` is the same Alpine install minus vim, the C toolchain, and Jupyter. `requirements.txt` drops `jupyter` and keeps `openpyxl`, `plotly`, `runipy`, `numpy`, `pandas`.

`install.sh` clones `https://github.com/bobruddy/pa_education_data.git` into `/project/pa_education_data` at image build time. `CMD` is `/bin/sh -l`. Nothing runs the notebooks.

`Jenkinsfile` on any agent:

1. `docker build -t w3rcr/batch_test -f docker_files/production/Dockerfile docker_files/production`
2. Echo `Your test steps...`
3. `docker push w3rcr/batch_test`

The tag (`w3rcr/batch_test`) does not match the README tag (`pa_education`). Build context is only `docker_files/production/`, which is correct because the Dockerfile copies that directory and then clones the repo. The image therefore contains whatever `main` was on GitHub at build time, not the Jenkins workspace.

## Static web image

`docker_files/static_web/Dockerfile` is `FROM nginx` plus `COPY . /usr/share/nginx/html`. There is no HTML, CSS, or config next to it. It was never wired to the Dash app.

## Python libraries the notebooks actually import

| Library | Where it comes from | Used by |
| --- | --- | --- |
| pandas, numpy | requirements and apk | all three notebooks |
| openpyxl | requirements | Excel reads, via pandas |
| requests | not declared | both acquisition notebooks |
| beautifulsoup4 | `apk add py3-beautifulsoup4` | both acquisition notebooks |
| sqlite3 | stdlib | all three notebooks |
| plotly | requirements | analysis |
| dash, jupyter_dash, dash_bootstrap_components | not declared | analysis |

`requests` may have been present in the 2021 environment by accident. A clean install of the current requirements file will not provide it. Dash will not be there either.

The analysis notebook's traceback shows a host Python 3.10 at `/Library/Frameworks/Python.framework/Versions/3.10/`, so the last chart work happened on the Mac, not in the container.

## Known unfinished work

From the notebooks' own todos, plus what the code does:

**Enrollment**

- Comments and a cleanup pass, called out at the top of the notebook.
- 2004–2006 still commented out (`lea_type` and `aun`).
- `LEA Type` backfill reads `df` instead of `df1`.
- `school_info` dedupes on `school_number` alone.

**Budget**

- Loop stops after five files.
- Years before 2011 have no sheet-name handling.
- `lea_type` is not on `finance_expense`; the notebook todo still wants a district dimension. `lea_info` is that dimension, if enrollment has been loaded.
- Lookup names include typos (`Edecation`, `Transrers`, `Transfers - Ou`).
- Account codes that show up in a future workbook and are missing from the CSV pass through with null names.

**Analysis**

- `build_sunburst` is defined below `run_server`.
- Scatter uses an undefined `cnx`.
- Year is fixed at 2020.
- Object-500 exclusion is only on the scatter.
- Dash stack is not in either requirements file.
- No year, grade, or category controls beyond county and LEA.

**Runtime**

- Dev README mount path does not match the Dockerfile.
- Production image clones the repo and then opens a shell. `runipy` is unused. Jenkins has no test.
- `w3rcr/batch_test` vs `pa_education`.
- `data/` is gitignored, so a fresh clone has no `pde.db` until both notebooks have been run.
- `.gitignore` ignores `docs/_build/` (Sphinx template). It does not ignore this `docs/` folder.

## Suggested order when picking this up

1. Decide whether notebooks stay the interface or the logic moves into importable modules. Right now a fix has to be made twice, because the cache and download helpers are duplicated.
2. Pin a current Python and write one requirements file that includes `requests`, `beautifulsoup4`, `dash`, and whatever replaces `jupyter_dash` (`Dash` runs inside Jupyter without that package now).
3. Re-check the two PDE index URLs. They are the only discovery mechanism. A redesigned PDE page returns no files and the notebooks fail quietly (`Error: not able to download`).
4. Remove the `count < 5` cap, fix the `df` / `df1` LEA-type bug, and confirm 2007–present sheet names still match.
5. Load enrollment, then budget, then point the chart at a year that exists in both tables.
