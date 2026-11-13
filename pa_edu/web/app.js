const CATEGORIES = [
  ["school_district", "School district"],
  ["charter_school", "Charter"],
  ["career_and_technical_center", "Career & technical"],
  ["jointure", "Jointure"],
  ["state_juvenile_correctional", "State juvenile"],
  ["unknown", "Other"],
];
const STATUSES = [
  ["open", "Open"],
  ["closed", "Closed"],
  ["unknown", "Unknown"],
];
const CATEGORY_LABEL = Object.fromEntries(CATEGORIES);

const app = document.querySelector("#app");
const crumb = document.querySelector("#crumb");
const tip = document.querySelector("#tip");
let catalog = null;
let leaPack = null;
let toastTimer = 0;

function asset(path) {
  return new URL(path, import.meta.url);
}

async function loadJson(path) {
  const response = await fetch(asset(path));
  if (!response.ok) throw new Error("Could not load " + path);
  return response.json();
}

const LEA_TABS = [
  ["overview", "Overview"],
  ["financials", "Financials"],
  ["staff", "Staff"],
  ["enrollment", "Enrollment"],
  ["pssa", "PSSA"],
  ["keystone", "Keystone"],
];
const PSSA_TOGGLE_GROUPS = [
  "All Students",
  "Economically Disadvantaged",
  "Hispanic (any race)",
  "IEP",
  "ELL",
  "White (not Hispanic)",
  "Black or African American (not Hispanic)",
  "Male",
  "Female",
];
const PSSA_DEFAULT_GROUPS = [
  "All Students",
  "Economically Disadvantaged",
  "IEP",
  "ELL",
];
const PSSA_GROUP_ORDER = [
  "Economically Disadvantaged",
  "Hispanic (any race)",
  "IEP",
  "ELL",
  "Black or African American (not Hispanic)",
  "Male",
  "Female",
  "Multi-ethnic (not Hispanic)",
  "White (not Hispanic)",
  "Asian (not Hispanic)",
];
const PSSA_GROUP_LABEL = {
  "All Students": "All students",
  "Economically Disadvantaged": "Econ. disadvantaged",
  IEP: "IEP",
  ELL: "English learners",
  "Hispanic (any race)": "Hispanic",
  "Black or African American (not Hispanic)": "Black",
  "White (not Hispanic)": "White",
  "Asian (not Hispanic)": "Asian",
  "Multi-ethnic (not Hispanic)": "Multi-ethnic",
  Female: "Female",
  Male: "Male",
};
const PSSA_SUBJECTS = [
  ["math", "Math"],
  ["ela", "ELA"],
];
const PSSA_SUBJECT_IDS = PSSA_SUBJECTS.map(([id]) => id);
const PSSA_SUBJECT_LABEL = Object.fromEntries(PSSA_SUBJECTS);
const PSSA_GRADE_CODES = ["003", "004", "005", "006", "007", "008"];
const PSSA_GRADE_LABELS = ["3", "4", "5", "6", "7", "8"];
/** Canvas chart palette — high hue/luma spread so multi-series lines stay separable. */
const PSSA_GROUP_COLOR = {
  "All Students": "#2E79B5",
  "Economically Disadvantaged": "#F0A040",
  "Hispanic (any race)": "#7B64B8",
  IEP: "#C85898",
  ELL: "#1F8A65",
  "White (not Hispanic)": "#2A9A8A",
  "Black or African American (not Hispanic)": "#C06028",
  Male: "#5A6CC0",
  Female: "#E8C030",
};
const KEYSTONE_SUBJECTS = [
  ["algebra_i", "Algebra I"],
  ["literature", "Literature"],
  ["biology", "Biology"],
];
const KEYSTONE_SUBJECT_IDS = KEYSTONE_SUBJECTS.map(([id]) => id);
const KEYSTONE_LABEL = Object.fromEntries(KEYSTONE_SUBJECTS);
const KEYSTONE_METRICS = [
  ["pct", "Proficient+"],
  ["advanced", "Advanced"],
  ["proficient", "Proficient"],
  ["basic", "Basic"],
  ["below", "Below basic"],
];
const KEYSTONE_METRIC_IDS = KEYSTONE_METRICS.map(([id]) => id);
const KEYSTONE_METRIC_LABEL = Object.fromEntries(KEYSTONE_METRICS);
const KEYSTONE_METRIC_COLOR = {
  pct: "#2E79B5",
  advanced: "#1F8A65",
  proficient: "#7B64B8",
  basic: "#F0A040",
  below: "#C06028",
};
const COHORT_COLORS = [
  "#8B6914", "#C04848", "#C06028", "#F0A040", "#C4A035", "#1F8A65", "#2E9B7A",
  "#2E79B5", "#3D6BB5", "#5B5FA8", "#7B64B8", "#C85898", "#0c5c56",
];
const COHORT_DASH = [
  null, null, null, "7 5", "7 5", "7 5", "7 5",
  "3 4", "3 4", "3 4", "2 3", "2 3", null,
];
const ENROLL_LADDER = [
  { code: "K", label: "K" },
  ...Array.from({ length: 12 }, (_, index) => {
    const grade = String(index + 1);
    return { code: grade.padStart(3, "0"), label: grade };
  }),
];
const ENROLL_GRADE_CODES = ENROLL_LADDER.map((grade) => grade.code);
const TREND_TOTAL = "total";
const TREND_SERIES = [
  ...ENROLL_LADDER,
  { code: TREND_TOTAL, label: "Total" },
];
const TREND_SERIES_CODES = TREND_SERIES.map((row) => row.code);
const TREND_DEFAULT = [TREND_TOTAL];
const K_GRADE_CODES = ["k4", "k4a", "k4p", "k4f", "k5", "k5a", "k5p", "k5f"];
const ALT_SERIES = [
  { code: "district", label: "District", color: "#0c5c56", dash: null, field: null },
  { code: "charter", label: "Charter", color: "#C06028", dash: "7 5", field: "charterAdm" },
  { code: "homeschool", label: "Homeschool", color: "#7B64B8", dash: "3 4", field: "homeEducation" },
];
const ALT_SERIES_CODES = ALT_SERIES.map((row) => row.code);
const ALT_DEFAULT = [...ALT_SERIES_CODES];
const GRAD_ALL = "all";
const GRAD_SERIES = [
  { code: GRAD_ALL, label: "All students", color: "#0c5c56" },
  { code: "male", label: "Male", color: "#5A6CC0" },
  { code: "female", label: "Female", color: "#E8C030" },
  { code: "special_ed", label: "IEP", color: "#C85898" },
  { code: "el", label: "English learners", color: "#1F8A65" },
  { code: "econ_disadv", label: "Econ. disadvantaged", color: "#F0A040" },
  { code: "white", label: "White", color: "#2A9A8A" },
  { code: "black", label: "Black", color: "#C06028" },
  { code: "hispanic", label: "Hispanic", color: "#7B64B8" },
  { code: "asian", label: "Asian", color: "#2E79B5" },
  { code: "multi_racial", label: "Multi-racial", color: "#A33B6B" },
  { code: "american_indian", label: "American Indian", color: "#8B6914" },
  { code: "pacific_islander", label: "Pacific Islander", color: "#5B5FA8" },
  { code: "migrant", label: "Migrant", color: "#C04848" },
  { code: "foster", label: "Foster", color: "#4C6A8A" },
  { code: "homeless", label: "Homeless", color: "#D4783A" },
  { code: "military", label: "Military", color: "#1F4E79" },
];
const GRAD_SERIES_CODES = GRAD_SERIES.map((row) => row.code);
const GRAD_DEFAULT = [GRAD_ALL];

/** Total is exclusive of grade lines; multiple grades may be on together. */
function normalizeTrendSelection(codes) {
  const selected = TREND_SERIES_CODES.filter((code) => (codes || []).includes(code));
  if (!selected.length) return [...TREND_DEFAULT];
  const grades = selected.filter((code) => code !== TREND_TOTAL);
  if (grades.length) return grades;
  return [TREND_TOTAL];
}

function normalizeAltSelection(codes) {
  const selected = ALT_SERIES_CODES.filter((code) => (codes || []).includes(code));
  return selected.length ? selected : [...ALT_DEFAULT];
}

function normalizeGradSelection(codes, available = GRAD_SERIES_CODES) {
  const selected = available.filter((code) => (codes || []).includes(code));
  if (selected.length) return selected;
  if (available.includes(GRAD_ALL)) return [GRAD_ALL];
  return available.length ? [available[0]] : [];
}
const RACE_ORDER = [
  "White",
  "Hispanic",
  "Black or African American",
  "Asian",
  "Multi-Racial",
  "American Indian / Alaskan Native",
  "Native Hawaiian or other Pacific Islander(not Hispanic)",
];
/** Stable colors for race trend lines — keep separable across the seven PDE groups. */
const RACE_COLOR = {
  White: "#2A9A8A",
  Hispanic: "#7B64B8",
  "Black or African American": "#C06028",
  Asian: "#2E79B5",
  "Multi-Racial": "#C85898",
  "American Indian / Alaskan Native": "#F0A040",
  "Native Hawaiian or other Pacific Islander(not Hispanic)": "#5A6CC0",
};
const DEMO_LOW_INCOME = "Economically Disadvantaged";
const DEMO_IEP = "IEP";
const DEMO_GENDER_KEYS = ["Female", "Male"];
const DEMO_EXTRA_KEYS = [DEMO_LOW_INCOME, DEMO_IEP, ...DEMO_GENDER_KEYS];
const DEMO_GENDER_COLOR = {
  Female: "#E8C030",
  Male: "#5A6CC0",
};
const DEMO_EXTRA_COLOR = {
  [DEMO_LOW_INCOME]: "#F0A040",
  [DEMO_IEP]: "#C85898",
  ...DEMO_GENDER_COLOR,
};
const DEMO_EXTRA_LABEL = {
  [DEMO_LOW_INCOME]: "Econ. disadvantaged",
  [DEMO_IEP]: "IEP",
  Female: "Female",
  Male: "Male",
};

function readState() {
  const query = new URLSearchParams(location.search);
  const categories = query.get("category");
  const tab = query.get("tab") || "overview";
  const groupsParam = query.get("groups");
  const groups = groupsParam
    ? groupsParam.split("|").filter((name) => PSSA_TOGGLE_GROUPS.includes(name))
    : [...PSSA_DEFAULT_GROUPS];
  const cohort = query.get("cohort");
  const egradesParam = query.get("egrades");
  const egrades = egradesParam
    ? egradesParam.split("|").filter((code) => ENROLL_GRADE_CODES.includes(code))
    : [...ENROLL_GRADE_CODES];
  const etrendParam = query.get("etrend");
  const etrend = normalizeTrendSelection(
    etrendParam ? etrendParam.split("|") : TREND_DEFAULT,
  );
  const ealtParam = query.get("ealt");
  const ealt = normalizeAltSelection(
    ealtParam ? ealtParam.split("|") : ALT_DEFAULT,
  );
  const edemoParam = query.get("edemo");
  const edemo = edemoParam ? edemoParam.split("|").filter(Boolean) : null;
  const ggroupsParam = query.get("ggroups");
  const ggroups = ggroupsParam
    ? ggroupsParam.split("|").filter((code) => GRAD_SERIES_CODES.includes(code))
    : [...GRAD_DEFAULT];
  const rawSubject = query.get("subject") || "";
  let subject = "math";
  if (KEYSTONE_SUBJECT_IDS.includes(rawSubject)) subject = rawSubject;
  else if (rawSubject === "ela") subject = "ela";
  const metric = query.get("metric") || "pct";
  const experience = query.get("experience") === "edu" ? "edu" : "lea";
  return {
    county: query.get("county") || "",
    aun: query.get("aun") || "",
    year: query.get("year") || "",
    tab: LEA_TABS.some(([id]) => id === tab) ? tab : "overview",
    subject,
    metric: KEYSTONE_METRIC_IDS.includes(metric) ? metric : "pct",
    experience,
    groups: groups.length ? groups : [...PSSA_DEFAULT_GROUPS],
    cohort: PSSA_TOGGLE_GROUPS.includes(cohort) ? cohort : "All Students",
    egrades: egrades.length ? egrades : [...ENROLL_GRADE_CODES],
    etrend,
    ealt,
    edemo,
    ggroups: ggroups.length ? ggroups : [...GRAD_DEFAULT],
    q: query.get("q") || "",
    category: categories ? categories.split(",").filter(Boolean) : CATEGORIES.map(([id]) => id),
    categoryAll: !categories,
    status: (query.get("status") || "open").split(",").filter(Boolean),
    sort: query.get("sort") || "name",
    dir: query.get("dir") || "asc",
    schools: query.get("schools") || "enrollment",
    budget: query.get("budget") || "",
    spend: query.get("spend") === "budget" ? "budget" : query.get("spend") === "actual" ? "actual" : "",
  };
}

function writeUrl(state, mode) {
  const query = new URLSearchParams();
  if (state.county) query.set("county", state.county);
  if (state.aun) query.set("aun", state.aun);
  if (includeYear(state)) query.set("year", state.year);
  if (state.aun && state.tab && state.tab !== "overview") query.set("tab", state.tab);
  putAssessmentParams(query, state);
  if (state.q) query.set("q", state.q);
  if (!state.categoryAll) query.set("category", state.category.join(","));
  query.set("status", state.status.join(","));
  if (state.sort !== "name") query.set("sort", state.sort);
  if (state.dir !== "asc") query.set("dir", state.dir);
  if (state.schools !== "enrollment") query.set("schools", state.schools);
  if (state.budget) query.set("budget", state.budget);
  if (state.spend === "actual" || state.spend === "budget") query.set("spend", state.spend);
  const next = location.pathname + (query.toString() ? "?" + query : "");
  if (next === location.pathname + location.search) return;
  if (mode === "push") history.pushState(null, "", next);
  else history.replaceState(null, "", next);
}

function putAssessmentParams(query, state) {
  if (!state.aun) return;
  if (state.tab === "pssa") {
    if (state.subject === "ela") query.set("subject", "ela");
    const defaultGroups = PSSA_DEFAULT_GROUPS.join("|");
    const groups = (state.groups || PSSA_DEFAULT_GROUPS).join("|");
    if (groups !== defaultGroups) query.set("groups", groups);
    if (state.cohort && state.cohort !== "All Students") query.set("cohort", state.cohort);
  } else if (state.tab === "keystone") {
    if (state.subject && state.subject !== "algebra_i") query.set("subject", state.subject);
    if (state.metric && state.metric !== "pct") query.set("metric", state.metric);
    const defaultGroups = PSSA_DEFAULT_GROUPS.join("|");
    const groups = (state.groups || PSSA_DEFAULT_GROUPS).join("|");
    if (groups !== defaultGroups) query.set("groups", groups);
  } else if (state.tab === "enrollment") {
    const selected = (state.egrades || ENROLL_GRADE_CODES).filter((code) => ENROLL_GRADE_CODES.includes(code));
    if (selected.length && selected.join("|") !== ENROLL_GRADE_CODES.join("|")) {
      query.set("egrades", selected.join("|"));
    }
    const trend = normalizeTrendSelection(state.etrend);
    if (trend.join("|") !== TREND_DEFAULT.join("|")) {
      query.set("etrend", trend.join("|"));
    }
    const alt = normalizeAltSelection(state.ealt);
    if (alt.join("|") !== ALT_DEFAULT.join("|")) {
      query.set("ealt", alt.join("|"));
    }
    if (Array.isArray(state.edemo) && state.edemo.length) {
      const available = demoSeriesKeys();
      const selected = state.edemo.filter((key) => available.includes(key));
      const defaultKeys = demoDefaultKeys(available);
      if (selected.length && selected.join("|") !== defaultKeys.join("|")) {
        query.set("edemo", selected.join("|"));
      }
    }
    const gradSelected = normalizeGradSelection(state.ggroups, gradSeriesKeys());
    if (gradSelected.join("|") !== GRAD_DEFAULT.join("|")) {
      query.set("ggroups", gradSelected.join("|"));
    }
  } else if (state.tab === "staff") {
    if (state.experience === "edu") query.set("experience", "edu");
  }
}

function yearLabel(year) {
  const start = Number(year);
  return start + "–" + String(start + 1).slice(-2);
}

function includeYear(state) {
  return Boolean(state.aun && state.tab === "financials" && state.year);
}

function money(value, digits = 1) {
  if (value == null || Number.isNaN(Number(value))) return "Not published";
  const amount = Number(value);
  const sign = amount < 0 ? "−" : "";
  const abs = Math.abs(amount);
  if (abs >= 1e9) return sign + "$" + (abs / 1e9).toFixed(2) + " billion";
  if (abs >= 1e6) return sign + "$" + (abs / 1e6).toFixed(digits) + " million";
  return sign + "$" + Math.round(abs).toLocaleString("en-US");
}

function moneyFull(value) {
  if (value == null) return "";
  return Number(value).toLocaleString("en-US", { style: "currency", currency: "USD" });
}

function count(value) {
  if (value == null) return "Not published";
  return Number(value).toLocaleString("en-US");
}

function categoryName(id) {
  return CATEGORY_LABEL[id] || id;
}

function matches(lea, state) {
  if (state.county && lea.county !== state.county) return false;
  if (!state.category.includes(lea.category)) return false;
  if (!state.status.includes(lea.status)) return false;
  if (!state.q) return true;
  const needle = state.q.toLowerCase();
  return lea.name.toLowerCase().includes(needle) || lea.aun.includes(needle) || lea.county.toLowerCase().includes(needle);
}

function viewOf(state) {
  if (state.aun) return "lea";
  if (state.county) return "county";
  return "home";
}

function ensure(view, html) {
  if (app.dataset.view === view) return false;
  app.dataset.view = view;
  app.innerHTML = html;
  return true;
}

function syncInput(selector, value) {
  const input = app.querySelector(selector);
  if (input && document.activeElement !== input && input.value !== value) input.value = value;
}

function setPressed(selector, selected) {
  for (const button of app.querySelectorAll(selector)) {
    button.setAttribute("aria-pressed", selected(button.dataset.value) ? "true" : "false");
  }
}

function renderCrumb(state) {
  const parts = [`<a href="./">Counties</a>`];
  if (state.county) {
    const countyState = { ...state, aun: "", year: "" };
    parts.push(`<a href="${escapeAttr(link(countyState))}">${escapeHtml(state.county)}</a>`);
  }
  if (state.aun && leaPack) parts.push(`<span>${escapeHtml(leaPack.name)}</span>`);
  crumb.innerHTML = parts.join(" / ");
}

function link(state) {
  const query = new URLSearchParams();
  if (state.county) query.set("county", state.county);
  if (state.aun) query.set("aun", state.aun);
  if (includeYear(state)) query.set("year", state.year);
  if (state.aun && state.tab && state.tab !== "overview") query.set("tab", state.tab);
  putAssessmentParams(query, state);
  if (state.q) query.set("q", state.q);
  if (!state.categoryAll) query.set("category", state.category.join(","));
  query.set("status", state.status.join(","));
  if (state.budget) query.set("budget", state.budget);
  const text = query.toString();
  return text ? "?" + text : "./";
}

function toast(message) {
  const node = document.querySelector("#toast");
  node.textContent = message;
  node.classList.add("show");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => node.classList.remove("show"), 1800);
}

async function share() {
  const url = location.href;
  try {
    await navigator.clipboard.writeText(url);
    toast("Link copied");
  } catch {
    const field = document.createElement("input");
    field.value = url;
    document.body.appendChild(field);
    field.select();
    document.execCommand("copy");
    field.remove();
    toast("Link copied");
  }
}

function bindHome() {
  app.querySelector("#q").addEventListener("input", (event) => {
    const state = readState();
    state.q = event.target.value.trim();
    writeUrl(state, "replace");
    paintHome(state);
    renderCrumb(state);
  });
  bindFilters(() => paintHome(readState()));
}

function bindCounty() {
  app.querySelector("#q").addEventListener("input", (event) => {
    const state = readState();
    state.q = event.target.value.trim();
    writeUrl(state, "replace");
    paintCounty(state);
  });
  bindFilters(() => paintCounty(readState()));
  app.querySelector(".sorts").addEventListener("click", (event) => {
    const button = event.target.closest("button");
    if (!button) return;
    const state = readState();
    if (state.sort === button.dataset.sort) state.dir = state.dir === "asc" ? "desc" : "asc";
    else {
      state.sort = button.dataset.sort;
      state.dir = button.dataset.sort === "name" ? "asc" : "desc";
    }
    writeUrl(state, "replace");
    paintCounty(state);
  });
}

function bindFilters(paint) {
  app.querySelectorAll(".chip").forEach((button) => {
    button.addEventListener("click", () => {
      const state = readState();
      const kind = button.dataset.kind;
      const value = button.dataset.value;
      const all = kind === "category" ? CATEGORIES.map(([id]) => id) : STATUSES.map(([id]) => id);
      const selected = new Set(kind === "category" ? state.category : state.status);
      if (selected.has(value)) selected.delete(value);
      else selected.add(value);
      if (selected.size === 0 || selected.size === all.length) selected = new Set(all);
      const ordered = all.filter((id) => selected.has(id));
      if (kind === "category") {
        state.category = ordered;
        state.categoryAll = ordered.length === all.length;
      } else state.status = ordered;
      writeUrl(state, "replace");
      paint();
    });
  });
}

function bindLea() {
  // Year pills and tabs are recreated with the LEA shell; rebind those each time.
  app.querySelector(".years")?.addEventListener("click", (event) => {
    const button = event.target.closest("button");
    if (!button) return;
    const state = readState();
    state.tab = "financials";
    state.year = button.dataset.year;
    state.budget = "";
    writeUrl(state, "replace");
    paintLea(state);
  });
  app.querySelector(".lea-tabs").addEventListener("click", (event) => {
    const button = event.target.closest("[data-tab]");
    if (!button) return;
    const state = readState();
    state.tab = button.dataset.tab;
    if (state.tab !== "financials") {
      state.year = "";
      state.budget = "";
    }
    writeUrl(state, "replace");
    paintLea(state);
  });
  // #app survives LEA switches. Binding click/tips more than once makes group
  // toggles fire twice and appear stuck.
  if (app.dataset.leaBound) return;
  app.dataset.leaBound = "1";
  app.addEventListener("click", (event) => {
    const spendMode = event.target.closest("#spend [data-spend]");
    if (spendMode) {
      hideTip();
      const state = readState();
      state.tab = "financials";
      state.spend = spendMode.dataset.spend;
      writeUrl(state, "replace");
      paintLea(state);
      return;
    }
    const spend = event.target.closest("#spend [data-budget]");
    if (spend) {
      hideTip();
      const state = readState();
      state.budget = spend.dataset.budget;
      writeUrl(state, "replace");
      paintLea(state);
      return;
    }
    const subject = event.target.closest("[data-subject]");
    if (subject && !event.target.closest(".rank-wrap")) {
      const state = readState();
      state.subject = subject.dataset.subject;
      writeUrl(state, "replace");
      paintLea(state);
      return;
    }
    const metricToggle = event.target.closest("[data-metric]");
    if (metricToggle) {
      const state = readState();
      state.metric = metricToggle.dataset.metric;
      writeUrl(state, "replace");
      paintLea(state);
      return;
    }
    const experienceToggle = event.target.closest("[data-experience]");
    if (experienceToggle) {
      const state = readState();
      state.tab = "staff";
      state.experience = experienceToggle.dataset.experience === "edu" ? "edu" : "lea";
      writeUrl(state, "replace");
      paintLea(state);
      return;
    }
    const groupToggle = event.target.closest("[data-pssa-group]");
    if (groupToggle) {
      const state = readState();
      const value = groupToggle.dataset.pssaGroup;
      const selected = new Set(state.groups || PSSA_DEFAULT_GROUPS);
      if (selected.has(value)) {
        if (selected.size > 1) selected.delete(value);
      } else selected.add(value);
      state.groups = PSSA_TOGGLE_GROUPS.filter((name) => selected.has(name));
      writeUrl(state, "replace");
      paintLea(state);
      return;
    }
    const cohortToggle = event.target.closest("[data-cohort-group]");
    if (cohortToggle) {
      const state = readState();
      state.cohort = cohortToggle.dataset.cohortGroup;
      writeUrl(state, "replace");
      paintLea(state);
      return;
    }
    const enrollGradeToggle = event.target.closest("[data-enroll-grade]");
    if (enrollGradeToggle) {
      const state = readState();
      const value = enrollGradeToggle.dataset.enrollGrade;
      const selected = new Set(state.egrades || ENROLL_GRADE_CODES);
      if (selected.has(value)) {
        if (selected.size > 1) selected.delete(value);
      } else selected.add(value);
      state.egrades = ENROLL_GRADE_CODES.filter((code) => selected.has(code));
      writeUrl(state, "replace");
      paintLea(state);
      return;
    }
    const trendSeriesToggle = event.target.closest("[data-trend-series]");
    if (trendSeriesToggle) {
      const state = readState();
      const value = trendSeriesToggle.dataset.trendSeries;
      let selected = normalizeTrendSelection(state.etrend);
      if (value === TREND_TOTAL) {
        selected = [TREND_TOTAL];
      } else if (selected.includes(value)) {
        if (selected.length > 1) selected = selected.filter((code) => code !== value);
      } else {
        selected = [...selected.filter((code) => code !== TREND_TOTAL), value];
        selected = TREND_SERIES_CODES.filter((code) => selected.includes(code));
      }
      state.etrend = normalizeTrendSelection(selected);
      writeUrl(state, "replace");
      paintLea(state);
      return;
    }
    const demoSeriesToggle = event.target.closest("[data-demo-series]");
    if (demoSeriesToggle) {
      const state = readState();
      const value = demoSeriesToggle.dataset.demoSeries;
      const available = demoSeriesKeys();
      const selected = new Set(normalizeDemoSelection(state.edemo, available));
      if (selected.has(value)) {
        if (selected.size > 1) selected.delete(value);
      } else if (available.includes(value)) {
        selected.add(value);
      }
      state.edemo = available.filter((key) => selected.has(key));
      writeUrl(state, "replace");
      paintLea(state);
      return;
    }
    const gradSeriesToggle = event.target.closest("[data-grad-series]");
    if (gradSeriesToggle) {
      const state = readState();
      const value = gradSeriesToggle.dataset.gradSeries;
      const available = gradSeriesKeys();
      const selected = new Set(normalizeGradSelection(state.ggroups, available));
      if (selected.has(value)) {
        if (selected.size > 1) selected.delete(value);
      } else if (available.includes(value)) {
        selected.add(value);
      }
      state.ggroups = available.filter((code) => selected.has(code));
      writeUrl(state, "replace");
      paintLea(state);
      return;
    }
    const altSeriesToggle = event.target.closest("[data-alt-series]");
    if (altSeriesToggle) {
      const state = readState();
      const value = altSeriesToggle.dataset.altSeries;
      const selected = new Set(normalizeAltSelection(state.ealt));
      if (selected.has(value)) {
        if (selected.size > 1) selected.delete(value);
      } else selected.add(value);
      state.ealt = normalizeAltSelection(ALT_SERIES_CODES.filter((code) => selected.has(code)));
      writeUrl(state, "replace");
      paintLea(state);
      return;
    }
    const schoolSort = event.target.closest(".schools thead button[data-schools]");
    if (schoolSort) {
      const state = readState();
      state.schools = schoolSort.dataset.schools;
      writeUrl(state, "replace");
      paintLea(state);
    }
  });
  bindTips(app);
}

function bindTips(root) {
  root.addEventListener("pointerover", (event) => {
    const host = root.querySelector("#spend");
    if (host) {
      host.querySelectorAll(".is-hot").forEach((el) => el.classList.remove("is-hot"));
      const hit = event.target.closest("#spend [data-slice]");
      if (hit) {
        for (const el of host.querySelectorAll("[data-slice]")) {
          if (el.dataset.slice === hit.dataset.slice) el.classList.add("is-hot");
        }
      }
    }
    const node = event.target.closest("[data-tip]");
    if (!node) return;
    showTip(node.dataset.tip, event.clientX, event.clientY);
  });
  root.addEventListener("pointermove", (event) => {
    if (tip.hidden) return;
    const node = event.target.closest("[data-tip]");
    if (!node) {
      hideTip();
      return;
    }
    moveTip(event.clientX, event.clientY);
  });
  root.addEventListener("pointerout", (event) => {
    const next = event.relatedTarget instanceof Element ? event.relatedTarget.closest("[data-tip]") : null;
    if (!next) hideTip();
  });
}

function showTip(text, x, y) {
  tip.hidden = false;
  tip.innerHTML = text;
  moveTip(x, y);
}

function moveTip(x, y) {
  const pad = 14;
  const width = tip.offsetWidth || 180;
  const height = tip.offsetHeight || 48;
  let left = x + pad;
  let top = y + pad;
  if (left + width > window.innerWidth - 8) left = x - width - pad;
  if (top + height > window.innerHeight - 8) top = y - height - pad;
  tip.style.left = Math.max(8, left) + "px";
  tip.style.top = Math.max(8, top) + "px";
}

function hideTip() {
  tip.hidden = true;
  tip.innerHTML = "";
}

function tipLines(title, lines) {
  return `<div class="tip-title">${escapeHtml(title)}</div>` + lines.map((line) => `<div>${line}</div>`).join("");
}

function paintHome(state) {
  syncInput("#q", state.q);
  setPressed('[data-kind="category"]', (value) => state.category.includes(value));
  setPressed('[data-kind="status"]', (value) => state.status.includes(value));
  const rows = catalog.leas.filter((lea) => matches({ ...lea }, { ...state, county: "" }));
  const query = state.q.toLowerCase();
  const results = app.querySelector("#results");
  if (query) {
    const hits = rows.filter((lea) => lea.name.toLowerCase().includes(query) || lea.aun.includes(query) || lea.county.toLowerCase().includes(query));
    results.innerHTML = hits.length
      ? `<div class="list">${hits.slice(0, 40).map((lea) => leaLink(lea, state)).join("")}</div>`
      : `<p class="empty">No LEAs match that search.</p>`;
    document.title = `Search · PDE data`;
    return;
  }
  const byCounty = new Map();
  for (const lea of rows) {
    const bucket = byCounty.get(lea.county) || { leas: 0, enrollment: 0, known: false };
    bucket.leas += 1;
    if (lea.enrollment != null) {
      bucket.enrollment += lea.enrollment;
      bucket.known = true;
    }
    byCounty.set(lea.county, bucket);
  }
  const cards = [...byCounty.entries()].sort(([a], [b]) => a.localeCompare(b)).map(([name, bucket]) => {
    const href = link({ ...state, county: name, aun: "", year: "", q: "" });
    const head = bucket.known ? count(bucket.enrollment) + " students" : "No " + yearLabel(catalog.enrollmentYear) + " enrollment";
    const noun = bucket.leas === 1 ? "LEA" : "LEAs";
    return `<a class="county-card" href="${escapeAttr(href)}"><strong>${escapeHtml(name)}</strong><span>${bucket.leas} ${noun} · ${head}</span></a>`;
  });
  results.innerHTML = cards.length
    ? `<div class="county-grid">${cards.join("")}</div>`
    : `<p class="empty">No counties match these filters.</p>`;
  document.title = "PDE data";
}

function paintCounty(state) {
  syncInput("#q", state.q);
  setPressed('[data-kind="category"]', (value) => state.category.includes(value));
  setPressed('[data-kind="status"]', (value) => state.status.includes(value));
  setPressed(".sorts button", (value) => state.sort === value);
  const rows = catalog.leas.filter((lea) => matches(lea, state));
  const dir = state.dir === "desc" ? -1 : 1;
  rows.sort((a, b) => {
    const key = state.sort;
    const left = key === "name" ? a.name : a[key];
    const right = key === "name" ? b.name : b[key];
    if (left == null && right == null) return a.name.localeCompare(b.name);
    if (left == null) return 1;
    if (right == null) return -1;
    if (typeof left === "string") return left.localeCompare(right) * dir;
    return (left - right) * dir;
  });
  app.querySelector("#count").textContent = rows.length + (rows.length === 1 ? " LEA" : " LEAs");
  app.querySelector("#results").innerHTML = rows.length
    ? rows.map((lea) => leaLink(lea, state)).join("")
    : `<p class="empty">No LEAs match these filters.</p>`;
  document.title = state.county + " · PDE data";
}

function leaLink(lea, state) {
  const href = link({ ...state, county: lea.county, aun: lea.aun, year: "", q: state.q });
  return `<a class="lea-row" href="${escapeAttr(href)}">
    <span><b>${escapeHtml(lea.name)}</b><span class="sub"><br>${escapeHtml(categoryName(lea.category))} · ${escapeHtml(lea.aun)}</span></span>
    <span class="hide-sm">${escapeHtml(lea.county)}</span>
    <span class="num">${lea.enrollment == null ? "—" : count(lea.enrollment)}</span>
    <span class="num hide-sm" title="${escapeAttr(moneyFull(lea.actual))}">${lea.actual == null ? "—" : money(lea.actual)}</span>
  </a>`;
}

function blockFor(year) {
  return leaPack.years[String(year)] || {};
}

function latestYear(predicate) {
  const years = Object.keys(leaPack.years)
    .filter((year) => predicate(leaPack.years[year]))
    .sort((a, b) => Number(a) - Number(b));
  return years.at(-1) || "";
}

/** Prefer the catalog's newest enrollment file; fall back to this LEA's latest grade counts. */
function enrollmentAnchorYear() {
  const catalogYear = catalog?.enrollmentYear != null ? String(catalog.enrollmentYear) : "";
  if (catalogYear && enrollmentOf(blockFor(catalogYear)) != null) return catalogYear;
  return latestYear((block) => enrollmentOf(block) != null);
}

function hasFinance(block) {
  if (!block) return false;
  if (sumMap(block.actual) != null || sumMap(block.budget) != null) return true;
  return Object.keys(block.budgetDetail || {}).length > 0 || Object.keys(block.actualDetail || {}).length > 0;
}

function financeYears() {
  return Object.keys(leaPack.years).filter((year) => hasFinance(leaPack.years[year]));
}

function financeYear(state) {
  const years = financeYears();
  if (state.year && years.includes(String(state.year))) return String(state.year);
  return years.at(-1) || "";
}

function enrollmentOf(block) {
  if (!block || !block.grades) return null;
  const values = Object.values(block.grades);
  if (!values.length) return null;
  return values.reduce((sum, value) => sum + value, 0);
}

function sumMap(map) {
  const values = Object.values(map || {});
  if (!values.length) return null;
  return values.reduce((sum, value) => sum + value, 0);
}

function paintLea(state) {
  const tab = state.tab || "overview";
  if (tab === "financials") {
    const year = financeYear(state);
    if (year !== state.year) {
      state.year = year;
      writeUrl(state, "replace");
    }
    setPressed(".years button", (value) => value === year);
  } else if (state.year) {
    state.year = "";
    writeUrl(state, "replace");
  }
  setPressed(".lea-tabs button", (value) => value === tab);
  for (const panel of app.querySelectorAll("[data-tab-panel]")) {
    panel.hidden = panel.dataset.tabPanel !== tab;
  }

  if (tab === "overview") paintOverview();
  else if (tab === "financials") {
    const year = state.year;
    const priorYear = String(Number(year) - 1);
    paintFinancials(blockFor(year), blockFor(priorYear), priorYear, year, state);
  } else if (tab === "staff") paintStaff(state);
  else if (tab === "enrollment") paintEnrollment(state);
  else if (tab === "pssa") paintPssa(state);
  else paintKeystone(state);

  document.title = leaPack.name + " · PDE data";
}

function financeStats(block, priorBlock, priorYear, year) {
  const enrolled = enrollmentOf(block);
  const actual = sumMap(block.actual);
  const budget = sumMap(block.budget);
  const priorEnrolled = enrollmentOf(priorBlock);
  const priorActual = sumMap(priorBlock.actual);
  const priorBudget = sumMap(priorBlock.budget);
  const currentCost = perStudentCost(block, year);
  const priorCost = perStudentCost(priorBlock, priorYear);
  const perPupil = currentCost?.value ?? null;
  const priorPerPupil = priorCost?.value ?? null;
  const perLabel = currentCost?.basis === "budget" ? "Budget per student" : "Actual per student";
  const ranks = block.countyRanks || {};
  return [
    stat("October 1 enrollment", enrolled == null ? "Not published" : count(enrolled), yearDelta(enrolled, priorEnrolled, priorYear), year, ranks.enrollment, "count"),
    stat("General fund actual", money(actual), yearDelta(actual, priorActual, priorYear), "", ranks.actual, "money"),
    stat("General fund budget", money(budget), `${yearDelta(budget, priorBudget, priorYear)}${act1Note(block)}${millNote(block, priorBlock, priorYear)}`, "", ranks.budget, "money"),
    stat(perLabel, perPupil == null ? "Not published" : money(perPupil, 0), `${yearDelta(perPupil, priorPerPupil, priorYear)}${currentCost?.note || ""}`, "", ranks.perStudent, "money0"),
  ].join("");
}

function paintOverview() {
  const enrollYear = enrollmentAnchorYear();
  const enrollBlock = blockFor(enrollYear);
  const priorEnrollYear = String(Number(enrollYear) - 1);
  const pssaYear = latestYear((block) => block.pssa?.math?.total?.["All Students"] || block.pssa?.ela?.total?.["All Students"]);
  const pssaBlock = blockFor(pssaYear);
  const spendYear = latestYear((block) => enrollmentOf(block) && operatingActual(block) != null);
  const spendBlock = blockFor(spendYear);
  const enrolled = enrollmentOf(enrollBlock);
  const pssaMath = pssaBlock.pssa?.math?.total?.["All Students"];
  const pssaEla = pssaBlock.pssa?.ela?.total?.["All Students"];
  const spending = operatingActual(spendBlock);
  const spendEnrolled = enrollmentOf(spendBlock);
  const perPupil = spendEnrolled && spending != null ? spending / spendEnrolled : null;
  const host = app.querySelector("#overview-stats");
  host.innerHTML = [
    stat("October 1 enrollment", enrolled == null ? "Not published" : count(enrolled), `${yearDelta(enrolled, enrollmentOf(blockFor(priorEnrollYear)), priorEnrollYear)}${yearNote(enrollYear)}`, enrollYear, enrollBlock.countyRanks?.enrollment, "count"),
    stat("PSSA math proficient+", pssaMath?.pct == null ? "Not published" : `${Number(pssaMath.pct).toFixed(1)}%`, pssaMath?.n != null ? `<div class="note">${count(pssaMath.n)} scored · ${yearLabel(pssaYear)}</div>` : yearNote(pssaYear)),
    stat("PSSA ELA proficient+", pssaEla?.pct == null ? "Not published" : `${Number(pssaEla.pct).toFixed(1)}%`, pssaEla?.n != null ? `<div class="note">${count(pssaEla.n)} scored · ${yearLabel(pssaYear)}</div>` : yearNote(pssaYear)),
    stat("Actual per student", perPupil == null ? "Not published" : money(perPupil, 0), `<div class="note">${spendYear ? yearLabel(spendYear) + " · " : ""}Excludes charter tuition</div>`, spendYear, spendBlock.countyRanks?.perStudent, "money0"),
  ].join("");
  const keystoneYear = latestYear((block) => KEYSTONE_SUBJECTS.some(([id]) => block.keystone?.[id]?.["011"]));
  const keystoneHost = app.querySelector("#overview-keystone");
  if (keystoneHost) {
    const keystoneBlock = blockFor(keystoneYear);
    const keystoneYearsList = keystoneYears();
    const priorKeystoneYear = priorIn(keystoneYearsList, Number(keystoneYear));
    const priorBlock = priorKeystoneYear == null ? {} : blockFor(priorKeystoneYear);
    const cards = KEYSTONE_SUBJECTS.map(([id, label]) => {
      const cell = keystoneBlock.keystone?.[id]?.["011"]?.["All Students"];
      if (!cell) return "";
      const prior = priorBlock.keystone?.[id]?.["011"]?.["All Students"];
      const note = `${yearDeltaPoints(cell.pct, prior?.pct, priorKeystoneYear)}${cell.n != null ? `<div class="note">${count(cell.n)} scored · grade 11</div>` : ""}${yearNote(keystoneYear)}`;
      const value = cell.pct == null ? "Not published" : `${Number(cell.pct).toFixed(1)}%`;
      return stat(`Keystone ${label}`, value, note, keystoneYear, keystoneBlock.countyRanks?.[`keystone_${id}`], "pct");
    }).filter(Boolean);
    keystoneHost.innerHTML = cards.length ? `<div class="stats stats-3">${cards.join("")}</div>` : "";
  }
  drawRace(app.querySelector("#overview-race"), enrollBlock.race || {}, enrollYear ? `Race / ethnicity · ${yearLabel(enrollYear)}` : "Race / ethnicity");
  drawGender(app.querySelector("#overview-gender"), enrollBlock.gender || {}, enrollYear ? `Gender · ${yearLabel(enrollYear)}` : "Gender");
  const blurb = app.querySelector("#overview-blurb");
  blurb.innerHTML = `<p class="note">Each figure is the latest year published for that series. The year selector is on Financials. Enrollment follows classes as they move up. Keystone charts each exam across years on that tab.</p>`;
}

function yearNote(year) {
  return year ? `<div class="note">${yearLabel(year)}</div>` : "";
}

function paintFinancials(block, priorBlock, priorYear, year, state) {
  app.querySelector("#finance-stats").innerHTML = financeStats(block, priorBlock, priorYear, year);
  drawSpend(block, state);
  app.querySelector("#sources").innerHTML = sourceLinks(year);
}

function paintStaff(state) {
  const year = latestYear((block) =>
    Object.values(block.salaries || {}).some((stats) => stats?.n)
    || Object.values(block.experience || {}).some((group) => group?.lea?.n || group?.edu?.n)
  );
  const mode = state.experience === "edu" ? "edu" : "lea";
  const heading = app.querySelector("#staff-heading");
  if (heading) heading.textContent = year ? `Full-time salaries · ${yearLabel(year)}` : "Full-time salaries";
  const experienceHeading = app.querySelector("#experience-heading");
  if (experienceHeading) {
    experienceHeading.textContent = year ? `Full-time experience · ${yearLabel(year)}` : "Full-time experience";
  }
  setPressed("[data-experience]", (value) => value === mode);
  const block = blockFor(year);
  drawExperience(block.experience || {}, mode);
  drawSalaries(block.salaries || {}, block.retention);
}

function paintEnrollment(state) {
  const year = enrollmentAnchorYear();
  const block = blockFor(year);
  const priorYear = String(Number(year) - 1);
  const enrolled = enrollmentOf(block);
  const gradYearList = gradYears();
  const gradYear = gradYearList.length ? gradYearList[gradYearList.length - 1] : null;
  const grad = gradYear == null ? null : gradCell(gradYear);
  const priorGradYear = gradYearList.length > 1 ? gradYearList[gradYearList.length - 2] : null;
  const priorGrad = priorGradYear == null ? null : gradCell(priorGradYear);
  app.querySelector("#enrollment-stats").innerHTML = [
    stat("October 1 enrollment", enrolled == null ? "Not published" : count(enrolled), `${yearDelta(enrolled, enrollmentOf(blockFor(priorYear)), priorYear)}${yearNote(year)}`, year, block.countyRanks?.enrollment, "count"),
    stat("Schools reporting", count((block.schools || []).length), yearNote(year)),
    stat(
      "4-year graduation",
      grad ? `${(Number(grad.rate) * 100).toFixed(1)}%` : "Not published",
      grad ? `<div class="note">${count(grad.grads)} of ${count(grad.cohort)}</div>${yearDeltaPoints(Number(grad.rate) * 100, priorGrad ? Number(priorGrad.rate) * 100 : null, priorGradYear)}${yearNote(gradYear)}` : "",
      gradYear,
      gradYear == null ? null : blockFor(gradYear).countyRanks?.graduation,
      "pct",
    ),
  ].join("");
  const gradPanel = app.querySelector("#grad-panel");
  if (gradPanel) {
    gradPanel.hidden = gradYearList.length === 0;
    const gradHeading = app.querySelector("#grad-heading");
    if (gradHeading && gradYear != null) {
      gradHeading.textContent = `4-year cohort graduation · through ${yearLabel(gradYear)}`;
    }
    const availableGrad = gradSeriesKeys();
    const selectedGrad = normalizeGradSelection(state.ggroups, availableGrad);
    state.ggroups = selectedGrad;
    const gradFilterHost = app.querySelector("#grad-filters");
    if (gradFilterHost) {
      gradFilterHost.innerHTML = availableGrad.map((code) => {
        const row = GRAD_SERIES.find((item) => item.code === code);
        return `<button type="button" class="chip chip-series" data-grad-series="${escapeAttr(code)}" data-value="${escapeAttr(code)}" style="--series:${row.color}"><i class="swatch" style="background:${row.color}"></i>${escapeHtml(row.label)}</button>`;
      }).join("");
    }
    setPressed("[data-grad-series]", (value) => selectedGrad.includes(value));
    if (gradYearList.length) drawGradRate(gradYearList, selectedGrad);
  }
  const trendHeading = app.querySelector("#trend-heading");
  if (trendHeading) trendHeading.textContent = year ? `Enrollment over time · through ${yearLabel(year)}` : "Enrollment over time";
  const cohortHeading = app.querySelector("#cohort-heading");
  if (cohortHeading) cohortHeading.textContent = year ? `How classes change as they move up · ${yearLabel(year)}` : "How classes change as they move up";
  const gradesHeading = app.querySelector("#grades-heading");
  if (gradesHeading) gradesHeading.textContent = year ? `Grades · ${yearLabel(year)}` : "Grades";
  const schoolsHeading = app.querySelector("#schools-heading");
  if (schoolsHeading) schoolsHeading.textContent = year ? `Schools · ${yearLabel(year)}` : "Schools";
  const egrades = (state.egrades || ENROLL_GRADE_CODES).filter((code) => ENROLL_GRADE_CODES.includes(code));
  const selectedGrades = egrades.length ? egrades : [...ENROLL_GRADE_CODES];
  const selectedTrend = normalizeTrendSelection(state.etrend);
  const selectedAlt = normalizeAltSelection(state.ealt);
  const trendFilterHost = app.querySelector("#trend-filters");
  if (trendFilterHost) {
    trendFilterHost.innerHTML = TREND_SERIES.map((row, index) => {
      const color = row.code === TREND_TOTAL
        ? "#0c5c56"
        : COHORT_COLORS[index % COHORT_COLORS.length];
      return `<button type="button" class="chip chip-series" data-trend-series="${escapeAttr(row.code)}" data-value="${escapeAttr(row.code)}" style="--series:${color}"><i class="swatch" style="background:${color}"></i>${escapeHtml(row.label)}</button>`;
    }).join("");
  }
  setPressed("[data-trend-series]", (value) => selectedTrend.includes(value));
  const altPanel = app.querySelector("#alt-enrollment");
  if (altPanel) {
    const showAlt = leaPack.category === "school_district";
    altPanel.hidden = !showAlt;
    if (showAlt) {
      const altHeading = app.querySelector("#alt-heading");
      if (altHeading) {
        altHeading.textContent = year
          ? `Charter and home education · through ${yearLabel(year)}`
          : "Charter and home education";
      }
      const altFilterHost = app.querySelector("#alt-filters");
      if (altFilterHost) {
        altFilterHost.innerHTML = ALT_SERIES.map((row) => (
          `<button type="button" class="chip chip-series" data-alt-series="${escapeAttr(row.code)}" data-value="${escapeAttr(row.code)}" style="--series:${row.color}"><i class="swatch" style="background:${row.color}"></i>${escapeHtml(row.label)}</button>`
        )).join("");
      }
      setPressed("[data-alt-series]", (value) => selectedAlt.includes(value));
      drawAltEnrollment(selectedAlt);
    }
  }
  const filterHost = app.querySelector("#cohort-filters");
  if (filterHost) {
    filterHost.innerHTML = ENROLL_LADDER.map((grade, index) => {
      const color = COHORT_COLORS[index % COHORT_COLORS.length];
      return `<button type="button" class="chip chip-series" data-enroll-grade="${escapeAttr(grade.code)}" data-value="${escapeAttr(grade.code)}" style="--series:${color}"><i class="swatch" style="background:${color}"></i>${escapeHtml(grade.label)}</button>`;
    }).join("");
  }
  setPressed("[data-enroll-grade]", (value) => selectedGrades.includes(value));
  drawTrend(selectedTrend);
  drawEnrollmentCohorts(year, selectedGrades);
  drawGrades(block.grades || {});
  const availableDemo = demoSeriesKeys();
  const selectedDemo = normalizeDemoSelection(state.edemo, availableDemo);
  state.edemo = selectedDemo;
  const demoFilterHost = app.querySelector("#demo-filters");
  if (demoFilterHost) {
    demoFilterHost.innerHTML = availableDemo.map((key) => {
      const color = demoSeriesColor(key);
      return `<button type="button" class="chip chip-series" data-demo-series="${escapeAttr(key)}" data-value="${escapeAttr(key)}" style="--series:${color}"><i class="swatch" style="background:${color}"></i>${escapeHtml(demoSeriesLabel(key))}</button>`;
    }).join("");
  }
  setPressed("[data-demo-series]", (value) => selectedDemo.includes(value));
  const raceHeading = app.querySelector("#race-heading");
  if (raceHeading) {
    const yearList = demoYears(selectedDemo);
    raceHeading.textContent = yearList.length
      ? `Student groups · through ${yearLabel(yearList[yearList.length - 1])}`
      : "Student groups";
  }
  drawRaceTrend(app.querySelector("#enrollment-race"), selectedDemo);
  drawGender(app.querySelector("#enrollment-gender"), block.gender || {}, year ? `Gender · ${yearLabel(year)}` : "Gender");
  drawSchools(block.schools, state.schools);
  const enrollmentSources = app.querySelector("#enrollment-sources");
  if (enrollmentSources) enrollmentSources.innerHTML = enrollmentSourceLinks(year);
}

function pssaYears(subject) {
  return Object.keys(leaPack.years)
    .filter((year) => {
      if (subject) return Boolean(leaPack.years[year]?.pssa?.[subject]);
      return leaPack.years[year]?.pssa && Object.keys(leaPack.years[year].pssa).length;
    })
    .map(Number)
    .sort((a, b) => a - b);
}

function paintPssa(state) {
  const stats = app.querySelector("#pssa-stats");
  const body = app.querySelector("#pssa-body");
  const subject = PSSA_SUBJECT_IDS.includes(state.subject) ? state.subject : "math";
  if (subject !== state.subject) {
    state.subject = subject;
    writeUrl(state, "replace");
  }
  if (!pssaYears().length) {
    if (stats) stats.innerHTML = "";
    if (body) body.innerHTML = `<p class="note">No PSSA results are published for this LEA.</p>`;
    return;
  }

  const years = pssaYears(subject);
  const year = years.length ? years[years.length - 1] : pssaYears().at(-1);
  const label = PSSA_SUBJECT_LABEL[subject];
  const groups = (state.groups || PSSA_DEFAULT_GROUPS).filter((name) => PSSA_TOGGLE_GROUPS.includes(name));
  const selected = groups.length ? groups : [...PSSA_DEFAULT_GROUPS];
  const cohort = PSSA_TOGGLE_GROUPS.includes(state.cohort) ? state.cohort : "All Students";
  const yearNum = Number(year);
  const all = year == null ? null : pssaTotal(yearNum, subject, "All Students");
  const gapRows = year == null ? [] : pssaGapRows(yearNum, subject, all?.pct ?? null);

  stats.innerHTML = PSSA_SUBJECTS.map(([id, subLabel]) => {
    const subYears = pssaYears(id);
    const subYear = subYears.length ? subYears[subYears.length - 1] : null;
    const priorYear = subYear == null ? null : priorIn(subYears, subYear);
    const cell = subYear == null ? null : pssaTotal(subYear, id, "All Students");
    const prior = priorYear == null ? null : pssaTotal(priorYear, id, "All Students");
    const ranks = subYear == null ? {} : (blockFor(subYear).countyRanks || {});
    const value = cell?.pct == null ? "Not published" : `${Number(cell.pct).toFixed(1)}%`;
    const extra = `${yearDeltaPoints(cell?.pct, prior?.pct, priorYear)}${cell?.n != null ? `<div class="note">${count(cell.n)} scored · grades 3–8</div>` : ""}${yearNote(subYear)}`;
    return stat(`${subLabel} · proficient+`, value, extra, subYear, ranks[`pssa_${id}`], "pct", {
      pick: id,
      selected: id === subject,
    });
  }).join("");

  if (year == null || (!all && !leaPack.years[String(year)]?.pssa?.[subject])) {
    body.innerHTML = `<p class="note">Not enough data available for ${escapeHtml(label)}.</p>`;
    return;
  }

  const gapLead = gapRows.slice(0, 3).map((row) => `${escapeHtml(row.label)} ${row.pct.toFixed(1)}% (${row.gap.toFixed(0)} pts)`).join(" · ");
  const groupPills = seriesChips("data-pssa-group");
  const cohortPills = seriesChips("data-cohort-group");

  body.innerHTML = `
    <div class="callout">
      <strong>${escapeHtml(label)} · who sits below the district average</strong>
      <p>District total is ${all?.pct == null ? "—" : Number(all.pct).toFixed(1) + "%"} proficient and above${all?.n != null ? ` (${count(all.n)} scored)` : ""}. Largest published gaps: ${gapLead || "none published"}.</p>
    </div>

    <h2 class="pssa-h2">Groups by grade · ${escapeHtml(label)} · ${escapeHtml(yearLabel(year))}</h2>
    <p class="note">Click a group to show or hide it on the chart. Defaults are selected — unselect to declutter.</p>
    <div class="chips" aria-label="Student groups">${groupPills}</div>
    <section class="panel pssa-chart-panel">
      <h3>% proficient and above by grade · selected groups</h3>
      <div id="pssa-by-grade"></div>
      <p class="note">Same-year cross-section. X-axis is grade tested; each line is a student group.</p>
    </section>

    <h2 class="pssa-h2">Cohort path · same kids across grades</h2>
    <p class="note">Each line is a current grade cohort in ${escapeHtml(yearLabel(year))}, walked backward through earlier PSSA grades. The grade-8 line runs through 8; the grade-7 line stops at 7. Rising = that group of kids improved as they moved up; a shared drop at one grade points at that grade band, not one cohort.</p>
    <section class="panel pssa-chart-panel">
      <h3>${escapeHtml(label)} proficiency path · ${escapeHtml(PSSA_GROUP_LABEL[cohort] || cohort)}</h3>
      <div class="chips" aria-label="Cohort group">${cohortPills}</div>
      <div id="pssa-cohort"></div>
      <p class="note">Approximate cohorts from grade-level aggregates (membership changes year to year). No 2019–20 PSSA (COVID) — cohorts that missed grade 3 start at their first tested grade.</p>
    </section>

    <section class="panel">
      <h3>District-total gaps · ${escapeHtml(label)} · ${escapeHtml(yearLabel(year))}</h3>
      <div id="pssa-gaps"></div>
    </section>
    ${assessmentSourceNote("pssa", year)}`;

  setPressed("[data-pssa-group]", (value) => selected.includes(value));
  setPressed("[data-cohort-group]", (value) => value === cohort);
  drawPssaByGrade(app.querySelector("#pssa-by-grade"), yearNum, subject, selected);
  drawPssaCohort(app.querySelector("#pssa-cohort"), yearNum, subject, cohort);
  drawPssaGaps(app.querySelector("#pssa-gaps"), gapRows);
}

function paintKeystone(state) {
  const stats = app.querySelector("#keystone-stats");
  const body = app.querySelector("#keystone-body");
  const subject = KEYSTONE_SUBJECT_IDS.includes(state.subject) ? state.subject : "algebra_i";
  const metric = KEYSTONE_METRIC_IDS.includes(state.metric) ? state.metric : "pct";
  if (subject !== state.subject || metric !== state.metric) {
    state.subject = subject;
    state.metric = metric;
    writeUrl(state, "replace");
  }
  if (!keystoneYears().length) {
    if (stats) stats.innerHTML = "";
    if (body) body.innerHTML = `<p class="note">No Keystone results are published for this LEA.</p>`;
    return;
  }

  const years = keystoneYears(subject);
  const year = years.length ? years[years.length - 1] : keystoneYears().at(-1);
  const label = KEYSTONE_LABEL[subject];
  const metricLabel = KEYSTONE_METRIC_LABEL[metric];
  const groups = (state.groups || PSSA_DEFAULT_GROUPS).filter((name) => PSSA_TOGGLE_GROUPS.includes(name));
  const selected = groups.length ? groups : [...PSSA_DEFAULT_GROUPS];
  const gapRows = year == null ? [] : keystoneGapRows(year, subject, metric);

  stats.innerHTML = KEYSTONE_SUBJECTS.map(([id, subLabel]) => {
    const subYears = keystoneYears(id);
    const subYear = subYears.length ? subYears[subYears.length - 1] : null;
    const priorYear = subYear == null ? null : priorIn(subYears, subYear);
    const cell = subYear == null ? null : keystoneCell(subYear, id, "All Students");
    const prior = priorYear == null ? null : keystoneCell(priorYear, id, "All Students");
    const ranks = subYear == null ? {} : (blockFor(subYear).countyRanks || {});
    const value = cell?.pct == null ? "Not published" : `${Number(cell.pct).toFixed(1)}%`;
    const extra = `${yearDeltaPoints(cell?.pct, prior?.pct, priorYear)}${cell?.n != null ? `<div class="note">${count(cell.n)} scored · grade 11</div>` : ""}${yearNote(subYear)}`;
    return stat(`${subLabel} · proficient+`, value, extra, subYear, ranks[`keystone_${id}`], "pct", {
      pick: id,
      selected: id === subject,
    });
  }).join("");

  const metricPills = KEYSTONE_METRICS.map(([id, metricName]) => {
    const color = KEYSTONE_METRIC_COLOR[id] || "#8888A8";
    return `<button type="button" class="chip chip-series" data-metric="${escapeAttr(id)}" data-value="${escapeAttr(id)}" style="--series:${color}"><i class="swatch" style="background:${color}"></i>${escapeHtml(metricName)}</button>`;
  }).join("");
  const groupPills = seriesChips("data-pssa-group");
  body.innerHTML = `
    <h2 class="pssa-h2">${escapeHtml(label)} by year</h2>
    <div class="chips" aria-label="Achievement level">${metricPills}</div>
    <div class="chips" aria-label="Student groups">${groupPills}</div>
    <section class="panel pssa-chart-panel">
      <h3>% ${escapeHtml(metricLabel.toLowerCase())} · ${escapeHtml(label)}</h3>
      <div id="keystone-by-year"></div>
      <p class="note">No 2019–20 Keystones (COVID). Spring 2021 Literature was not widely administered, so that point is often missing.</p>
    </section>

    <section class="panel">
      <h3>Gaps versus all students · ${escapeHtml(metricLabel)} · ${escapeHtml(label)} · ${escapeHtml(yearLabel(year))}</h3>
      <div id="keystone-gaps"></div>
    </section>
    ${assessmentSourceNote("keystone", year)}`;

  setPressed("[data-metric]", (value) => value === metric);
  setPressed("[data-pssa-group]", (value) => selected.includes(value));
  drawKeystoneByYear(app.querySelector("#keystone-by-year"), subject, selected, metric);
  drawKeystoneGaps(app.querySelector("#keystone-gaps"), gapRows, metricLabel);
}

function seriesChips(attr) {
  return PSSA_TOGGLE_GROUPS.map((grp) => {
    const color = PSSA_GROUP_COLOR[grp] || "#8888A8";
    return `<button type="button" class="chip chip-series" ${attr}="${escapeAttr(grp)}" data-value="${escapeAttr(grp)}" style="--series:${color}"><i class="swatch" style="background:${color}"></i>${escapeHtml(PSSA_GROUP_LABEL[grp] || grp)}</button>`;
  }).join("");
}

function keystoneYears(subject) {
  return Object.keys(leaPack.years)
    .filter((year) => {
      if (subject) return Boolean(leaPack.years[year]?.keystone?.[subject]?.["011"]);
      return KEYSTONE_SUBJECTS.some(([id]) => leaPack.years[year]?.keystone?.[id]?.["011"]);
    })
    .map(Number)
    .sort((a, b) => a - b);
}

function keystoneCell(year, subject, group) {
  return leaPack.years[String(year)]?.keystone?.[subject]?.["011"]?.[group] || null;
}

function keystoneMetricValue(cell, metric = "pct") {
  if (!cell) return null;
  if (metric === "pct") return cell.pct ?? null;
  const value = cell[metric];
  return value == null ? null : value;
}

function keystoneGapRows(year, subject, metric = "pct") {
  const allPct = keystoneMetricValue(keystoneCell(year, subject, "All Students"), metric);
  return PSSA_TOGGLE_GROUPS.filter((grp) => grp !== "All Students")
    .map((grp) => {
      const row = keystoneCell(year, subject, grp);
      const pct = keystoneMetricValue(row, metric);
      const n = row?.n ?? null;
      const gap = pct != null && allPct != null ? pct - allPct : null;
      return { grp, label: PSSA_GROUP_LABEL[grp] || grp, pct, n, gap };
    })
    .filter((row) => row.n != null && row.n >= 11 && row.pct != null)
    .sort((a, b) => (a.gap ?? 0) - (b.gap ?? 0));
}

function drawKeystoneByYear(host, subject, selected, metric = "pct") {
  const present = keystoneYears(subject);
  if (!present.length) {
    host.innerHTML = `<p class="note">Not enough data available.</p>`;
    return;
  }
  const metricLabel = KEYSTONE_METRIC_LABEL[metric] || "Proficient+";
  const categories = [];
  for (let year = present[0]; year <= present[present.length - 1]; year++) categories.push(year);
  const series = selected.map((grp) => {
    const slots = categories.map((year) => keystoneMetricValue(keystoneCell(year, subject, grp), metric));
    if (slots.every((value) => value == null)) return null;
    return {
      name: PSSA_GROUP_LABEL[grp] || grp,
      color: PSSA_GROUP_COLOR[grp] || "#8888A8",
      slots,
      emphasis: grp === "All Students",
    };
  }).filter(Boolean);
  if (!series.length) {
    host.innerHTML = `<div class="callout warn"><strong>Not enough data available</strong><p>Selected groups have no published rates for ${escapeHtml(metricLabel.toLowerCase())} (PDE suppresses cells with fewer than 11 scored students).</p></div>`;
    return;
  }
  series.sort((a, b) => Number(a.emphasis) - Number(b.emphasis));
  drawMultiLine(host, {
    categories,
    series,
    ariaLabel: `Keystone ${KEYSTONE_LABEL[subject]} ${metricLabel} by year`,
    categoryLabel: (year) => shortYear(year),
    formatPoint: (row, year, value) => tipLines(row.name, [
      `${KEYSTONE_LABEL[subject]} · ${yearLabel(year)}`,
      `${Number(value).toFixed(1)}% ${metricLabel.toLowerCase()}`,
    ]),
  });
}

function shortYear(year) {
  const start = Number(year);
  return String(start).slice(-2) + "–" + String(start + 1).slice(-2);
}

function drawKeystoneGaps(host, rows, metricLabel = "Proficient+") {
  if (!rows.length) {
    host.innerHTML = `<p class="note">Not enough data available.</p>`;
    return;
  }
  host.innerHTML = `<table class="schools">
    <thead><tr><th>Group</th><th class="num">${escapeHtml(metricLabel)}</th><th class="num">Students</th><th class="num">Gap vs all</th></tr></thead>
    <tbody>${rows.map((row) => `<tr class="${row.gap != null && row.gap < -20 ? "gap-bad" : ""}">
      <td>${escapeHtml(row.label)}</td>
      <td class="num">${row.pct == null ? "—" : row.pct.toFixed(1) + "%"}</td>
      <td class="num">${count(row.n)}</td>
      <td class="num">${row.gap == null ? "—" : row.gap.toFixed(1)}</td>
    </tr>`).join("")}</tbody>
  </table>`;
}

function assessmentSourceNote(assessment, year) {
  const items = [];
  const page = catalog?.sources?.assessment;
  if (page) items.push(`<a href="${escapeAttr(page)}" target="_blank" rel="noopener">Assessment Reporting</a>`);
  const workbook = catalog?.sources?.[assessment]?.[String(year)];
  if (workbook) {
    items.push(`<a href="${escapeAttr(workbook)}" target="_blank" rel="noopener">${escapeHtml(yearLabel(year))} ${assessment === "pssa" ? "PSSA" : "Keystone"} workbook</a>`);
  }
  const label = assessment === "pssa" ? "PSSA" : "Keystone Exams (grade 11 best score)";
  const lead = items.length
    ? `Source: ${items.join(" · ")}`
    : `Source: PDE Assessment Reporting · ${label}`;
  return `<p class="sources note">${lead}. Economically disadvantaged is PDE’s published group. Groups under 11 scored students are suppressed.</p>`;
}

function pssaCell(year, subject, gradeCode, group) {
  const bucket = leaPack.years[String(year)]?.pssa?.[subject];
  if (!bucket) return null;
  return bucket[gradeCode]?.[group] || null;
}

function pssaTotal(year, subject, group) {
  return leaPack.years[String(year)]?.pssa?.[subject]?.total?.[group] || null;
}

function pssaGapRows(year, subject, allPct) {
  return PSSA_TOGGLE_GROUPS.filter((grp) => grp !== "All Students")
    .map((grp) => {
      const row = pssaTotal(year, subject, grp);
      const pctValue = row?.pct ?? null;
      const n = row?.n ?? null;
      const gap = pctValue != null && allPct != null ? pctValue - allPct : null;
      return { grp, label: PSSA_GROUP_LABEL[grp] || grp, pct: pctValue, n, gap };
    })
    .filter((row) => row.n != null && row.n >= 11)
    .sort((a, b) => (a.gap ?? 0) - (b.gap ?? 0));
}

function drawPssaByGrade(host, year, subject, selected) {
  const series = selected.map((grp) => {
    const slots = PSSA_GRADE_CODES.map((code) => {
      const cell = pssaCell(year, subject, code, grp);
      return cell?.pct ?? null;
    });
    if (slots.every((value) => value == null)) return null;
    return {
      name: PSSA_GROUP_LABEL[grp] || grp,
      color: PSSA_GROUP_COLOR[grp] || "#8888A8",
      slots,
      emphasis: grp === "All Students",
    };
  }).filter(Boolean);
  if (!series.length) {
    host.innerHTML = `<div class="callout warn"><strong>Not enough data available</strong><p>Selected groups have no published grade-level proficiency rates (PDE suppresses cells with fewer than 11 scored students). District totals may still appear in the gaps table below.</p></div>`;
    return;
  }
  // Draw "All students" last so the reference line sits on top.
  series.sort((a, b) => Number(a.emphasis) - Number(b.emphasis));
  drawMultiLine(host, {
    categories: PSSA_GRADE_LABELS,
    series,
    ariaLabel: "PSSA proficient and above by grade for selected groups",
  });
}

function drawPssaCohort(host, year, subject, group) {
  const series = [3, 4, 5, 6, 7, 8].map((terminal, index) => {
    const slots = [];
    for (let gradeNum = 3; gradeNum <= terminal; gradeNum++) {
      const code = String(gradeNum).padStart(3, "0");
      const testYear = year - (terminal - gradeNum);
      const cell = pssaCell(testYear, subject, code, group);
      slots.push(cell?.pct ?? null);
    }
    while (slots.length < PSSA_GRADE_CODES.length) slots.push(null);
    if (slots.every((value) => value == null)) return null;
    return {
      name: `Current grade ${terminal}`,
      color: COHORT_COLORS[index % COHORT_COLORS.length],
      dash: COHORT_DASH[index % COHORT_DASH.length],
      slots,
      emphasis: terminal === 8,
    };
  }).filter(Boolean);
  if (!series.length) {
    host.innerHTML = `<div class="callout warn"><strong>Not enough data available</strong><p>Grade-level rates for ${escapeHtml(PSSA_GROUP_LABEL[group] || group)} are suppressed (fewer than 11 scored students per grade). A district-total rate may still be in the gaps table below.</p></div>`;
    return;
  }
  drawMultiLine(host, {
    categories: PSSA_GRADE_LABELS,
    series,
    ariaLabel: `PSSA cohort path for ${PSSA_GROUP_LABEL[group] || group}`,
  });
}

function drawPssaGaps(host, rows) {
  if (!rows.length) {
    host.innerHTML = `<p class="note">Not enough data available.</p>`;
    return;
  }
  host.innerHTML = `<table class="schools">
    <thead><tr><th>Group</th><th class="num">Proficient+</th><th class="num">Students</th><th class="num">Gap vs all</th></tr></thead>
    <tbody>${rows.map((row) => `<tr class="${row.gap != null && row.gap < -20 ? "gap-bad" : ""}">
      <td>${escapeHtml(row.label)}</td>
      <td class="num">${row.pct == null ? "—" : row.pct.toFixed(1) + "%"}</td>
      <td class="num">${count(row.n)}</td>
      <td class="num">${row.gap == null ? "—" : row.gap.toFixed(1)}</td>
    </tr>`).join("")}</tbody>
  </table>`;
}

function drawMultiLine(host, {
  categories,
  series,
  ariaLabel,
  yMin = 0,
  yMax = 100,
  yTicks,
  formatY = (value) => value + "%",
  formatPoint,
  categoryLabel = (label) => "Grade " + label,
  left = 48,
  labelEvery = 1,
  showLegend = true,
}) {
  const width = 720;
  const height = 360;
  const right = 18;
  const top = 18;
  const bottom = 40;
  const plotW = width - left - right;
  const plotH = height - top - bottom;
  const xAt = (index) => left + (categories.length <= 1 ? plotW / 2 : (index / (categories.length - 1)) * plotW);
  const yAt = (value) => top + plotH - ((value - yMin) / (yMax - yMin)) * plotH;
  const ticks = yTicks || [0, 25, 50, 75, 100];
  const pointTip = formatPoint || ((row, category, value) => tipLines(row.name, [
    `Grade ${category}`,
    `${Number(value).toFixed(1)}% proficient+`,
  ]));

  const axis = ticks.map((tick) => {
    const y = yAt(tick);
    return `<line x1="${left}" y1="${y}" x2="${width - right}" y2="${y}" stroke="#e7e1d6" stroke-width="1"/>
      <text class="axis" x="${left - 8}" y="${y + 4}" text-anchor="end">${escapeHtml(formatY(tick))}</text>`;
  }).join("");
  const labels = categories.map((label, index) => {
    if (labelEvery > 1 && index % labelEvery !== 0 && index !== categories.length - 1) return "";
    return `<text class="axis" x="${xAt(index)}" y="${height - 14}" text-anchor="middle">${escapeHtml(categoryLabel(label))}</text>`;
  }).join("");

  const pathD = (row) => {
    const segments = [];
    let current = [];
    row.slots.forEach((value, index) => {
      if (value == null || !Number.isFinite(value)) {
        if (current.length) {
          segments.push(current);
          current = [];
        }
        return;
      }
      current.push([index, value]);
    });
    if (current.length) segments.push(current);
    return segments.map((points) => points.map(([index, value], pointIndex) =>
      `${pointIndex ? "L" : "M"}${xAt(index).toFixed(1)},${yAt(value).toFixed(1)}`
    ).join(" ")).join(" ");
  };

  // Halo understrokes first so crossing lines stay readable.
  const halos = series.map((row) => {
    const d = pathD(row);
    if (!d) return "";
    const dash = row.dash ? ` stroke-dasharray="${row.dash}"` : "";
    return `<path d="${d}" fill="none" stroke="#fffdf8" stroke-width="6.5" stroke-linecap="round" stroke-linejoin="round"${dash}/>`;
  }).join("");

  const paths = series.map((row) => {
    const d = pathD(row);
    if (!d) return "";
    const widthPx = row.emphasis ? 3.4 : 2.8;
    const dash = row.dash ? ` stroke-dasharray="${row.dash}"` : "";
    const dots = row.slots.map((value, index) => {
      if (value == null || !Number.isFinite(value)) return "";
      const tip = pointTip(row, categories[index], value, index);
      const r = row.emphasis ? 5 : 4.2;
      return `<circle class="line-dot" data-tip="${escapeAttr(tip)}" cx="${xAt(index)}" cy="${yAt(value)}" r="${r}" fill="${row.color}" stroke="#fffdf8" stroke-width="1.6"></circle>`;
    }).join("");
    return `<path d="${d}" fill="none" stroke="${row.color}" stroke-width="${widthPx}" stroke-linecap="round" stroke-linejoin="round"${dash}/>${dots}`;
  }).join("");

  const legend = series.map((row) => {
    const dashAttr = row.dash ? ` stroke-dasharray="${row.dash}"` : "";
    return `<span class="line-legend">
      <svg width="28" height="10" viewBox="0 0 28 10" aria-hidden="true">
        <line x1="1" y1="5" x2="27" y2="5" stroke="${row.color}" stroke-width="2.6" stroke-linecap="round"${dashAttr}/>
        <circle cx="14" cy="5" r="3.2" fill="${row.color}" stroke="#fffdf8" stroke-width="1"/>
      </svg>
      ${escapeHtml(row.name)}
    </span>`;
  }).join("");

  host.innerHTML = `${showLegend ? `<div class="line-legend-row">${legend}</div>` : ""}
    <svg class="chart line-chart" viewBox="0 0 ${width} ${height}" role="img" aria-label="${escapeAttr(ariaLabel)}">${axis}${labels}${halos}${paths}</svg>`;
}

function raceLabel(name) {
  if (name.startsWith("Native Hawaiian")) return "Pacific Islander";
  if (name.startsWith("American Indian")) return "American Indian";
  if (name === "Black or African American") return "Black";
  if (name === "Multi-Racial") return "Multi-racial";
  return name;
}

function demoSeriesLabel(key) {
  if (DEMO_EXTRA_LABEL[key]) return DEMO_EXTRA_LABEL[key];
  return raceLabel(key);
}

function demoSeriesColor(key, index = 0) {
  if (DEMO_EXTRA_COLOR[key]) return DEMO_EXTRA_COLOR[key];
  return RACE_COLOR[key] || COHORT_COLORS[index % COHORT_COLORS.length];
}

function demoValue(year, key) {
  const block = leaPack?.years?.[String(year)] || {};
  if (key === DEMO_LOW_INCOME) {
    const value = block.lowIncome?.n;
    if (value == null || value === "") return null;
    const number = Number(value);
    return Number.isFinite(number) ? number : null;
  }
  if (key === DEMO_IEP) {
    const value = block.iep?.n;
    if (value == null || value === "") return null;
    const number = Number(value);
    return Number.isFinite(number) ? number : null;
  }
  if (DEMO_GENDER_KEYS.includes(key)) {
    const value = block.gender?.[key];
    if (value == null || value === "") return null;
    const number = Number(value);
    return Number.isFinite(number) ? number : null;
  }
  const value = block.race?.[key];
  if (value == null || value === "") return null;
  const number = Number(value);
  return Number.isFinite(number) ? number : null;
}

function demoPct(year, key) {
  const block = leaPack?.years?.[String(year)] || {};
  let value = null;
  let source = null;
  if (key === DEMO_LOW_INCOME) {
    value = block.lowIncome?.pct;
    source = "low-income report";
  } else if (key === DEMO_IEP) {
    value = block.iep?.pct;
    source = "IEP child count";
  } else {
    return null;
  }
  if (value == null || value === "") return null;
  const number = Number(value);
  if (!Number.isFinite(number)) return null;
  return { pct: number, source };
}

function raceYears() {
  return Object.keys(leaPack?.years || {})
    .map(Number)
    .sort((a, b) => a - b)
    .filter((year) => {
      const race = leaPack.years[String(year)]?.race || {};
      return Object.keys(race).some((key) => race[key] != null && Number(race[key]) > 0);
    });
}

function genderYears() {
  return Object.keys(leaPack?.years || {})
    .map(Number)
    .sort((a, b) => a - b)
    .filter((year) => {
      const gender = leaPack.years[String(year)]?.gender || {};
      return DEMO_GENDER_KEYS.some((key) => gender[key] != null && Number(gender[key]) > 0);
    });
}

function lowIncomeYears() {
  return Object.keys(leaPack?.years || {})
    .map(Number)
    .sort((a, b) => a - b)
    .filter((year) => {
      const value = leaPack.years[String(year)]?.lowIncome?.n;
      return value != null && Number(value) >= 0;
    });
}

function iepYears() {
  return Object.keys(leaPack?.years || {})
    .map(Number)
    .sort((a, b) => a - b)
    .filter((year) => {
      const value = leaPack.years[String(year)]?.iep?.n;
      return value != null && Number(value) >= 0;
    });
}

function raceKeysForYears(years) {
  const seen = new Set();
  for (const year of years) {
    const race = leaPack.years[String(year)]?.race || {};
    for (const [key, value] of Object.entries(race)) {
      if (value != null && Number(value) > 0) seen.add(key);
    }
  }
  const ordered = RACE_ORDER.filter((key) => seen.has(key));
  const extras = [...seen].filter((key) => !RACE_ORDER.includes(key)).sort();
  return [...ordered, ...extras];
}

function demoSeriesKeys() {
  const raceKeys = raceKeysForYears(raceYears());
  const extras = [];
  if (lowIncomeYears().some((year) => demoValue(year, DEMO_LOW_INCOME) != null)) {
    extras.push(DEMO_LOW_INCOME);
  }
  if (iepYears().some((year) => demoValue(year, DEMO_IEP) != null)) {
    extras.push(DEMO_IEP);
  }
  for (const key of DEMO_GENDER_KEYS) {
    if (genderYears().some((year) => {
      const value = demoValue(year, key);
      return value != null && value > 0;
    })) {
      extras.push(key);
    }
  }
  return [...raceKeys, ...extras];
}

function demoDefaultKeys(available = demoSeriesKeys()) {
  return available.filter((key) => !DEMO_EXTRA_KEYS.includes(key));
}

function normalizeDemoSelection(selected, available = demoSeriesKeys()) {
  const defaults = demoDefaultKeys(available);
  if (!available.length) return [];
  if (!Array.isArray(selected) || !selected.length) return defaults.length ? defaults : [...available];
  const picked = available.filter((key) => selected.includes(key));
  if (picked.length) return picked;
  return defaults.length ? defaults : [...available];
}

function demoYears(selected) {
  const keys = selected?.length ? selected : demoDefaultKeys();
  const wantsRace = keys.some((key) => !DEMO_EXTRA_KEYS.includes(key));
  const wantsGender = keys.some((key) => DEMO_GENDER_KEYS.includes(key));
  const wantsLowIncome = keys.includes(DEMO_LOW_INCOME);
  const wantsIep = keys.includes(DEMO_IEP);
  const years = new Set();
  if (wantsRace) for (const year of raceYears()) years.add(year);
  if (wantsGender) for (const year of genderYears()) years.add(year);
  if (wantsLowIncome) for (const year of lowIncomeYears()) years.add(year);
  if (wantsIep) for (const year of iepYears()) years.add(year);
  if (!years.size) {
    for (const year of raceYears()) years.add(year);
    for (const year of genderYears()) years.add(year);
    for (const year of lowIncomeYears()) years.add(year);
    for (const year of iepYears()) years.add(year);
  }
  return [...years].sort((a, b) => a - b);
}

function raceMetersHtml(race) {
  const rows = (RACE_ORDER.filter((key) => race[key] > 0).length
    ? RACE_ORDER.filter((key) => race[key] > 0)
    : Object.keys(race).filter((key) => race[key] > 0)
  ).map((key) => [key, race[key]]);
  if (!rows.length) return `<p class="note">No race counts published.</p>`;
  const total = rows.reduce((sum, [, value]) => sum + value, 0) || 1;
  const max = Math.max(...rows.map(([, value]) => value)) || 1;
  return rows.map(([key, value]) => {
    const width = Math.max(2, (value / max) * 100);
    const tip = tipLines(raceLabel(key), [`${count(value)} students`, `${((value / total) * 100).toFixed(1)}% of reported`]);
    return `<div class="grade-row" data-tip="${escapeAttr(tip)}"><span>${escapeHtml(raceLabel(key))}</span><div class="meter"><span style="width:${width}%"></span></div><b>${count(value)}</b></div>`;
  }).join("");
}

function drawRace(host, race, title) {
  if (!host) return;
  if (!title) {
    host.innerHTML = raceMetersHtml(race);
    return;
  }
  const body = raceMetersHtml(race);
  if (body.startsWith("<p class=\"note\">No race")) {
    host.innerHTML = `<h3>${escapeHtml(title)}</h3>${body}`;
    return;
  }
  host.innerHTML = `<h3>${escapeHtml(title)}</h3>${body}`;
}

function drawRaceTrend(host, selectedKeys) {
  if (!host) return;
  const available = demoSeriesKeys();
  const selected = normalizeDemoSelection(selectedKeys, available);
  const years = demoYears(selected);
  if (years.length < 2) {
    const year = years[0];
    const block = year == null ? {} : (leaPack.years[String(year)] || {});
    const race = block.race || {};
    const gender = block.gender || {};
    const note = year == null
      ? ""
      : `<p class="note">Only ${yearLabel(year)} is published — not enough years for a trend.</p>`;
    const enrolled = enrollmentOf(block);
    const rowsHtml = demoMetersForYear(year, selected, enrolled);
    host.innerHTML = rowsHtml + note;
    return;
  }
  const series = selected.map((key, index) => {
    const slots = years.map((year) => demoValue(year, key));
    if (!slots.some((value) => value != null)) return null;
    return {
      name: demoSeriesLabel(key),
      color: demoSeriesColor(key, index),
      slots,
      pointYears: years,
      key,
    };
  }).filter(Boolean);
  if (!series.length) {
    host.innerHTML = `<p class="note">No group counts published for the selected series.</p>`;
    return;
  }
  const maxValue = Math.max(...series.flatMap((row) => row.slots.filter((value) => value != null)));
  const maxY = niceMax(maxValue);
  const ticks = [0, 0.5, 1].map((share) => Math.round(maxY * share));
  drawMultiLine(host, {
    categories: years.map((year) => String(year).slice(-2)),
    series,
    ariaLabel: "October 1 enrollment by student group",
    yMin: 0,
    yMax: maxY,
    yTicks: ticks,
    formatY: (value) => count(value),
    formatPoint: (row, _category, value, index) => {
      const year = row.pointYears[index];
      const enrolled = enrollmentOf(blockFor(year));
      const published = demoPct(year, row.key);
      const lines = [`${count(value)} students`];
      if (published != null) {
        lines.push(`${Number(published.pct).toFixed(1)}% of enrollment (${published.source})`);
      } else if (enrolled != null && enrolled > 0) {
        lines.push(`${((value / enrolled) * 100).toFixed(1)}% of enrollment`);
      }
      lines.push(`<span class="tip-muted">${escapeHtml(row.name)}</span>`);
      return tipLines(yearLabel(year), lines);
    },
    categoryLabel: (label) => "’" + label,
    left: 58,
    labelEvery: years.length > 16 ? 3 : years.length > 8 ? 2 : 1,
    showLegend: true,
  });
}

function demoMetersForYear(year, selected, enrolled) {
  if (year == null) return `<p class="note">No group counts published.</p>`;
  const block = leaPack.years[String(year)] || {};
  const rows = selected
    .map((key) => [key, demoValue(year, key)])
    .filter(([, value]) => value != null && value > 0);
  if (!rows.length) return `<p class="note">No group counts published.</p>`;
  const max = Math.max(...rows.map(([, value]) => value)) || 1;
  const shareBase = enrolled != null && enrolled > 0
    ? enrolled
    : rows.reduce((sum, [, value]) => sum + value, 0) || 1;
  return rows.map(([key, value]) => {
    const width = Math.max(2, (value / max) * 100);
    const tip = tipLines(demoSeriesLabel(key), [
      `${count(value)} students`,
      `${((value / shareBase) * 100).toFixed(1)}% of ${enrolled != null && enrolled > 0 ? "enrollment" : "reported groups"}`,
    ]);
    return `<div class="grade-row" data-tip="${escapeAttr(tip)}"><span>${escapeHtml(demoSeriesLabel(key))}</span><div class="meter"><span style="width:${width}%"></span></div><b>${count(value)}</b></div>`;
  }).join("");
}

function drawGender(host, gender, title = "Gender") {
  if (!host) return;
  const female = gender.Female || 0;
  const male = gender.Male || 0;
  const total = female + male;
  if (!total) {
    host.innerHTML = `<h3>${escapeHtml(title)}</h3><p class="note">No gender counts published.</p>`;
    return;
  }
  host.innerHTML = `<h3>${escapeHtml(title)}</h3>
    <div class="grade-row"><span>Female</span><div class="meter"><span style="width:${(female / total) * 100}%"></span></div><b>${count(female)}</b></div>
    <div class="grade-row"><span>Male</span><div class="meter"><span style="width:${(male / total) * 100}%"></span></div><b>${count(male)}</b></div>
    <p class="note">${pct(female / total)} female · ${pct(male / total)} male</p>`;
}

function operatingActual(block) {
  const actual = sumMap(block?.actual);
  if (actual == null) return null;
  const charter = Number(block.charterTuition || 0);
  return actual - charter;
}

/** Actuals minus charter tuition when the AFR is in. Otherwise the general fund budget
 * minus the latest published object 562, which is what makes it comparable to last year. */
function perStudentCost(block, year) {
  const enrolled = enrollmentOf(block);
  if (!enrolled) return null;
  const spending = operatingActual(block);
  if (spending != null) {
    return {
      value: spending / enrolled,
      basis: "actual",
      note: block?.charterTuition
        ? `<div class="note">Charter tuition removed</div>`
        : `<div class="note">Excludes charter tuition</div>`,
    };
  }
  const budget = sumMap(block?.budget);
  if (budget == null) return null;
  const charter = latestCharter(year);
  const amount = charter?.amount || 0;
  let note = "Budget";
  if (charter?.amount) {
    note = String(charter.year) === String(year)
      ? "Charter tuition removed"
      : "Estimated charter tuition removed";
  }
  return {
    value: (budget - amount) / enrolled,
    basis: "budget",
    note: `<div class="note">${note}</div>`,
  };
}

function latestCharter(year) {
  const current = blockFor(year);
  if (current?.charterTuition != null) {
    return { year: String(year), amount: Number(current.charterTuition) || 0 };
  }
  const earlier = Object.keys(leaPack?.years || {})
    .filter((candidate) => Number(candidate) < Number(year) && blockFor(candidate).charterTuition != null)
    .sort((a, b) => Number(a) - Number(b));
  const found = earlier.at(-1);
  if (!found) return null;
  return { year: found, amount: Number(blockFor(found).charterTuition) || 0 };
}

function yearDelta(current, prior, priorYear) {
  if (current == null || prior == null || prior === 0) return "";
  const change = (current - prior) / prior;
  const pct = (change * 100).toFixed(1) + "% vs " + yearLabel(priorYear);
  return `<div class="delta ${change < 0 ? "down" : ""}">${change > 0 ? "+" : ""}${pct}</div>`;
}

function yearDeltaPoints(current, prior, priorYear) {
  if (current == null || prior == null || priorYear == null) return "";
  const change = Number(current) - Number(prior);
  const text = `${change > 0 ? "+" : ""}${change.toFixed(1)} pts vs ${yearLabel(priorYear)}`;
  return `<div class="delta ${change < 0 ? "down" : ""}">${text}</div>`;
}

function priorIn(years, year) {
  const earlier = years.filter((value) => Number(value) < Number(year));
  return earlier.length ? earlier[earlier.length - 1] : null;
}

function act1Note(block) {
  const district = block.act1;
  const base = block.act1Base;
  if (district == null && base == null) return "";
  if (district == null) return `<div class="note">Act 1 base index ${percentPoints(base)}</div>`;
  const lines = [`<div class="note">Act 1 index ${percentPoints(district)}</div>`];
  if (base != null && Math.abs(district - base) >= 0.05) {
    lines.push(`<div class="note">Statewide base ${percentPoints(base)}</div>`);
  }
  return lines.join("");
}

function percentPoints(value) {
  return Number(value).toFixed(1) + "%";
}

function millNote(block, priorBlock, priorYear) {
  const rows = block.mills;
  if (!rows?.length) return "";
  const prior = priorBlock.mills || [];
  const split = rows.length > 1 || rows.some((row) => row.place);
  return rows.map((row) => {
    const where = [
      split && row.county ? row.county : "",
      row.place || "",
    ].filter(Boolean).join(" ");
    let text = `${where ? where + " " : ""}${formatMills(row.mills)} mills`;
    if (row.college) text += ` + ${formatMills(row.college)} college`;
    const before = prior.find((item) => item.county === row.county && (item.place || "") === (row.place || ""));
    if (before?.mills) {
      const change = (row.mills - before.mills) / before.mills;
      const pct = `${(change * 100).toFixed(1)}% vs ${yearLabel(priorYear)}`;
      text += ` · ${change > 0 ? "+" : ""}${pct}`;
    }
    return `<div class="note">${text}</div>`;
  }).join("");
}

function formatMills(value) {
  return Number(value).toFixed(4).replace(/\.?0+$/, "");
}

function formatRankValue(value, kind) {
  if (kind === "count") return count(value);
  if (kind === "pct") return Number(value).toFixed(1) + "%";
  if (kind === "money0") return money(value, 0);
  return money(value);
}

function rankBadge(label, rank, kind) {
  if (!rank?.rank || !rank?.of || !rank?.peers?.length) return "";
  const state = readState();
  const rows = rank.peers.map((peer, index) => {
    const place = index + 1;
    const mine = peer.aun === leaPack.aun;
    const value = escapeHtml(formatRankValue(peer.value, kind));
    const name = `${place}. ${escapeHtml(peer.name)}`;
    if (mine) {
      return `<div class="tip-rank tip-rank-you"><span>${name}</span><span>${value}</span></div>`;
    }
    const href = link({
      ...state,
      county: leaPack.county,
      aun: peer.aun,
      year: state.year,
      budget: "",
    });
    return `<a class="tip-rank" href="${escapeAttr(href)}"><span>${name}</span><span>${value}</span></a>`;
  }).join("");
  return `<span class="rank-wrap">
    <button type="button" class="rank" aria-label="${escapeAttr(`${label} county rank ${rank.rank} of ${rank.of}`)}">${rank.rank}/${rank.of}</button>
    <div class="rank-panel" role="tooltip">
      <div class="tip-title">${escapeHtml(label)} · ${escapeHtml(leaPack.county)} County</div>
      <div class="tip-sub">Rank ${rank.rank} of ${rank.of} (highest first). Click a name to open that LEA.</div>
      ${rows}
    </div>
  </span>`;
}

function stat(label, value, extra, title, rank, kind, options = {}) {
  const pick = options.pick;
  const selected = Boolean(options.selected);
  const classes = pick ? "stat stat-pick" : "stat";
  const pickAttrs = pick
    ? ` data-subject="${escapeAttr(pick)}" data-value="${escapeAttr(pick)}" aria-pressed="${selected ? "true" : "false"}" tabindex="0"`
    : "";
  return `<article class="${classes}"${pickAttrs}${title ? ` title="${escapeAttr(yearLabel(title))}"` : ""}>
    <div class="label-row"><div class="label">${escapeHtml(label)}</div>${rankBadge(label, rank, kind)}</div>
    <div class="value">${escapeHtml(value)}</div>${extra || ""}
  </article>`;
}

function trendSeriesLabel(code) {
  if (code === TREND_TOTAL) return "Total students";
  if (code === "K") return "Kindergarten";
  const grade = ENROLL_LADDER.find((row) => row.code === code);
  return grade ? `Grade ${grade.label}` : code;
}

function gradCell(year) {
  const cell = blockFor(year).graduation?.["4"];
  if (!cell || cell.rate == null || cell.grads == null || cell.cohort == null) return null;
  return cell;
}

function gradYears() {
  return Object.keys(leaPack.years || {})
    .map(Number)
    .sort((a, b) => a - b)
    .filter((year) => gradCell(year));
}

function gradGroupRate(year, code) {
  const value = blockFor(year).graduation?.groups?.["4"]?.[code];
  if (value == null || value === "") return null;
  const number = Number(value);
  return Number.isFinite(number) ? number : null;
}

function gradSeriesKeys() {
  if (!leaPack?.years) return [...GRAD_SERIES_CODES];
  const years = gradYears();
  return GRAD_SERIES.filter((row) => {
    if (row.code === GRAD_ALL) return years.length > 0;
    return years.some((year) => gradGroupRate(year, row.code) != null);
  }).map((row) => row.code);
}

function drawGradRate(years, selectedCodes = GRAD_DEFAULT) {
  const host = app.querySelector("#grad-trend");
  if (!host) return;
  const selected = normalizeGradSelection(selectedCodes, gradSeriesKeys());
  const series = selected.map((code) => {
    const meta = GRAD_SERIES.find((row) => row.code === code);
    const slots = years.map((year) => {
      if (code === GRAD_ALL) {
        const cell = gradCell(year);
        return cell ? Number(cell.rate) * 100 : null;
      }
      const rate = gradGroupRate(year, code);
      return rate == null ? null : rate * 100;
    });
    if (!slots.some((value) => value != null)) return null;
    return {
      name: meta.label,
      color: meta.color,
      slots,
      pointYears: years,
      code,
      emphasis: code === GRAD_ALL,
    };
  }).filter(Boolean);
  if (!series.length) {
    host.innerHTML = `<p class="note">No selected group has a published 4-year rate.</p>`;
    return;
  }
  series.sort((a, b) => Number(a.emphasis) - Number(b.emphasis));
  drawMultiLine(host, {
    categories: years.map((year) => String(year).slice(-2)),
    series,
    ariaLabel: "4-year cohort graduation rate by student group",
    yMin: 0,
    yMax: 100,
    yTicks: [0, 25, 50, 75, 100],
    formatY: (value) => Number(value).toFixed(0) + "%",
    formatPoint: (row, _category, value, index) => {
      const year = row.pointYears[index];
      const lines = [`${Number(value).toFixed(1)}%`];
      if (row.code === GRAD_ALL) {
        const cell = gradCell(year);
        if (cell) lines.push(`${count(cell.grads)} of ${count(cell.cohort)}`);
      }
      if (series.length > 1) lines.push(`<span class="tip-muted">${escapeHtml(row.name)}</span>`);
      return tipLines(yearLabel(year), lines);
    },
    categoryLabel: (label) => "’" + label,
    left: 48,
    labelEvery: years.length > 8 ? 2 : 1,
    showLegend: series.length > 1,
  });
}

function drawTrend(selectedCodes = TREND_DEFAULT) {
  const host = app.querySelector("#trend");
  const years = Object.keys(leaPack.years)
    .map(Number)
    .sort((a, b) => a - b)
    .filter((year) => {
      const block = leaPack.years[String(year)];
      return block?.grades && Object.keys(block.grades).length;
    });
  if (years.length < 2) {
    host.innerHTML = `<p class="note">Not enough years of enrollment to chart.</p>`;
    return;
  }
  const selected = normalizeTrendSelection(selectedCodes);
  const series = selected.map((code) => {
    const index = TREND_SERIES.findIndex((row) => row.code === code);
    const meta = TREND_SERIES[index];
    const slots = years.map((year) => {
      const block = leaPack.years[String(year)];
      if (code === TREND_TOTAL) return enrollmentOf(block);
      return gradeEnrollment(block, code);
    });
    if (!slots.some((value) => value != null)) return null;
    return {
      name: meta.label,
      color: code === TREND_TOTAL ? "#0c5c56" : COHORT_COLORS[index % COHORT_COLORS.length],
      dash: code === TREND_TOTAL ? null : COHORT_DASH[index % COHORT_DASH.length],
      slots,
      pointYears: years,
      code,
      emphasis: code === TREND_TOTAL,
    };
  }).filter(Boolean);
  if (!series.length) {
    host.innerHTML = `<p class="note">No selected series have published enrollment to chart.</p>`;
    return;
  }
  series.sort((a, b) => Number(a.emphasis) - Number(b.emphasis));
  const maxValue = Math.max(...series.flatMap((row) => row.slots.filter((value) => value != null)));
  const maxY = niceMax(maxValue);
  const ticks = [0, 0.5, 1].map((share) => Math.round(maxY * share));
  drawMultiLine(host, {
    categories: years.map((year) => String(year).slice(-2)),
    series,
    ariaLabel: "October 1 enrollment by year",
    yMin: 0,
    yMax: maxY,
    yTicks: ticks,
    formatY: (value) => count(value),
    formatPoint: (row, _category, value, index) => tipLines(yearLabel(row.pointYears[index]), [
      `${count(value)} students`,
      `<span class="tip-muted">${escapeHtml(trendSeriesLabel(row.code))}</span>`,
    ]),
    categoryLabel: (label) => "’" + label,
    left: 58,
    labelEvery: years.length > 16 ? 3 : years.length > 8 ? 2 : 1,
    showLegend: false,
  });
  const totalRow = series.find((row) => row.code === TREND_TOTAL);
  if (totalRow) {
    const points = totalRow.slots
      .map((value, index) => [years[index], value])
      .filter(([, value]) => value != null);
    if (points.length >= 2) {
      const [startYear, start] = points[0];
      const [endYear, end] = points[points.length - 1];
      const change = start ? (end - start) / start : null;
      const direction = change == null ? "" : change > 0 ? "up" : change < 0 ? "down" : "unchanged";
      const changeText = change == null || direction === "unchanged"
        ? "unchanged"
        : `${direction} ${(Math.abs(change) * 100).toFixed(1)}%`;
      host.insertAdjacentHTML("beforeend", `<p class="note">${count(end)} total students in ${yearLabel(endYear)}, ${changeText} from ${count(start)} in ${yearLabel(startYear)}.</p>`);
      return;
    }
  }
  host.insertAdjacentHTML("beforeend", `<p class="note">October 1 counts by selected grade. Kindergarten combines half-day and full-day.</p>`);
}

function drawAltEnrollment(selectedCodes = ALT_DEFAULT) {
  const host = app.querySelector("#alt-trend");
  if (!host) return;
  const years = Object.keys(leaPack.years)
    .map(Number)
    .sort((a, b) => a - b)
    .filter((year) => {
      const block = leaPack.years[String(year)];
      return enrollmentOf(block) != null
        || block?.charterAdm != null
        || block?.homeEducation != null;
    });
  if (!years.length) {
    host.innerHTML = `<p class="note">No district, charter, or home-education counts are published to chart.</p>`;
    return;
  }
  const selected = normalizeAltSelection(selectedCodes);
  const series = selected.map((code) => {
    const meta = ALT_SERIES.find((row) => row.code === code);
    const slots = years.map((year) => {
      const block = leaPack.years[String(year)];
      if (code === "district") return enrollmentOf(block);
      const value = Number(block?.[meta.field]);
      return Number.isFinite(value) ? value : null;
    });
    if (!slots.some((value) => value != null)) return null;
    return {
      name: meta.label,
      color: meta.color,
      dash: meta.dash,
      slots,
      pointYears: years,
      code,
      emphasis: code === "district",
    };
  }).filter(Boolean);
  if (!series.length) {
    host.innerHTML = `<p class="note">No selected series have published counts to chart.</p>`;
    return;
  }
  series.sort((a, b) => Number(a.emphasis) - Number(b.emphasis));
  const maxValue = Math.max(...series.flatMap((row) => row.slots.filter((value) => value != null)));
  const maxY = niceMax(maxValue);
  const ticks = [0, 0.5, 1].map((share) => Math.round(maxY * share));
  drawMultiLine(host, {
    categories: years.map((year) => String(year).slice(-2)),
    series,
    ariaLabel: "District enrollment versus charter ADM and home education",
    yMin: 0,
    yMax: maxY,
    yTicks: ticks,
    formatY: (value) => count(value),
    formatPoint: (row, _category, value, index) => tipLines(yearLabel(row.pointYears[index]), [
      `${count(value)} ${row.code === "charter" ? "ADM" : "students"}`,
      `<span class="tip-muted">${escapeHtml(row.name)}</span>`,
    ]),
    categoryLabel: (label) => "’" + label,
    left: 58,
    labelEvery: years.length > 16 ? 3 : years.length > 8 ? 2 : 1,
    showLegend: false,
  });
}

function niceMax(value) {
  if (!Number.isFinite(value) || value <= 0) return 1;
  const pow = 10 ** Math.floor(Math.log10(value));
  const scaled = value / pow;
  const nice = scaled <= 1 ? 1 : scaled <= 2 ? 2 : scaled <= 2.5 ? 2.5 : scaled <= 5 ? 5 : 10;
  return nice * pow;
}

function gradeEnrollment(block, code) {
  const grades = block?.grades;
  if (!grades) return null;
  if (code === "K") {
    const present = K_GRADE_CODES.map((key) => Number(grades[key])).filter((value) => value > 0);
    if (!present.length) return null;
    return present.reduce((sum, value) => sum + value, 0);
  }
  const value = Number(grades[code]);
  return value > 0 ? value : null;
}

function cohortAnchorCodes(year) {
  // One line per current grade on the K–12 ladder: K has 1 point, grade 12 has 13.
  return ENROLL_LADDER
    .filter((grade) => gradeEnrollment(blockFor(year), grade.code) != null)
    .map((grade) => grade.code);
}

function cohortEndpoints(row) {
  let start = null;
  let end = null;
  row.slots.forEach((value, index) => {
    if (value == null || !Number.isFinite(value)) return;
    const point = {
      value,
      index,
      year: row.pointYears[index],
      grade: ENROLL_LADDER[index],
    };
    if (!start) start = point;
    end = point;
  });
  return start && end && start.index !== end.index ? { start, end } : null;
}

function cohortChangeText(start, end) {
  if (!start || start === 0) return "unchanged";
  const change = (end - start) / start;
  if (change === 0) return "unchanged";
  const direction = change > 0 ? "up" : "down";
  return `${direction} ${(Math.abs(change) * 100).toFixed(1)}%`;
}

function gradeShortLabel(grade) {
  if (!grade) return "";
  return grade.label === "K" ? "kindergarten" : `grade ${grade.label}`;
}

function drawEnrollmentCohorts(year, selectedGrades = ENROLL_GRADE_CODES) {
  const host = app.querySelector("#cohort");
  if (!host) return;
  if (!year) {
    host.innerHTML = `<p class="note">Not enough grade counts to follow a class across years.</p>`;
    return;
  }
  const yearNum = Number(year);
  const selected = new Set(
    (selectedGrades.length ? selectedGrades : ENROLL_GRADE_CODES)
      .filter((code) => ENROLL_GRADE_CODES.includes(code)),
  );
  const codes = cohortAnchorCodes(year).filter((code) => selected.has(code));
  const series = codes.map((code) => {
    const terminal = ENROLL_LADDER.findIndex((grade) => grade.code === code);
    if (terminal < 0) return null;
    const pointYears = ENROLL_LADDER.map((_, index) => (index > terminal ? null : yearNum - (terminal - index)));
    const slots = pointYears.map((testYear, index) => (
      testYear == null ? null : gradeEnrollment(blockFor(testYear), ENROLL_LADDER[index].code)
    ));
    if (!slots.some((value) => value != null)) return null;
    const label = ENROLL_LADDER[terminal].label;
    return {
      name: label === "K" ? "K" : label,
      color: COHORT_COLORS[terminal % COHORT_COLORS.length],
      dash: COHORT_DASH[terminal % COHORT_DASH.length],
      slots,
      pointYears,
      terminal,
      emphasis: terminal === ENROLL_LADDER.length - 1,
    };
  }).filter(Boolean);
  if (!series.length) {
    host.innerHTML = `<p class="note">No selected classes have published grade counts to chart.</p>`;
    return;
  }
  const maxValue = Math.max(...series.flatMap((row) => row.slots.filter((value) => value != null)));
  const maxY = niceMax(maxValue);
  const annotated = series.map((row) => {
    const ends = cohortEndpoints(row);
    if (!ends) return { ...row, changeLabel: null, changeClass: "" };
    const change = ends.start.value ? (ends.end.value - ends.start.value) / ends.start.value : 0;
    return {
      ...row,
      changeLabel: cohortChangeText(ends.start.value, ends.end.value),
      changeClass: change < 0 ? "down" : change > 0 ? "up" : "",
      ends,
    };
  });
  drawMultiLine(host, {
    categories: ENROLL_LADDER.map((grade) => grade.label),
    series: annotated,
    ariaLabel: "Enrollment of current classes traced back through earlier grades",
    yMin: 0,
    yMax: maxY,
    yTicks: [0, 0.5, 1].map((share) => Math.round(maxY * share)),
    formatY: (value) => count(value),
    formatPoint: (row, category, value, index) => tipLines(
      row.name === "K" ? "Kindergarten class" : `Grade ${row.name} class`,
      [
        row.pointYears[index] ? yearLabel(row.pointYears[index]) : category,
        category === "K" ? "Kindergarten" : `Grade ${category}`,
        `${count(value)} students`,
      ],
    ),
    categoryLabel: (label) => (label === "K" ? "K" : label),
    left: 52,
    showLegend: false,
  });
  const summary = annotated.map((row) => {
    const className = row.name === "K" ? "Kindergarten" : `Grade ${row.name}`;
    if (!row.ends) {
      const value = row.slots.find((slot) => slot != null);
      const pointYear = row.pointYears.find((candidate) => candidate != null);
      if (value == null) return "";
      return `<li class="cohort-change" style="--series:${row.color}">
        <span class="cohort-change-name">${escapeHtml(className)}</span>
        <span class="cohort-change-text">${count(value)} students in ${yearLabel(pointYear)}</span>
      </li>`;
    }
    const { start, end } = row.ends;
    const tip = `${count(end.value)} now, ${row.changeLabel} from ${count(start.value)} in ${gradeShortLabel(start.grade)} (${yearLabel(start.year)})`;
    return `<li class="cohort-change ${row.changeClass}" style="--series:${row.color}">
      <span class="cohort-change-name">${escapeHtml(className)}</span>
      <span class="cohort-change-text">${escapeHtml(tip)}</span>
    </li>`;
  }).filter(Boolean).join("");
  if (summary) {
    host.insertAdjacentHTML("beforeend", `<ul class="cohort-change-list" aria-label="Class size change">${summary}</ul>`);
  }
}

function functionName(code) {
  return catalog.functions?.[code] || catalog.majors.find((major) => major.code === code)?.label || code;
}

function objectName(code) {
  return catalog.objectNames?.[code] || catalog.objects?.find((object) => object.code === code)?.label || code;
}

function schoolName(block, number) {
  return block.actualSchool?._names?.[number] || `School ${number}`;
}

function majorOf(code) {
  return code.slice(0, 1) + "000";
}

function summaryOf(code) {
  return code.slice(0, 2) + "00";
}

function amountOf(value) {
  if (value == null) return 0;
  if (typeof value === "number") return value;
  return Number(value.t || 0);
}

const SPEND_COLORS = {
  "1000": "#0c5c56",
  "2000": "#2f5f8a",
  "3000": "#8a6a2f",
  "4000": "#6b5344",
  "5000": "#a1622a",
};

function majorObjectCode(code) {
  return String(code).slice(0, 1) + "00";
}

function freshSpendTotals() {
  return { budget: 0, actual: 0, elem: 0, sec: 0, fed: 0, credits: [], sources: [] };
}

function addSpendAmount(bucket, series, value, source) {
  if (series === "actual" && source && !bucket.sources.includes(source)) bucket.sources.push(source);
  const amount = amountOf(value);
  if (amount < 0) {
    bucket.credits.push({ series, amount, source });
    return;
  }
  if (!amount) return;
  bucket[series] += amount;
  if (series === "actual" && value && typeof value === "object") {
    bucket.elem += Number(value.e || 0);
    bucket.sec += Number(value.s || 0);
    bucket.fed += Number(value.f || 0);
  }
}

function absorbSpend(into, from) {
  into.budget += from.budget;
  into.actual += from.actual;
  into.elem += from.elem;
  into.sec += from.sec;
  into.fed += from.fed;
  into.credits.push(...from.credits);
  for (const source of from.sources || []) {
    if (!into.sources.includes(source)) into.sources.push(source);
  }
}

function signedSpend(node, series) {
  const credit = (node.credits || []).filter((row) => row.series === series).reduce((sum, row) => sum + row.amount, 0);
  return (node[series] || 0) + credit;
}

function hasSpend(node, series) {
  if ((node[series] || 0) > 0) return true;
  return (node.credits || []).some((row) => row.series === series);
}

function wedgeValue(node, measure) {
  const amount = node[measure] || 0;
  return amount > 0 ? amount : 0;
}

function makeSpendNode(kind, fields) {
  return {
    kind,
    code: fields.code,
    segment: fields.segment,
    path: fields.path,
    parentPath: fields.parentPath || "",
    label: fields.label,
    account: fields.account || "",
    major: fields.major || "",
    budget: fields.budget || 0,
    actual: fields.actual || 0,
    elem: fields.elem || 0,
    sec: fields.sec || 0,
    fed: fields.fed || 0,
    credits: fields.credits || [],
    sources: fields.sources || [],
    children: fields.children || [],
    parent: null,
  };
}

function linkSpend(node) {
  for (const child of node.children) {
    child.parent = node;
    linkSpend(child);
  }
  return node;
}

function spendAlive(row) {
  return row.budget > 0 || row.actual > 0 || (row.credits || []).length > 0;
}

function schoolSpendNodes(schools, parentPath, major) {
  return [...schools.values()].filter(spendAlive).map((row) => makeSpendNode("school", {
    code: row.code,
    segment: `s:${row.code}`,
    path: `${parentPath}/s:${row.code}`,
    parentPath,
    label: row.name,
    account: `School ${row.code}`,
    major,
    actual: row.actual,
    credits: row.credits,
    sources: row.sources,
  }));
}

function detailSpendNode(row, pathPrefix, objectCode, major, accountFunction) {
  const path = `${pathPrefix}/${objectCode}/${row.code}`;
  return makeSpendNode("detail", {
    code: row.code,
    segment: row.code,
    path,
    parentPath: `${pathPrefix}/${objectCode}`,
    label: objectName(row.code),
    account: `${accountFunction}-${row.code}`,
    major,
    budget: row.budget,
    actual: row.actual,
    elem: row.elem,
    sec: row.sec,
    fed: row.fed,
    credits: row.credits,
    sources: row.sources,
    children: schoolSpendNodes(row.schools, path, major),
  });
}

function objectSpendChildren(row, pathPrefix, major, accountFunction) {
  const details = [...row.details.values()].filter(spendAlive);
  const path = `${pathPrefix}/${row.code}`;
  const split = details.length > 1 || (details.length === 1 && details[0].code !== row.code);
  if (split) return details.map((detail) => detailSpendNode(detail, pathPrefix, row.code, major, accountFunction));
  if (!details.length) return [];
  return schoolSpendNodes(details[0].schools, path, major);
}

function objectSpendNode(row, pathPrefix, major, accountFunction) {
  return makeSpendNode("object", {
    code: row.code,
    segment: row.code,
    path: `${pathPrefix}/${row.code}`,
    parentPath: pathPrefix,
    label: objectName(row.code),
    account: `${accountFunction}-${row.code}`,
    major,
    budget: row.budget,
    actual: row.actual,
    elem: row.elem,
    sec: row.sec,
    fed: row.fed,
    credits: row.credits,
    sources: row.sources,
    children: objectSpendChildren(row, pathPrefix, major, accountFunction),
  });
}

function subfunctionSpendNode(row, family, major) {
  const path = `${family}/${row.code}`;
  return makeSpendNode("function", {
    code: row.code,
    segment: row.code,
    path,
    parentPath: family,
    label: functionName(row.code),
    account: row.code,
    major,
    budget: row.budget,
    actual: row.actual,
    elem: row.elem,
    sec: row.sec,
    fed: row.fed,
    credits: row.credits,
    sources: row.sources,
    children: [...row.objects.values()].filter(spendAlive).map((object) => objectSpendNode(object, path, major, row.code)),
  });
}

function familySpendNode(row, major) {
  const subs = [...row.subs.values()].filter(spendAlive).map((sub) => subfunctionSpendNode(sub, row.code, major));
  const objects = [...row.objects.values()].filter(spendAlive).map((object) => objectSpendNode(object, row.code, major, row.code));
  return makeSpendNode("family", {
    code: row.code,
    segment: row.code,
    path: row.code,
    parentPath: major,
    label: functionName(row.code),
    account: row.code,
    major,
    budget: row.budget,
    actual: row.actual,
    elem: row.elem,
    sec: row.sec,
    fed: row.fed,
    credits: row.credits,
    sources: row.sources,
    children: [...subs, ...objects],
  });
}

function majorSpendLabel(code) {
  return catalog.majors.find((major) => major.code === code)?.label || functionName(code);
}

// Budget stays at the published function and major object. Actual keeps the
// posted subfunction (1110, 2823) under that function, then the posted object.
// A parent account is not added on top of those leaves.
function buildSpendTree(block) {
  const families = new Map();
  const ensureFamily = (fn) => {
    const code = summaryOf(fn);
    let row = families.get(code);
    if (!row) {
      row = { ...freshSpendTotals(), code, objects: new Map(), subs: new Map() };
      families.set(code, row);
    }
    return row;
  };
  const ensureSub = (family, fn) => {
    let row = family.subs.get(fn);
    if (!row) {
      row = { ...freshSpendTotals(), code: fn, objects: new Map() };
      family.subs.set(fn, row);
    }
    return row;
  };
  const ensureObject = (owner, objectCode) => {
    const code = majorObjectCode(objectCode);
    let row = owner.objects.get(code);
    if (!row) {
      row = { ...freshSpendTotals(), code, details: new Map() };
      owner.objects.set(code, row);
    }
    return row;
  };
  const ensureDetail = (object, objectCode) => {
    let row = object.details.get(objectCode);
    if (!row) {
      row = { ...freshSpendTotals(), code: objectCode, schools: new Map() };
      object.details.set(objectCode, row);
    }
    return row;
  };
  const take = (fn, objectCode, series, value) => {
    const family = ensureFamily(fn);
    const postedAtFamily = summaryOf(fn) === String(fn);
    const owner = series === "actual" && !postedAtFamily ? ensureSub(family, String(fn)) : family;
    const object = ensureObject(owner, objectCode);
    const detail = ensureDetail(object, objectCode);
    addSpendAmount(family, series, value, fn);
    if (owner !== family) addSpendAmount(owner, series, value, fn);
    addSpendAmount(object, series, value, fn);
    addSpendAmount(detail, series, value, fn);
    return detail;
  };

  for (const [fn, objects] of Object.entries(block.budgetDetail || {})) {
    for (const [objectCode, value] of Object.entries(objects)) take(fn, objectCode, "budget", value);
  }
  for (const [fn, objects] of Object.entries(block.actualDetail || {})) {
    for (const [objectCode, value] of Object.entries(objects)) {
      const detail = take(fn, objectCode, "actual", value);
      const schools = (block.actualSchool || {})[fn]?.[objectCode] || {};
      for (const [number, schoolValue] of Object.entries(schools)) {
        let school = detail.schools.get(number);
        if (!school) {
          school = { ...freshSpendTotals(), code: number, name: schoolName(block, number) };
          detail.schools.set(number, school);
        }
        addSpendAmount(school, "actual", schoolValue, fn);
      }
    }
  }

  const majorRows = new Map();
  for (const family of families.values()) {
    if (!spendAlive(family)) continue;
    const majorCode = majorOf(family.code);
    let major = majorRows.get(majorCode);
    if (!major) {
      major = { ...freshSpendTotals(), code: majorCode, families: [] };
      majorRows.set(majorCode, major);
    }
    absorbSpend(major, family);
    major.families.push(family);
  }

  const root = makeSpendNode("root", {
    code: "",
    segment: "",
    path: "",
    label: "General fund",
    account: "Fund 10",
    children: [...majorRows.values()].map((row) => makeSpendNode("major", {
      code: row.code,
      segment: row.code,
      path: row.code,
      label: majorSpendLabel(row.code),
      account: row.code,
      major: row.code,
      budget: row.budget,
      actual: row.actual,
      elem: row.elem,
      sec: row.sec,
      fed: row.fed,
      credits: row.credits,
      sources: row.sources,
      children: row.families.map((family) => familySpendNode(family, row.code)),
    })),
  });
  for (const major of root.children) absorbSpend(root, major);
  return linkSpend(root);
}

function findSpendNode(root, focus) {
  const parts = String(focus || "").split("/").filter(Boolean);
  if (!parts.length) return root;
  let node = root;
  if (parts[0].endsWith("000") && parts[0].length === 4) {
    node = root.children.find((child) => child.segment === parts[0]) || root;
    if (node === root) return root;
    parts.shift();
  } else {
    const major = root.children.find((child) => child.code === majorOf(parts[0]));
    const family = major?.children.find((child) => child.segment === parts[0]);
    if (family) {
      node = family;
      parts.shift();
    } else {
      const sub = major?.children
        .flatMap((child) => child.children)
        .find((child) => child.kind === "function" && child.segment === parts[0]);
      if (!sub) return root;
      node = sub;
      parts.shift();
    }
  }
  for (const part of parts) {
    const next = node.children.find((child) => child.segment === part);
    if (!next) return node;
    node = next;
  }
  return node;
}

function visibleSpendNode(node, measure) {
  let current = node;
  while (current && current.kind !== "root" && !hasSpend(current, measure)) current = current.parent;
  return current || node;
}

function orderedChildren(node, measure) {
  const kids = node.children.filter((child) => wedgeValue(child, measure) > 0);
  if (kids.length === 1 && kids[0].code === node.code && Math.abs(wedgeValue(kids[0], measure) - wedgeValue(node, measure)) < 1) {
    return [];
  }
  if (node.kind === "root") {
    const order = new Map((catalog.majors || []).map((major, index) => [major.code, index]));
    kids.sort((a, b) => (order.get(a.code) ?? 99) - (order.get(b.code) ?? 99) || a.label.localeCompare(b.label));
    return kids;
  }
  kids.sort((a, b) => wedgeValue(b, measure) - wedgeValue(a, measure) || a.label.localeCompare(b.label));
  return kids;
}

function spendDepth(node) {
  let depth = 0;
  let current = node;
  while (current?.parent && current.parent.kind !== "root") {
    depth += 1;
    current = current.parent;
  }
  return depth;
}

function mixHex(hex, toward, amount) {
  const read = (value) => {
    const n = value.slice(1);
    return [0, 2, 4].map((index) => parseInt(n.slice(index, index + 2), 16));
  };
  const start = read(hex);
  const end = read(toward);
  const mixed = start.map((channel, index) => Math.round(channel + (end[index] - channel) * amount));
  return `#${mixed.map((channel) => channel.toString(16).padStart(2, "0")).join("")}`;
}

function sliceFill(node, index) {
  const base = SPEND_COLORS[node.major] || "#5e574c";
  const depth = spendDepth(node);
  if (depth <= 0) return base;
  const step = (index % 4) * 0.1;
  const start = depth === 1 ? 0.12 : 0.38;
  return mixHex(base, "#f4efe4", Math.min(0.78, start + step));
}

function fillOf(node, measure) {
  if (!node.parent) return SPEND_COLORS[node.major] || "#0c5c56";
  const siblings = orderedChildren(node.parent, measure);
  const index = Math.max(0, siblings.findIndex((child) => child.path === node.path));
  return sliceFill(node, index);
}

function inkFor(fill) {
  const channels = [0, 2, 4].map((index) => parseInt(fill.slice(1 + index, 3 + index), 16));
  const lum = (0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2]) / 255;
  return lum > 0.64 ? "#1c1915" : "#fffdf8";
}

function seriesPublished(block, series) {
  const map = block[series];
  if (map && Object.keys(map).some((key) => amountOf(map[key]))) return true;
  const detail = series === "budget" ? block.budgetDetail : block.actualDetail;
  return Object.keys(detail || {}).length > 0;
}

function spendMeasure(block, state) {
  const yearActual = seriesPublished(block, "actual");
  const yearBudget = seriesPublished(block, "budget");
  if (state.spend === "budget" && yearBudget) return "budget";
  if (state.spend === "actual" && yearActual) return "actual";
  if (yearActual) return "actual";
  return "budget";
}

function pctText(part, whole) {
  if (!whole) return "";
  const pct = (Math.abs(part) / Math.abs(whole)) * 100;
  if (pct >= 10) return `${Math.round(pct)}%`;
  if (pct >= 0.1) return `${pct.toFixed(1)}%`;
  return "<0.1%";
}

function spendLines(text, max) {
  const words = String(text || "").split(/\s+/).filter(Boolean);
  const lines = [];
  let line = "";
  for (const word of words) {
    const next = line ? `${line} ${word}` : word;
    if (line && next.length > max) {
      lines.push(line);
      line = word;
    } else {
      line = next;
    }
  }
  if (line) lines.push(line);
  return lines;
}

function ringPath(cx, cy, r0, r1, a0, a1) {
  const span = a1 - a0;
  if (span >= Math.PI * 2 - 0.0001) {
    return `M ${cx - r1} ${cy} A ${r1} ${r1} 0 1 1 ${cx + r1} ${cy} A ${r1} ${r1} 0 1 1 ${cx - r1} ${cy} M ${cx - r0} ${cy} A ${r0} ${r0} 0 1 0 ${cx + r0} ${cy} A ${r0} ${r0} 0 1 0 ${cx - r0} ${cy} Z`;
  }
  const point = (radius, angle) => [cx + radius * Math.cos(angle), cy + radius * Math.sin(angle)];
  const [x0, y0] = point(r1, a0);
  const [x1, y1] = point(r1, a1);
  const [x2, y2] = point(r0, a1);
  const [x3, y3] = point(r0, a0);
  const large = span > Math.PI ? 1 : 0;
  const n = (value) => value.toFixed(2);
  return `M ${n(x0)} ${n(y0)} A ${r1} ${r1} 0 ${large} 1 ${n(x1)} ${n(y1)} L ${n(x2)} ${n(y2)} A ${r0} ${r0} 0 ${large} 0 ${n(x3)} ${n(y3)} Z`;
}

function layoutRing(nodes, measure, a0, a1) {
  const total = nodes.reduce((sum, node) => sum + wedgeValue(node, measure), 0);
  if (!total) return [];
  let angle = a0;
  return nodes.map((node, index) => {
    const span = (wedgeValue(node, measure) / total) * (a1 - a0);
    const start = angle;
    const end = index === nodes.length - 1 ? a1 : angle + span;
    angle = end;
    return { node, index, start, end, fill: sliceFill(node, index) };
  });
}

function spendAmountText(node, series, published) {
  if (!published) return "Not published";
  if (!hasSpend(node, series)) return series === "budget" ? "Not in the budget" : "Not in the actual";
  return moneyFull(signedSpend(node, series));
}

function seriesPhrase(label, node, series, published) {
  if (!published) return `${label} not published`;
  if (!hasSpend(node, series)) return series === "budget" ? "Not in the budget" : "Not in the actual";
  return `${label} ${moneyFull(signedSpend(node, series))}`;
}

function spendTip(node, measure, yearActual, yearBudget) {
  const lines = [];
  if (node.account) lines.push(`<span class="tip-muted">${escapeHtml(node.account)}</span>`);
  lines.push(seriesPhrase("Actual", node, "actual", yearActual));
  lines.push(seriesPhrase("Budget", node, "budget", yearBudget));
  if (node.parent) {
    const share = pctText(wedgeValue(node, measure), wedgeValue(node.parent, measure));
    if (share) lines.push(`${share} of ${escapeHtml(node.parent.label)}`);
  }
  if (orderedChildren(node, measure).length) lines.push(`<span class="tip-muted">Click to open</span>`);
  return tipLines(node.label, lines);
}

let sunLabelId = 0;

function wedgeName(label) {
  const text = String(label || "").replace(/\s+/g, " ").trim();
  const letters = text.replace(/[^A-Za-z]/g, "");
  if (!(letters.length > 3 && letters === letters.toUpperCase())) return text;
  return text.toLowerCase().replace(/\b([a-z])([a-z]*)/g, (_, first, rest) => (
    rest.length <= 1 ? (first + rest).toUpperCase() : first.toUpperCase() + rest
  ));
}

function fitSpendLabel(label, maxChars) {
  if (maxChars < 3) return "";
  if (label.length <= maxChars) return label;
  return `${label.slice(0, maxChars - 1).trimEnd()}…`;
}

function wedgeLabel(slice, radius, fontSize) {
  const span = slice.end - slice.start;
  const arcPx = radius * span * 0.9;
  const size = arcPx < 78 ? Math.min(fontSize, 9.5) : fontSize;
  const maxChars = Math.floor(arcPx / (size * 0.5));
  const name = fitSpendLabel(wedgeName(slice.node.label), maxChars);
  if (!name) return "";
  const mid = (slice.start + slice.end) / 2;
  const half = Math.min(span * 0.46, 1.15);
  let start = mid - half;
  let end = mid + half;
  const below = Math.sin(mid) > 0;
  if (below) [start, end] = [end, start];
  const point = (angle) => [210 + radius * Math.cos(angle), 210 + radius * Math.sin(angle)];
  const [x0, y0] = point(start);
  const [x1, y1] = point(end);
  const id = `sun-arc-${sunLabelId += 1}`;
  const sweep = below ? 0 : 1;
  const arc = `M ${x0.toFixed(2)} ${y0.toFixed(2)} A ${radius} ${radius} 0 0 ${sweep} ${x1.toFixed(2)} ${y1.toFixed(2)}`;
  const cls = size < 11 ? "sun-label sun-label-sm" : "sun-label";
  return `<path id="${id}" class="sun-arc" d="${arc}"></path><text class="${cls}" fill="${inkFor(slice.fill)}"><textPath href="#${id}" startOffset="50%" text-anchor="middle">${escapeHtml(name)}</textPath></text>`;
}

function wedgeMarkup(slice, r0, r1, measure, yearActual, yearBudget) {
  const path = ringPath(210, 210, r0, r1, slice.start, slice.end);
  const tip = spendTip(slice.node, measure, yearActual, yearBudget);
  const radius = (r0 + r1) / 2;
  const fontSize = r1 - r0 > 50 ? 12 : 10.5;
  return `<path class="sun-wedge" fill="${slice.fill}" fill-rule="evenodd" stroke="#f3efe6" stroke-width="1.5" d="${path}" data-budget="${escapeAttr(slice.node.path)}" data-slice="${escapeAttr(slice.node.path)}" data-tip="${escapeAttr(tip)}"></path>${wedgeLabel(slice, radius, fontSize)}`;
}

function centerMarkup(node, measure, diskFill) {
  const lines = spendLines(node.label, 18).slice(0, 2);
  const amount = money(signedSpend(node, measure));
  const rows = [...lines, amount];
  const start = 210 - ((rows.length - 1) * 20) / 2;
  const ink = diskFill ? inkFor(diskFill) : "#1c1915";
  const muted = diskFill ? ink : "#5e574c";
  const text = rows.map((row, index) => {
    const y = start + index * 20;
    const isValue = index === lines.length;
    const cls = isValue ? "sun-value" : "sun-center-label";
    const fill = isValue ? ink : muted;
    return `<text class="${cls}" x="210" y="${y.toFixed(1)}" fill="${fill}" text-anchor="middle" dominant-baseline="middle">${escapeHtml(row)}</text>`;
  }).join("");
  const parent = node.parent;
  const backTip = tipLines(parent?.label || "All functions", [`<span class="tip-muted">Click to go back</span>`]);
  const back = parent
    ? ` class="sun-back" data-budget="${escapeAttr(parent.path || "")}" data-tip="${escapeAttr(backTip)}"`
    : "";
  const radius = diskFill ? 168 : 74;
  const fill = diskFill || "#fffdf8";
  return `<circle cx="210" cy="210" r="${radius}" fill="${fill}"${back}></circle>${text}`;
}

function spendCrumb(node) {
  const chain = [];
  let current = node;
  while (current && current.kind !== "root") {
    chain.unshift(current);
    current = current.parent;
  }
  if (!chain.length) return `<div class="drill"><span class="here">All functions</span></div>`;
  const parts = [`<button type="button" data-budget="">All functions</button>`];
  chain.forEach((item, index) => {
    if (index === chain.length - 1) parts.push(`<span class="here">${escapeHtml(item.label)}</span>`);
    else parts.push(`<button type="button" data-budget="${escapeAttr(item.path)}">${escapeHtml(item.label)}</button>`);
  });
  return `<div class="drill">${parts.join(" / ")}</div>`;
}

function spendCard(node, measure, root, yearActual, yearBudget) {
  const amount = money(signedSpend(node, measure));
  const parentShare = node.parent ? pctText(signedSpend(node, measure), signedSpend(node.parent, measure)) : "";
  const fundShare = node.kind === "root" ? "" : pctText(signedSpend(node, measure), signedSpend(root, measure));
  let share = "The whole general fund";
  if (node.parent && node.parent.kind !== "root" && parentShare && fundShare) {
    share = `${parentShare} of ${node.parent.label} · ${fundShare} of the general fund`;
  } else if (parentShare) {
    share = `${parentShare} of the general fund`;
  }
  const pair = (label, series, published) => `<div><span>${label}</span><b>${escapeHtml(spendAmountText(node, series, published))}</b></div>`;
  let gap = "";
  if (yearActual && yearBudget && hasSpend(node, "actual") && hasSpend(node, "budget")) {
    const diff = signedSpend(node, "actual") - signedSpend(node, "budget");
    gap = Math.abs(diff) < 1
      ? "Actual matches the budget"
      : `Actual is ${money(Math.abs(diff))} ${diff > 0 ? "above" : "below"} the budget`;
  }
  const splitBits = [];
  if (node.elem) splitBits.push(`Elementary ${money(node.elem)}`);
  if (node.sec) splitBits.push(`Secondary ${money(node.sec)}`);
  if (node.fed) splitBits.push(`Federal ${money(node.fed)}`);
  const extraSources = [...new Set(node.sources || [])].filter((code) => code !== node.code).sort();
  const source = node.kind !== "root" && node.kind !== "major" && node.kind !== "school" && extraSources.length
    ? `Actual lines ${extraSources.slice(0, 4).join(", ")}${extraSources.length > 4 ? `, and ${extraSources.length - 4} more` : ""}.`
    : "";
  return `<div class="sun-card">
    <p class="sun-kicker">${measure === "actual" ? "Actual" : "Budget"}${node.account ? ` · ${escapeHtml(node.account)}` : ""}</p>
    <p class="sun-figure">${escapeHtml(amount)}</p>
    <p class="sun-shareline">${escapeHtml(share)}</p>
    <div class="sun-pair">
      ${pair("Actual", "actual", yearActual)}
      ${pair("Budget", "budget", yearBudget)}
    </div>
    ${gap ? `<p class="sun-gap">${escapeHtml(gap)}</p>` : ""}
    ${splitBits.length ? `<p class="sun-split">${escapeHtml(splitBits.join(" · "))}</p>` : ""}
    ${source ? `<p class="sun-source">${escapeHtml(source)}</p>` : ""}
  </div>`;
}

function spendList(nodes, measure, yearActual, yearBudget) {
  if (!nodes.length) return `<p class="note">No further breakdown is published under this slice.</p>`;
  const total = nodes.reduce((sum, node) => sum + wedgeValue(node, measure), 0);
  return `<div class="sun-list">${nodes.map((node, index) => {
    const fill = sliceFill(node, index);
    const tip = spendTip(node, measure, yearActual, yearBudget);
    return `<button type="button" class="sun-row" data-budget="${escapeAttr(node.path)}" data-slice="${escapeAttr(node.path)}" data-tip="${escapeAttr(tip)}">
      <span class="sun-swatch" style="background:${fill}"></span>
      <span class="sun-name">${escapeHtml(node.label)}<small>${escapeHtml(node.account || node.code)}</small></span>
      <span class="sun-pct">${pctText(wedgeValue(node, measure), total)}</span>
      <span class="sun-amt">${escapeHtml(money(wedgeValue(node, measure)))}</span>
    </button>`;
  }).join("")}</div>`;
}

function creditNote(node, measure) {
  const credits = (node.credits || []).filter((row) => row.series === measure);
  if (!credits.length) return "";
  const total = credits.reduce((sum, row) => sum + row.amount, 0);
  if (Math.abs(total) < 100) return "";
  return `A published ${measure} credit of ${moneyFull(total)} is left off the wedges.`;
}

function childGapNote(node, measure) {
  const kids = node.children.filter((child) => wedgeValue(child, measure) > 0);
  if (!kids.length) return "";
  const sum = kids.reduce((total, child) => total + wedgeValue(child, measure), 0);
  const parent = wedgeValue(node, measure);
  if (!parent || Math.abs(parent - sum) < 1) return "";
  return `These pieces add to ${moneyFull(sum)}. This level is ${moneyFull(parent)}.`;
}

function reconcileNote(block, node, measure) {
  const published = node.kind === "root"
    ? sumMap(block[measure])
    : node.kind === "major" ? block[measure]?.[node.code] : null;
  if (published == null) return "";
  const built = signedSpend(node, measure);
  if (Math.abs(published - built) < 1) return "";
  return `The published total for this level is ${moneyFull(published)}.`;
}

function drawSpend(block, state) {
  const host = app.querySelector("#spend");
  if (!host) return;
  const measure = spendMeasure(block, state);
  const yearActual = seriesPublished(block, "actual");
  const yearBudget = seriesPublished(block, "budget");
  if (!yearActual && !yearBudget) {
    host.innerHTML = `<p class="note">No general-fund budget or actual is published for this year.</p>`;
    return;
  }
  const root = buildSpendTree(block);
  const focus = visibleSpendNode(findSpendNode(root, state.budget || ""), measure);
  if ((state.budget || "") !== focus.path) {
    state.budget = focus.path;
    writeUrl(state, "replace");
  }
  sunLabelId = 0;
  const innerNodes = orderedChildren(focus, measure);
  const inner = layoutRing(innerNodes, measure, -Math.PI / 2, -Math.PI / 2 + Math.PI * 2);
  const outer = inner.flatMap((slice) => layoutRing(orderedChildren(slice.node, measure), measure, slice.start, slice.end));
  const wedges = [
    ...outer.map((slice) => wedgeMarkup(slice, 160, 198, measure, yearActual, yearBudget)),
    ...inner.map((slice) => wedgeMarkup(slice, 86, 152, measure, yearActual, yearBudget)),
  ].join("");
  const disk = inner.length ? "" : fillOf(focus, measure);
  const chart = `<svg class="sun-chart" viewBox="0 0 420 420" role="img" aria-label="${escapeAttr(`${focus.label}, ${measure}`)}">${wedges}${centerMarkup(focus, measure, inner.length ? "" : disk)}</svg>`;
  const measures = yearActual && yearBudget
    ? `<div class="chips sun-measures" aria-label="Amounts to draw">${[["actual", "Actual"], ["budget", "Budget"]].map(([id, label]) => `<button type="button" class="chip" data-spend="${id}" data-value="${id}" aria-pressed="${measure === id ? "true" : "false"}">${label}</button>`).join("")}</div>`
    : "";
  const notes = [reconcileNote(block, focus, measure), childGapNote(focus, measure), creditNote(focus, measure)].filter(Boolean);
  const footnote = measure === "budget"
    ? "Wedge size is the share of this view in the adopted general-fund budget. The budget stops at the function and the major object. Actual opens each published subfunction and object, then the building when PDE reported one."
    : "Wedge size is the share of this view in the general-fund actual. Each step is a published account: subfunction, then object, then building when PDE reported one. Elementary, secondary, and federal are a split of that actual, not extra dollars. A missing account is left out.";
  host.innerHTML = `${measures}${spendCrumb(focus)}
    <div class="sun-layout">${chart}${spendCard(focus, measure, root, yearActual, yearBudget)}</div>
    ${spendList(innerNodes, measure, yearActual, yearBudget)}
    ${notes.map((note) => `<p class="note">${escapeHtml(note)}</p>`).join("")}
    <p class="note">${footnote}</p>`;
}

function drawGrades(grades) {
  const host = app.querySelector("#grades");
  const rows = catalog.grades.filter((grade) => grades[grade.code]);
  if (!rows.length) {
    host.innerHTML = `<p class="note">No grade counts published.</p>`;
    return;
  }
  const max = Math.max(...rows.map((grade) => grades[grade.code])) || 1;
  host.innerHTML = rows.map((grade) => {
    const value = grades[grade.code];
    const width = Math.max(2, (value / max) * 100);
    const tip = tipLines(grade.label, [`${count(value)} students`]);
    return `<div class="grade-row" data-tip="${escapeAttr(tip)}"><span>${escapeHtml(grade.label)}</span><div class="meter"><span style="width:${width}%"></span></div><b>${count(value)}</b></div>`;
  }).join("");
}

function drawSchools(schools, sort) {
  const body = app.querySelector("#school-rows");
  const rows = [...(schools || [])];
  rows.sort((a, b) => sort === "name" ? a.name.localeCompare(b.name) : b.enrollment - a.enrollment || a.name.localeCompare(b.name));
  const max = Math.max(1, ...rows.map((school) => school.enrollment));
  setPressed(".schools thead button", (value) => value === sort);
  body.innerHTML = rows.map((school) => {
    const tip = tipLines(school.name, [`School ${school.number}`, `${count(school.enrollment)} students`]);
    return `<tr data-tip="${escapeAttr(tip)}">
    <td>${escapeHtml(school.name)}<div class="sub">${escapeHtml(school.number)}</div></td>
    <td><div class="meter"><span style="width:${(school.enrollment / max) * 100}%"></span></div></td>
    <td class="num">${count(school.enrollment)}</td>
  </tr>`;
  }).join("") || `<tr><td colspan="3" class="note">No school rows published.</td></tr>`;
}

function drawExperience(experience, mode) {
  const host = app.querySelector("#experience");
  if (!host) return;
  const groups = catalog.salaryGroups || [];
  const edges = catalog.experienceEdges || [];
  const modeLabel = mode === "edu" ? "years in education" : "years in this LEA";
  const otherLabel = mode === "edu" ? "years in this LEA" : "years in education";
  const cards = groups.map((group) => {
    const stats = experience[group.id]?.[mode];
    if (!stats || !stats.n) {
      return `<article class="panel salary-card"><h3>${escapeHtml(group.label)}</h3><p class="note">No ${escapeHtml(modeLabel)} published for this year.</p></article>`;
    }
    const hist = experienceHist(group.label, stats, edges, mode);
    const other = mode === "lea" ? experience[group.id]?.edu : experience[group.id]?.lea;
    const note = other?.mean != null
      ? `Mean ${Number(other.mean).toFixed(1)} ${otherLabel}`
      : "";
    return `<article class="panel salary-card">
      <h3>${escapeHtml(group.label)}</h3>
      <div class="people">${count(stats.n)} full-time staff</div>
      <div class="salary-stats">
        <div><div class="label">Lowest</div><div class="value">${escapeHtml(yearsLabel(stats.min))}</div></div>
        <div><div class="label">Mean</div><div class="value">${escapeHtml(yearsLabel(stats.mean, 1))}</div></div>
        <div><div class="label">Median</div><div class="value">${escapeHtml(yearsLabel(stats.median))}</div></div>
        <div><div class="label">Highest</div><div class="value">${escapeHtml(yearsLabel(stats.max))}</div></div>
      </div>
      ${hist}
      ${note ? `<p class="note">${escapeHtml(note)}</p>` : ""}
    </article>`;
  });
  if (!groups.some((group) => experience[group.id]?.[mode]?.n)) {
    host.innerHTML = `<p class="note">No full-time professional staff experience for this year. PDE’s classified support staff (aides and similar) are published only as counts, not individual tenure.</p>`;
    return;
  }
  host.innerHTML = `<div class="salary-grid">${cards.join("")}</div>
    <p class="note">Full-time only (FTE 100%), same staff as the salary charts. Toggle between years employed in this LEA and years in education. Hover a bar for mean salary, ${escapeHtml(otherLabel)}, and degree mix in that band.</p>`;
}

function drawSalaries(salaries, retention) {
  const host = app.querySelector("#salaries");
  if (!host) return;
  const groups = catalog.salaryGroups || [];
  const edges = catalog.salaryEdges || [];
  const cards = groups.map((group) => {
    const stats = salaries[group.id];
    if (!stats || !stats.n) {
      return `<article class="panel salary-card"><h3>${escapeHtml(group.label)}</h3><p class="note">No full-time salaries in this year.</p></article>`;
    }
    const hist = salaryHist(group.label, stats, edges);
    const tenure = [
      stats.leaYears != null ? `Mean ${Number(stats.leaYears).toFixed(1)} years in this LEA` : null,
      stats.eduYears != null ? `mean ${Number(stats.eduYears).toFixed(1)} in education` : null,
      stats.mastersPct != null ? `${Math.round(stats.mastersPct)}% master’s+` : null,
      stats.retention != null ? `${pct(stats.retention)} returned next year` : null,
    ].filter(Boolean).join(" · ");
    return `<article class="panel salary-card">
      <h3>${escapeHtml(group.label)}</h3>
      <div class="people">${count(stats.n)} full-time staff</div>
      <div class="salary-stats">
        <div><div class="label">Lowest</div><div class="value">${escapeHtml(money(stats.min, 0))}</div></div>
        <div><div class="label">Mean</div><div class="value">${escapeHtml(money(stats.mean, 0))}</div></div>
        <div><div class="label">Median</div><div class="value">${escapeHtml(money(stats.median, 0))}</div></div>
        <div><div class="label">Highest</div><div class="value">${escapeHtml(money(stats.max, 0))}</div></div>
      </div>
      ${hist}
      ${tenure ? `<p class="note">${escapeHtml(tenure)}</p>` : ""}
    </article>`;
  });
  if (!groups.some((group) => salaries[group.id]?.n)) {
    host.innerHTML = `<p class="note">No full-time professional staff salaries for this year. PDE’s classified support staff (aides and similar) are published only as counts, not individual salaries.</p>`;
    return;
  }
  const retentionLine = retention?.rate != null
    ? `<p class="retention"><strong>${pct(retention.rate)}</strong> of full-time professional staff returned to this LEA in ${yearLabel(retention.nextYear)} (${count(retention.stayed)} of ${count(retention.base)}).</p>`
    : `<p class="note">Retention into the following year is not published yet for this staff year.</p>`;
  host.innerHTML = `${retentionLine}<div class="salary-grid">${cards.join("")}</div>
    <p class="note">Full-time only (FTE 100%). Part-time and overload assignments are excluded. Elementary includes kindergarten and pre-K teachers. Support is counselors, specialists, and other non-classroom professional roles — not classified support aides. Retention is the share still employed at this LEA the next school year. Hover a salary bar for tenure and degree mix in that pay band.</p>`;
}

function pct(rate) {
  return `${(Number(rate) * 100).toFixed(1)}%`;
}

function yearsLabel(value, digits = 0) {
  if (value == null || Number.isNaN(Number(value))) return "Not published";
  const amount = Number(value);
  const text = digits > 0 ? amount.toFixed(digits) : String(Math.round(amount));
  return `${text} ${Math.abs(amount) === 1 && digits === 0 ? "year" : "years"}`;
}

function experienceRangeLabel(index, edges, histLength) {
  if (index === 0) return "Under 1 year";
  if (index === histLength - 1) return `${edges[edges.length - 1]}+ years`;
  const years = edges[index - 1];
  return years === 1 ? "1 year" : `${years} years`;
}

function experienceHist(label, stats, edges, mode) {
  if (!edges.length || !stats.hist?.length) return "";
  const expected = edges.length + 1;
  if (stats.hist.length !== expected) return "";
  let start = 0;
  let end = stats.hist.length - 1;
  while (start < end && stats.hist[start] === 0) start += 1;
  while (end > start && stats.hist[end] === 0) end -= 1;
  const slice = stats.hist.slice(start, end + 1);
  const width = 420;
  const height = 84;
  const pad = 2;
  const max = Math.max(...slice, 1);
  const barWidth = (width - pad * 2) / slice.length;
  const otherKey = mode === "edu" ? "leaYears" : "eduYears";
  const otherLabel = mode === "edu" ? "years in this LEA" : "years in education";
  const bars = slice.map((people, offset) => {
    const index = start + offset;
    const range = experienceRangeLabel(index, edges, stats.hist.length);
    const bin = stats.bins?.[index];
    const tip = tipLines(label, [
      range,
      `${count(people)} staff`,
      bin?.meanSalary != null ? `Mean salary ${money(bin.meanSalary, 0)}` : null,
      bin?.[otherKey] != null ? `Mean ${Number(bin[otherKey]).toFixed(1)} ${otherLabel}` : null,
      bin?.mastersPct != null ? `${Math.round(bin.mastersPct)}% master’s or higher` : null,
    ].filter(Boolean));
    const barHeight = (people / max) * (height - 8);
    const x = pad + offset * barWidth;
    const y = height - barHeight;
    return `<rect class="hist-bar" data-tip="${escapeAttr(tip)}" x="${x.toFixed(1)}" y="${y.toFixed(1)}" width="${Math.max(1, barWidth - 1).toFixed(1)}" height="${barHeight.toFixed(1)}"></rect>`;
  }).join("");
  const measure = mode === "edu" ? "years in education" : "years in this LEA";
  return `<svg class="hist" viewBox="0 0 ${width} ${height}" role="img" aria-label="${escapeAttr(label)} full-time ${escapeAttr(measure)} distribution">${bars}</svg>`;
}

function salaryHist(label, stats, edges) {
  if (!edges.length || !stats.hist?.length) return "";
  // hist is [under, ...bins between edges, over]
  const expected = edges.length + 1;
  if (stats.hist.length !== expected) return "";
  let start = 0;
  let end = stats.hist.length - 1;
  while (start < end && stats.hist[start] === 0) start += 1;
  while (end > start && stats.hist[end] === 0) end -= 1;
  const slice = stats.hist.slice(start, end + 1);
  const width = 420;
  const height = 84;
  const pad = 2;
  const max = Math.max(...slice, 1);
  const barWidth = (width - pad * 2) / slice.length;
  const bars = slice.map((people, offset) => {
    const index = start + offset;
    let range;
    if (index === 0) range = `Under ${moneyFull(edges[0])}`;
    else if (index === stats.hist.length - 1) range = `${moneyFull(edges[edges.length - 1])}+`;
    else {
      const lo = edges[index - 1];
      const hi = edges[index];
      range = `${moneyFull(lo)} – ${moneyFull(hi - 0.01)}`;
    }
    const bin = stats.bins?.[index];
    const tip = tipLines(label, [
      range,
      `${count(people)} staff`,
      bin?.leaYears != null ? `Mean ${Number(bin.leaYears).toFixed(1)} years in this LEA` : null,
      bin?.eduYears != null ? `Mean ${Number(bin.eduYears).toFixed(1)} years in education` : null,
      bin?.mastersPct != null ? `${Math.round(bin.mastersPct)}% master’s or higher` : null,
    ].filter(Boolean));
    const barHeight = (people / max) * (height - 8);
    const x = pad + offset * barWidth;
    const y = height - barHeight;
    return `<rect class="hist-bar" data-tip="${escapeAttr(tip)}" x="${x.toFixed(1)}" y="${y.toFixed(1)}" width="${Math.max(1, barWidth - 1).toFixed(1)}" height="${barHeight.toFixed(1)}"></rect>`;
  }).join("");
  return `<svg class="hist" viewBox="0 0 ${width} ${height}" role="img" aria-label="${escapeAttr(label)} full-time salary distribution">${bars}</svg>`;
}

function sourceLinks(year) {
  const items = [];
  const enrollment = catalog.sources.enrollment?.[year];
  const actual = catalog.sources.afr?.[year];
  const budget = catalog.sources.gfb?.[year];
  if (enrollment) items.push(`<a href="${escapeAttr(enrollment)}">Enrollment workbook</a>`);
  if (actual) items.push(`<a href="${escapeAttr(actual)}">Annual Financial Report</a>`);
  if (budget) items.push(`<a href="${escapeAttr(budget)}">General Fund Budget</a>`);
  if (catalog.sources.chart) items.push(`<a href="${escapeAttr(catalog.sources.chart)}">Chart of accounts</a>`);
  if (catalog.sources.act1) items.push(`<a href="${escapeAttr(catalog.sources.act1)}">Act 1 index</a>`);
  const mills = catalog.sources.retax?.[year];
  if (mills) items.push(`<a href="${escapeAttr(mills)}">Real estate tax rates</a>`);
  if (catalog.sources.personnel) items.push(`<a href="${escapeAttr(catalog.sources.personnel)}">Professional personnel</a>`);
  if (catalog.sources.edna) items.push(`<a href="${escapeAttr(catalog.sources.edna)}">EdNA entity list</a>`);
  const note = leaPack.category === "career_and_technical_center"
    ? " Part-day students here can also be counted in a school district."
    : "";
  return `<p class="note">Enrollment is the October 1 count. Actual is general fund (fund 10) AFR detail: subfunction × object, then building when PDE published one. Budget is the general fund budget at function × major object, the finest grain those workbooks publish. The Act 1 index under the budget’s change from the prior year is the cap on a school district’s tax increase for that school year. A district above the aid-ratio cutoff is shown its adjusted index and the statewide base; other LEAs are shown the base index. Real estate mills are the property-tax rates on that adopted budget. A district in more than one county, or with a split rate, lists each one. Actual per student removes tuition paid to brick-and-mortar and cyber charters (object 562), because those students are counted in the charter’s enrollment. Tuition for CTCs, approved private schools, and PRRIs stays in — those students remain on this LEA’s books. When that year’s AFR is not published, the card uses the general fund budget divided by October 1 enrollment, with estimated charter tuition removed, and compares that with the prior year.${note}</p>
    <p class="sources note">${items.join(" · ") || "Source files are listed in the catalog."}</p>`;
}

function enrollmentSourceLinks(year) {
  const items = [];
  const sources = catalog?.sources || {};
  if (sources.enrollmentPage) {
    items.push(`<a href="${escapeAttr(sources.enrollmentPage)}" target="_blank" rel="noopener">Enrollment data</a>`);
  }
  const enrollment = year ? sources.enrollment?.[String(year)] : null;
  if (enrollment) {
    items.push(`<a href="${escapeAttr(enrollment)}" target="_blank" rel="noopener">${escapeHtml(yearLabel(year))} public-school workbook</a>`);
  }
  if (leaPack.category === "school_district") {
    if (sources.admPage) {
      items.push(`<a href="${escapeAttr(sources.admPage)}" target="_blank" rel="noopener">Financial data elements (ADM)</a>`);
    }
    const charterYears = Object.keys(sources.charterAdm || {}).sort((a, b) => Number(b) - Number(a));
    for (const charterYear of charterYears) {
      const url = sources.charterAdm[charterYear];
      if (!url) continue;
      items.push(`<a href="${escapeAttr(url)}" target="_blank" rel="noopener">${escapeHtml(yearLabel(charterYear))} charter ADM by district</a>`);
    }
    const homeYears = Object.keys(sources.homeEducation || {}).sort((a, b) => Number(b) - Number(a));
    for (const homeYear of homeYears) {
      const url = sources.homeEducation[homeYear];
      if (!url) continue;
      items.push(`<a href="${escapeAttr(url)}" target="_blank" rel="noopener">${escapeHtml(yearLabel(homeYear))} home education</a>`);
    }
  }
  const lowYear = year && sources.lowIncome?.[String(year)] ? String(year) : null;
  if (lowYear) {
    items.push(`<a href="${escapeAttr(sources.lowIncome[lowYear])}" target="_blank" rel="noopener">${escapeHtml(yearLabel(lowYear))} percent low income</a>`);
  } else {
    const lowYears = Object.keys(sources.lowIncome || {}).sort((a, b) => Number(b) - Number(a));
    if (lowYears[0]) {
      items.push(`<a href="${escapeAttr(sources.lowIncome[lowYears[0]])}" target="_blank" rel="noopener">${escapeHtml(yearLabel(lowYears[0]))} percent low income</a>`);
    }
  }
  if (sources.iep) {
    items.push(`<a href="${escapeAttr(sources.iep)}" target="_blank" rel="noopener">Special education by LEA (PennData)</a>`);
  }
  if (sources.graduationPage) {
    items.push(`<a href="${escapeAttr(sources.graduationPage)}" target="_blank" rel="noopener">Cohort graduation rates</a>`);
  }
  const gradFileYears = Object.keys(sources.cohortGrad || {}).sort((a, b) => Number(a) - Number(b));
  for (const gradFileYear of gradFileYears) {
    const url = sources.cohortGrad[gradFileYear]?.["4"];
    if (!url) continue;
    items.push(`<a href="${escapeAttr(url)}" target="_blank" rel="noopener">${escapeHtml(yearLabel(gradFileYear))} 4-year cohort graduation</a>`);
  }
  const lead = items.length
    ? `Source: ${items.join(" · ")}`
    : "Source: PDE enrollment files listed in the catalog";
  return `<p class="sources note">${lead}. October 1 public-school counts come from the yearly enrollment workbooks. Economically disadvantaged is PDE’s percent-low-income LEA count. IEP is December 1 school-age child count from PennData. Charter is average daily membership of resident students in charter schools from the ADM release. Homeschool is PDE’s home-education student total. The 4-year graduation rate is the published cohort rate for a regular diploma.</p>`;
}

function homeHtml() {
  return `<h1>Counties</h1>
    <p class="lede">October 1 enrollment for ${yearLabel(catalog.enrollmentYear)}, general fund actuals for ${yearLabel(catalog.actualYear)}, and adopted budgets for ${yearLabel(catalog.budgetYear)}.</p>
    ${filterHtml("Search LEAs, counties, or an AUN")}
    <div id="results"></div>`;
}

function countyHtml(state) {
  return `<h1>${escapeHtml(state.county)}</h1>
    <p class="lede" id="count"></p>
    ${filterHtml("Filter LEAs in this county")}
    <div class="toolbar"><div class="sorts">
      <button type="button" data-sort="name" data-value="name">Name</button>
      <button type="button" data-sort="enrollment" data-value="enrollment">Enrollment</button>
      <button type="button" data-sort="actual" data-value="actual">Actual</button>
    </div></div>
    <div class="list" id="results"></div>`;
}

function filterHtml(placeholder) {
  const cats = CATEGORIES.map(([id, label]) => `<button type="button" class="chip" data-kind="category" data-value="${id}">${label}</button>`).join("");
  const statuses = STATUSES.map(([id, label]) => `<button type="button" class="chip" data-kind="status" data-value="${id}">${label}</button>`).join("");
  return `<input class="search" id="q" type="search" placeholder="${placeholder}" autocomplete="off">
    <div class="chips" aria-label="Category">${cats}</div>
    <div class="chips" aria-label="Status">${statuses}</div>`;
}

function leaHtml() {
  const yearButtons = financeYears().map((year) => `<button type="button" data-year="${year}" data-value="${year}">${yearLabel(year)}</button>`).join("");
  const yearRow = yearButtons
    ? `<div class="year-row"><span class="year-label">School year</span><div class="years" role="group" aria-label="School year">${yearButtons}</div></div>`
    : "";
  const tabs = LEA_TABS.map(([id, label]) => `<button type="button" data-tab="${id}" data-value="${id}">${label}</button>`).join("");
  const directory = leaPack.inDirectory ? "" : " This AUN is not in the current EdNA public-entity extract.";
  return `<h1>${escapeHtml(leaPack.name)}</h1>
    <p class="meta">${escapeHtml(categoryName(leaPack.category))} · ${escapeHtml(leaPack.status)} · AUN ${escapeHtml(leaPack.aun)} · ${escapeHtml(leaPack.county)}.${directory}</p>
    <div class="lea-tabs" role="tablist" aria-label="LEA sections">${tabs}</div>

    <div data-tab-panel="overview">
      <div class="stats stats-wide" id="overview-stats"></div>
      <div id="overview-keystone"></div>
      <div class="panels">
        <section class="panel" id="overview-race"></section>
        <section class="panel" id="overview-gender"></section>
      </div>
      <div id="overview-blurb"></div>
    </div>

    <div data-tab-panel="financials" hidden>
      ${yearRow}
      <div class="stats" id="finance-stats"></div>
      <section class="panel"><h2>General fund</h2><div id="spend"></div></section>
      <div id="sources"></div>
    </div>

    <div data-tab-panel="staff" hidden>
      <section class="panel">
        <h2 id="experience-heading">Full-time experience</h2>
        <div class="chips" aria-label="Experience measure">
          <button type="button" class="chip" data-experience="lea" data-value="lea">Years in this LEA</button>
          <button type="button" class="chip" data-experience="edu" data-value="edu">Years in education</button>
        </div>
        <div id="experience"></div>
      </section>
      <section class="panel"><h2 id="staff-heading">Full-time salaries</h2><div id="salaries"></div></section>
    </div>

    <div data-tab-panel="enrollment" hidden>
      <div class="stats stats-3" id="enrollment-stats"></div>
      <section class="panel" id="grad-panel" hidden>
        <h2 id="grad-heading">4-year cohort graduation</h2>
        <div class="chips" id="grad-filters" aria-label="Graduation series"></div>
        <div id="grad-trend"></div>
        <p class="note">Share of students who entered 9th grade four years earlier and earned a regular diploma by the end of that school year. A GED is not counted as a graduate. All students is on by default. Other lines are the rate PDE published for that group. A gap is a year with no published rate. A printed zero stays on the chart.</p>
      </section>
      <section class="panel">
        <h2 id="trend-heading">Enrollment over time</h2>
        <div class="chips" id="trend-filters" aria-label="Enrollment series"></div>
        <div id="trend"></div>
        <p class="note">One line per selected series across October 1 files. K–12 are grade counts; Total is all published grade membership for the year. Kindergarten combines half-day and full-day.</p>
      </section>
      <section class="panel" id="alt-enrollment" hidden>
        <h2 id="alt-heading">Charter and home education</h2>
        <div class="chips" id="alt-filters" aria-label="District alternative enrollment series"></div>
        <div id="alt-trend"></div>
        <p class="note">School districts only. District is the October 1 public-school headcount. Charter is average daily membership of resident students attending brick-and-mortar or cyber charters. Homeschool is PDE’s home-education student total. If district enrollment falls while charter rises, the tradeoff shows here.</p>
      </section>
      <section class="panel">
        <h2 id="cohort-heading">How classes change as they move up</h2>
        <div class="chips" id="cohort-filters" aria-label="Current grade classes"></div>
        <div id="cohort"></div>
        <p class="note">Anchored on the latest October 1 enrollment file. One line per selected current class from kindergarten through grade 12. Grade 12 walks back through all thirteen points; kindergarten is only this year’s count. Up = the class grew; down = it shrank. Kindergarten combines half-day and full-day. Pre-kindergarten is not included — membership changes year to year, so these are approximate cohorts.</p>
      </section>
      <section class="panel">
        <h2 id="race-heading">Student groups</h2>
        <div class="chips" id="demo-filters" aria-label="Student group series"></div>
        <div id="enrollment-race"></div>
        <p class="note">Race lines stay on by default. Toggle Male, Female, Economically disadvantaged, or IEP onto the same chart. IEP is December 1 school-age child count from PennData; low-income is PDE’s October 1 percent-low-income LEA count. Hover a point for headcount and share. A gap is unpublished or suppressed, not zero.</p>
      </section>
      <div class="panels">
        <section class="panel"><h2 id="grades-heading">Grades</h2><div id="grades"></div></section>
        <section class="panel" id="enrollment-gender"></section>
      </div>
      <section class="panel">
        <h2 id="schools-heading">Schools</h2>
        <table class="schools">
          <thead><tr>
            <th><button type="button" data-schools="name" data-value="name">School</button></th>
            <th></th>
            <th class="num"><button type="button" data-schools="enrollment" data-value="enrollment">Enrollment</button></th>
          </tr></thead>
          <tbody id="school-rows"></tbody>
        </table>
      </section>
      <div id="enrollment-sources"></div>
    </div>

    <div data-tab-panel="pssa" hidden>
      <div class="stats stats-2" id="pssa-stats"></div>
      <div id="pssa-body"></div>
    </div>

    <div data-tab-panel="keystone" hidden>
      <div class="stats stats-3" id="keystone-stats"></div>
      <div id="keystone-body"></div>
    </div>`;
}

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[char]));
}

function escapeAttr(value) {
  return escapeHtml(value);
}

async function render() {
  const state = readState();
  if (!catalog) catalog = await loadJson("data/index.json");
  if (state.aun) {
    if (!leaPack || leaPack.aun !== state.aun) {
      app.dataset.view = "";
      app.innerHTML = `<p class="lede">Loading ${escapeHtml(state.aun)}…</p>`;
      try {
        leaPack = await loadJson("data/lea/" + state.aun + ".json");
      } catch {
        app.dataset.view = "";
        app.innerHTML = `<h1>LEA not found</h1><p class="lede">No published file for AUN ${escapeHtml(state.aun)}.</p>`;
        return;
      }
    }
    if (!state.county) state.county = leaPack.county;
    if (ensure("lea", leaHtml())) bindLea();
    paintLea(readState());
  } else if (state.county) {
    leaPack = null;
    if (ensure("county", countyHtml(state))) bindCounty();
    paintCounty(readState());
  } else {
    leaPack = null;
    if (ensure("home", homeHtml())) bindHome();
    paintHome(readState());
  }
  renderCrumb(readState());
}

document.querySelector("#share").addEventListener("click", share);
window.addEventListener("popstate", () => { render().catch(showError); });
document.body.addEventListener("click", (event) => {
  const anchor = event.target.closest("a");
  if (!anchor || anchor.origin !== location.origin || anchor.classList.contains("brand")) return;
  if (anchor.getAttribute("href")?.startsWith("http")) return;
  event.preventDefault();
  history.pushState(null, "", anchor.href);
  render().catch(showError);
});

function showError(error) {
  app.innerHTML = `<h1>Something went wrong</h1><p class="lede">${escapeHtml(error.message)}</p>`;
}

render().catch(showError);
