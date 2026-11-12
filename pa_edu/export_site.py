"""Write the chart as static files for elm's existing nginx.

`python -m pa_edu.export_site` writes `site/`. Copy that directory to
`/data/elm/htdocs/agsd_data/` on elm. nginx already serves that tree at
https://elm.o4x.net/agsd_data/.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pandas as pd

from pa_edu.chart import (
    MEASURE_PER_PUPIL,
    MEASURE_TOTAL,
    apply_measure,
    counties,
    expense_frame,
    leas,
    selection_summary,
    tuition_years,
    years,
)

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "site"
PLOTLY_JS = Path(__file__).resolve().parents[1] / ".venv" / "lib"

PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>PA school spending</title>
<script src="plotly.min.js"></script>
<style>
  body { margin: 0; font: 16px/1.45 system-ui, sans-serif; color: #1c1917; background: #fafaf9; }
  main { max-width: 1100px; margin: 0 auto; padding: 24px 20px 48px; }
  h1 { font-size: 1.8rem; margin: 0 0 8px; }
  p { margin: 0 0 12px; }
  .controls { display: grid; grid-template-columns: 1fr 1fr 2fr; gap: 16px; margin: 16px 0; }
  label.field { display: block; font-size: 0.9rem; }
  select { width: 100%; margin-top: 4px; font: inherit; }
  .leas { margin-top: 4px; max-height: 220px; overflow: auto; background: #fff; border: 1px solid #d6d3d1; border-radius: 6px; padding: 6px 8px; }
  .leas label { display: block; font-size: 0.92rem; }
  .row-actions { display: flex; gap: 8px; margin-top: 6px; }
  button { font: inherit; }
  #summary { min-height: 3em; }
  #status { color: #57534e; }
  @media (max-width: 800px) { .controls { grid-template-columns: 1fr; } }
</style>
</head>
<body>
<main>
  <h1>PA school spending</h1>
  <p>General Fund Budget amounts. Per pupil removes tuition paid to brick-and-mortar and cyber charters, including special-education charter tuition, because those students are in the charter's enrollment. Tuition for approved private schools and PRRIs stays in: those students remain in the district count.</p>
  <div>
    <span>View</span>
    <label><input type="radio" name="measure" value="total"> All expenses</label>
    <label><input type="radio" name="measure" value="per_pupil" checked> Per pupil</label>
  </div>
  <div class="controls">
    <label class="field">School year
      <select id="year"></select>
    </label>
    <label class="field">County
      <select id="county"></select>
    </label>
    <div>
      <span>LEA</span>
      <div id="leas" class="leas"></div>
      <div class="row-actions">
        <button type="button" id="all">All</button>
        <button type="button" id="none">None</button>
      </div>
    </div>
  </div>
  <p id="summary"></p>
  <p id="status"></p>
  <div id="chart"></div>
</main>
<script>
const META = __META__;
const palette = ["#636EFA","#EF553B","#00CC96","#AB63FA","#FFA15A","#19D3F3","#FF6692","#B6E880","#FF97FF","#FECB52"];
const plotConfig = {responsive: true, showSendToCloud: false};
const cache = new Map();
let pack = null;
const opening = new URLSearchParams(location.search);

const yearEl = document.querySelector("#year");
const countyEl = document.querySelector("#county");
const leaEl = document.querySelector("#leas");
const summaryEl = document.querySelector("#summary");
const statusEl = document.querySelector("#status");

function money(value) {
  return "$" + Math.round(value).toLocaleString("en-US");
}

function yearLabel(year) {
  const n = Number(year);
  return n + "-" + String(n + 1).slice(-2);
}

function fill(select, values, selected, labeler) {
  select.replaceChildren();
  for (const value of values) {
    const option = document.createElement("option");
    option.value = String(value);
    option.textContent = labeler(value);
    option.selected = String(value) === String(selected);
    select.appendChild(option);
  }
}

async function loadCounty(name) {
  if (!cache.has(name)) {
    const response = await fetch("data/" + encodeURIComponent(name) + ".json");
    if (!response.ok) throw new Error("Could not load " + name);
    cache.set(name, await response.json());
  }
  return cache.get(name);
}

function checkedNames() {
  return [...leaEl.querySelectorAll("input:checked")].map((box) => box.value);
}

function renderLeas(wanted) {
  const rows = pack.y[yearEl.value] || [];
  const chosen = wanted ? new Set(wanted) : null;
  leaEl.replaceChildren();
  for (const lea of rows) {
    const name = pack.s[lea.n];
    const label = document.createElement("label");
    const box = document.createElement("input");
    box.type = "checkbox";
    box.value = name;
    box.checked = chosen ? chosen.has(name) : true;
    label.append(box, document.createTextNode(" " + name));
    leaEl.appendChild(label);
  }
}

function writeParams() {
  const params = new URLSearchParams();
  params.set("year", yearEl.value);
  params.set("county", countyEl.value);
  params.set("measure", document.querySelector('input[name="measure"]:checked').value);
  const boxes = [...leaEl.querySelectorAll("input")];
  const checked = boxes.filter((box) => box.checked).map((box) => box.value);
  if (boxes.length && checked.length === 0) params.append("lea", "");
  else if (checked.length !== boxes.length) {
    for (const name of checked) params.append("lea", name);
  }
  const query = params.toString();
  const next = location.pathname + (query ? "?" + query : "");
  if (next !== location.pathname + location.search) history.replaceState(null, "", next);
}

function setChecks(on) {
  for (const box of leaEl.querySelectorAll("input")) box.checked = on;
  draw();
}

function draw() {
  writeParams();
  const year = yearEl.value;
  const measure = document.querySelector('input[name="measure"]:checked').value;
  const tuition = META.tuitionYears.includes(Number(year));
  const chosen = new Set(checkedNames());
  const rows = (pack.y[year] || []).filter((lea) => chosen.has(pack.s[lea.n]));
  const label = yearLabel(year);
  const per = measure === "per_pupil";
  const title = per
    ? "Per pupil, charter tuition removed, " + label
    : "All district expenses, " + label;
  const layout = {title, height: 720, margin: {t: 48, l: 8, r: 8, b: 8}};

  if (per && !tuition) {
    summaryEl.textContent = "";
    statusEl.textContent = label + ": charter tuition actuals are not published for this year yet";
    Plotly.react("chart", [], {title: statusEl.textContent, height: 240, margin: layout.margin}, plotConfig);
    return;
  }

  let total = 0;
  let charter = 0;
  let sped = 0;
  let enrollment = 0;
  for (const lea of rows) {
    total += lea.x;
    enrollment += lea.e;
    if (lea.k === "SD") {
      charter += lea.c[0] + lea.c[1];
      sped += lea.c[2] + lea.c[3];
    }
  }

  if (!rows.length) {
    summaryEl.textContent = "No expenses for this selection.";
  } else if (!tuition) {
    summaryEl.textContent = "Total expenses " + money(total) + ". Charter tuition and special-education tuition are not split out until the AFR tuition schedule is published.";
  } else if (!enrollment) {
    summaryEl.textContent = "Total expenses " + money(total) + ". Charter tuition in that total " + money(charter) + ". Special education tuition kept " + money(sped) + " (approved private schools and PRRIs). Per pupil is not available until the AFR tuition schedule is published.";
  } else {
    summaryEl.textContent = "Total expenses " + money(total) + ". Charter tuition in that total " + money(charter) + ". Special education tuition kept " + money(sped) + " (approved private schools and PRRIs). Per pupil " + money((total - charter) / enrollment) + " on " + Math.round(enrollment).toLocaleString("en-US") + " enrolled students, after removing charter tuition.";
  }
  statusEl.textContent = "";

  const colors = new Map();
  const names = new Set();
  for (const lea of rows) {
    for (const row of lea.r) {
      const value = per ? row[4] : row[3];
      if (value) names.add(pack.s[row[0]]);
    }
  }
  [...names].sort().forEach((name, index) => colors.set(name, palette[index % palette.length]));

  const ids = [];
  const labels = [];
  const parents = [];
  const values = [];
  const marker = [];
  const custom = [];
  const sep = "\\u001f";

  function add(id, text, parent, color) {
    ids.push(id);
    labels.push(text);
    parents.push(parent);
    values.push(0);
    marker.push(color);
    custom.push([0, 0, 0, 0, ""]);
  }

  function absorb(index, slice, expense, amountUsed, charterRemoved, enrollment, code) {
    values[index] += slice;
    const item = custom[index];
    item[0] += expense;
    item[1] += amountUsed;
    item[2] += charterRemoved;
    item[3] = enrollment;
    if (!item[4]) item[4] = code;
    else if (item[4] !== code) item[4] = "(?)";
  }

  for (const lea of rows) {
    const leaName = pack.s[lea.n];
    add(leaName, leaName, "", "#d9d9d9");
    const seen = new Map([[leaName, ids.length - 1]]);
    for (const row of lea.r) {
      const expense = row[3];
      const slice = per ? row[4] : expense;
      if (!slice) continue;
      const amountUsed = per ? (row[6] || 0) : expense;
      const charterRemoved = per ? (row[7] || 0) : 0;
      const code = row.length > 5 ? pack.s[row[5]] : "";
      const parts = [leaName, pack.s[row[0]], pack.s[row[1]], pack.s[row[2]]];
      const color = colors.get(parts[1]) || palette[0];
      let parent = leaName;
      const path = [seen.get(leaName)];
      for (let depth = 1; depth < parts.length; depth += 1) {
        const id = parts.slice(0, depth + 1).join(sep);
        if (!seen.has(id)) {
          add(id, parts[depth], parent, color);
          seen.set(id, ids.length - 1);
        }
        path.push(seen.get(id));
        parent = id;
      }
      for (const index of path) absorb(index, slice, expense, amountUsed, charterRemoved, lea.e, code);
    }
  }

  const referenced = new Set(parents);
  const keep = ids.map((id, index) => parents[index] !== "" || referenced.has(id));
  const take = (items) => items.filter((_, index) => keep[index]);
  const keptValues = take(values);
  if (!keptValues.some((value) => value > 0)) {
    Plotly.react("chart", [], {title: title + ": no rows for this selection", height: 240, margin: layout.margin}, plotConfig);
    return;
  }
  const keptLabels = take(labels);
  const keptCustom = take(custom);
  const hovertext = keptLabels.map((text, index) => {
    const item = keptCustom[index];
    return [
      text,
      "slice_value=" + Math.round(keptValues[index]).toLocaleString("en-US"),
      "expense_value=" + Math.round(item[0]).toLocaleString("en-US"),
      "amount_used=" + Math.round(item[1]).toLocaleString("en-US"),
      "charter_removed=" + Math.round(item[2]).toLocaleString("en-US"),
      "enrollment=" + Math.round(item[3]).toLocaleString("en-US"),
      "expense_category=" + (item[4] || "(?)"),
    ].join("<br>");
  });
  Plotly.react("chart", [{
    type: "sunburst",
    ids: take(ids),
    labels: keptLabels,
    parents: take(parents),
    values: keptValues,
    branchvalues: "total",
    marker: {colors: take(marker), line: {color: "#ffffff", width: 1}},
    customdata: keptCustom,
    hovertext,
    hovertemplate: "%{hovertext}<extra></extra>",
  }], Object.assign({}, layout, {hoverlabel: {bgcolor: "#fff", font: {size: 13}}}), plotConfig);
}

async function show(wanted) {
  statusEl.textContent = "Loading…";
  pack = await loadCounty(countyEl.value);
  renderLeas(wanted);
  draw();
}

const startYear = META.years.map(String).includes(opening.get("year")) ? opening.get("year") : META.defaultYear;
const startCounty = META.counties.includes(opening.get("county")) ? opening.get("county") : META.defaultCounty;
const startMeasure = opening.get("measure") === "total" ? "total" : "per_pupil";
document.querySelector('input[name="measure"][value="' + startMeasure + '"]').checked = true;
fill(yearEl, META.years, startYear, yearLabel);
fill(countyEl, META.counties, startCounty, (name) => name);
yearEl.addEventListener("change", () => show(null));
countyEl.addEventListener("change", () => show(null));
leaEl.addEventListener("change", draw);
document.querySelectorAll('input[name="measure"]').forEach((input) => input.addEventListener("change", draw));
document.querySelector("#all").addEventListener("click", () => setChecks(true));
document.querySelector("#none").addEventListener("click", () => setChecks(false));
show(opening.has("lea") ? opening.getAll("lea").filter(Boolean) : null).catch((error) => {
  statusEl.textContent = error.message;
});
</script>
</body>
</html>
"""


class _Strings:
    def __init__(self) -> None:
        self.ids: dict[str, int] = {}
        self.values: list[str] = []

    def add(self, text: str) -> int:
        index = self.ids.get(text)
        if index is None:
            index = len(self.values)
            self.ids[text] = index
            self.values.append(text)
        return index


def _text(value: object) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return "—"
    text = str(value).strip()
    return text or "—"


def _money(value: float) -> float:
    return round(float(value), 2)


def _labeled(frame: pd.DataFrame) -> pd.DataFrame:
    return frame.assign(
        a=frame["expense_category_name_0"].map(_text),
        b=frame["expense_category_name_1"].map(_text),
        c=frame["expense_category_name_2"].map(_text),
    )


def _grouped(frame: pd.DataFrame, column: str) -> pd.Series:
    if frame.empty:
        return pd.Series(dtype=float)
    return _labeled(frame).groupby(["lea_name", "a", "b", "c"], dropna=False)[column].sum()


def _grouped_first(frame: pd.DataFrame, column: str) -> pd.Series:
    if frame.empty:
        return pd.Series(dtype=object)
    return _labeled(frame).groupby(["lea_name", "a", "b", "c"], dropna=False)[column].first()


def _county_payload(county: str, available_years: list[int], published: set[int]) -> dict:
    strings = _Strings()
    by_year: dict[str, list[dict]] = {}
    for school_year in available_years:
        names = leas(county, school_year)
        if not names:
            continue
        raw = expense_frame(county, names, school_year)
        if raw.empty:
            continue
        ready = school_year in published
        expenses = _grouped(raw, "expense_value")
        codes = _grouped_first(raw, "expense_category")
        per_frame = apply_measure(raw, MEASURE_PER_PUPIL) if ready else None
        per = _grouped(per_frame, "slice_value") if per_frame is not None else None
        used = _grouped(per_frame, "amount_used") if per_frame is not None else None
        removed = _grouped(per_frame, "charter_removed") if per_frame is not None else None
        rows_for: dict[str, list[list]] = {name: [] for name in names}
        for key, expense in expenses.items():
            lea_name, cat0, cat1, cat2 = key
            if lea_name not in rows_for or expense <= 0:
                continue
            per_value = None
            used_value = None
            removed_value = None
            if per is not None and key in per.index and float(per.loc[key]) > 0:
                per_value = round(float(per.loc[key]), 4)
                used_value = _money(used.loc[key]) if key in used.index else 0
                removed_value = _money(removed.loc[key]) if key in removed.index else 0
            code = _text(codes.loc[key]) if key in codes.index else ""
            rows_for[lea_name].append(
                [
                    strings.add(cat0),
                    strings.add(cat1),
                    strings.add(cat2),
                    _money(expense),
                    per_value,
                    strings.add(code),
                    used_value,
                    removed_value,
                ]
            )
        lea_rows = []
        ordered = raw.groupby("lea_name", sort=False)
        for lea_name in names:
            if lea_name not in ordered.groups:
                continue
            block = ordered.get_group(lea_name)
            one = block.drop_duplicates("aun")
            district = block["lea_type"].iloc[0] == "SD"
            charter = one[["charter_nonspecial", "charter_special", "sped_aps", "sped_prri"]].sum()
            lea_rows.append(
                {
                    "n": strings.add(lea_name),
                    "k": "SD" if district else str(block["lea_type"].iloc[0]),
                    "e": _money(one["enrollment"].sum()),
                    "x": _money(block["expense_value"].sum()),
                    "c": [
                        _money(charter["charter_nonspecial"]) if district else 0,
                        _money(charter["charter_special"]) if district else 0,
                        _money(charter["sped_aps"]) if district else 0,
                        _money(charter["sped_prri"]) if district else 0,
                    ],
                    "r": rows_for.get(lea_name, []),
                }
            )
        if lea_rows:
            by_year[str(school_year)] = lea_rows
    return {"s": strings.values, "y": by_year}


def _check_chester(payload: dict, school_year: int) -> None:
    names = leas("Chester", school_year)
    raw = expense_frame("Chester", names, school_year)
    summary = selection_summary(raw, MEASURE_PER_PUPIL, school_year)
    rows = payload["y"][str(school_year)]
    strings = payload["s"]
    total = sum(row["x"] for row in rows)
    charter = sum(row["c"][0] + row["c"][1] for row in rows if row["k"] == "SD")
    enrollment = sum(row["e"] for row in rows)
    if abs(total - summary["total"]) > 1 or abs(charter - summary["charter_removed"]) > 1:
        raise SystemExit(
            f"Chester {school_year} summary mismatch: exported {total} / {charter}, app {summary['total']} / {summary['charter_removed']}"
        )
    if abs(enrollment - summary["enrollment"]) > 1:
        raise SystemExit("Chester enrollment mismatch")
    per = apply_measure(raw, MEASURE_PER_PUPIL)
    exported = 0.0
    for row in rows:
        if strings[row["n"]] in names:
            exported += sum(item[4] or 0 for item in row["r"])
    if abs(exported - float(per["slice_value"].sum())) > 1:
        raise SystemExit(f"Chester sunburst mismatch: {exported} vs {float(per['slice_value'].sum())}")


def _plotly_js() -> Path:
    matches = list(PLOTLY_JS.glob("python*/site-packages/plotly/package_data/plotly.min.js"))
    if not matches:
        raise FileNotFoundError("plotly.min.js is not in .venv; pip install -e . first")
    return matches[0]


def main() -> None:
    available_years = years()
    published = set(tuition_years())
    default_year = next((year for year in reversed(available_years) if year in published), available_years[-1])
    county_names = counties()
    data_dir = OUT / "data"
    if OUT.exists():
        shutil.rmtree(OUT)
    data_dir.mkdir(parents=True)
    shutil.copyfile(_plotly_js(), OUT / "plotly.min.js")
    chester = None
    for county in county_names:
        payload = _county_payload(county, available_years, published)
        if county == "Chester":
            chester = payload
        target = data_dir / f"{county}.json"
        target.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")
        print(f"{county}: {target.stat().st_size / 1_000_000:.1f} MB")
    if chester is None:
        raise SystemExit("Chester County is missing from the export")
    _check_chester(chester, default_year)
    meta = {
        "counties": county_names,
        "years": available_years,
        "tuitionYears": sorted(published),
        "defaultCounty": "Chester" if "Chester" in county_names else county_names[0],
        "defaultYear": default_year,
    }
    html = PAGE.replace("__META__", json.dumps(meta).replace("<", "\\u003c"))
    (OUT / "index.html").write_text(html, encoding="utf-8")
    print(f"wrote {OUT} default year {default_year}")


if __name__ == "__main__":
    main()
