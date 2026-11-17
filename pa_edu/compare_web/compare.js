let pack = null;
let viewId = "actual";
let path = [];
let order = null;

const title = document.querySelector("#title");
const deck = document.querySelector("#deck");
const switcher = document.querySelector("#switch");
const crumb = document.querySelector("#crumb");
const status = document.querySelector("#status");
const board = document.querySelector("#board");
const sources = document.querySelector("#sources");
const tip = document.querySelector("#tip");

switcher.addEventListener("click", (event) => {
  if (event.target.closest("[data-sort]")) {
    sortBigToSmall();
    return;
  }
  const button = event.target.closest("[data-view]");
  if (!button || button.dataset.view === viewId) return;
  viewId = button.dataset.view;
  path = [];
  order = null;
  hideTip();
  render();
});

crumb.addEventListener("click", (event) => {
  const button = event.target.closest("[data-back]");
  if (!button) return;
  if (button.dataset.back === "all") path = [];
  else path = path.slice(0, path.indexOf(button.dataset.back) + 1);
  hideTip();
  render();
});

document.addEventListener("click", (event) => {
  const button = event.target.closest("button[data-code]");
  if (!button || !pack) return;
  path = ancestors(button.dataset.code);
  hideTip();
  render();
});

board.addEventListener("pointerover", (event) => {
  const seg = event.target.closest("[data-code]");
  if (!seg) return;
  showTip(seg, event);
});
board.addEventListener("pointermove", (event) => {
  if (tip.hidden) return;
  placeTip(event.clientX, event.clientY);
});
board.addEventListener("pointerout", (event) => {
  const seg = event.target.closest("[data-code]");
  if (!seg || seg.contains(event.relatedTarget)) return;
  hideTip();
});
board.addEventListener("focusin", (event) => {
  const seg = event.target.closest("[data-code]");
  if (!seg) return;
  const rect = seg.getBoundingClientRect();
  showTip(seg, { clientX: rect.left, clientY: rect.top });
});
board.addEventListener("focusout", (event) => {
  if (event.target.closest("[data-code]")) hideTip();
});

fetch("compare.json")
  .then((response) => {
    if (!response.ok) throw new Error(String(response.status));
    return response.json();
  })
  .then((payload) => {
    pack = payload;
    status.hidden = true;
    render();
  })
  .catch(() => {
    status.textContent = "Could not load the Chester County comparison.";
  });

function view() {
  return pack.views.find((item) => item.id === viewId);
}

function render() {
  const shown = view();
  const code = path.at(-1) || null;
  const kids = code ? shown.nodes[code].children : majorCodes();
  title.textContent = `${shown.yearLabel} ${shown.heading} per student`;
  renderSwitch();
  const districts = listed();
  if (!code) {
    deck.textContent = shown.blurb;
    renderBoard(kids, districts, "total", true);
  } else if (kids.length) {
    deck.textContent = `${named(code)}. Each bar is the next account. Click a color to open it.`;
    renderBoard(kids, districts, code, true);
  } else {
    deck.textContent = named(code);
    renderBoard([code], districts, code, false);
  }
  renderCrumb();
  renderSources();
}

function renderSwitch() {
  switcher.replaceChildren();
  for (const item of pack.views) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "chip";
    button.dataset.view = item.id;
    button.textContent = item.label;
    button.setAttribute("aria-pressed", item.id === viewId ? "true" : "false");
    switcher.append(button);
  }
  const sort = document.createElement("button");
  sort.type = "button";
  sort.className = "chip sort";
  sort.dataset.sort = "desc";
  sort.textContent = "Big to small";
  switcher.append(sort);
}

function listed() {
  const shown = view();
  if (!order) return shown.districts;
  const byAun = new Map(shown.districts.map((item) => [item.aun, item]));
  return order.map((aun) => byAun.get(aun)).filter(Boolean);
}

function sortBigToSmall() {
  const shown = view();
  const code = path.at(-1) || null;
  const kids = code ? shown.nodes[code].children : [];
  const codes = code ? (kids.length ? kids : [code]) : majorCodes();
  const ranked = shown.districts.slice().sort((a, b) => {
    const rank = (district) => {
      if (!district.published) return [2, 0, district.name];
      const amount = stackAmount(district, codes);
      if (amount == null || !(district.enrolled > 0)) return [1, 0, district.name];
      return [0, -(amount / district.enrolled), district.name];
    };
    const [ar, ap, an] = rank(a);
    const [br, bp, bn] = rank(b);
    return ar - br || ap - bp || an.localeCompare(bn);
  });
  order = ranked.map((item) => item.aun);
  hideTip();
  render();
}

function renderCrumb() {
  crumb.replaceChildren();
  if (!path.length) {
    crumb.append(here("All accounts"));
    return;
  }
  crumb.append(crumbButton("All accounts", "all"));
  path.forEach((code, index) => {
    crumb.append(slash());
    const text = named(code);
    crumb.append(index === path.length - 1 ? here(text) : crumbButton(text, code));
  });
}

function renderBoard(codes, districts, medianKey, clickable) {
  const max = scaleMax(codes, districts);
  const median = view().medians[medianKey];
  const grid = document.createElement("div");
  grid.className = "grid";
  const showMedian = median != null && max > 0;
  const at = showMedian ? (median / max) * 100 : 0;

  for (const district of districts) {
    const name = document.createElement("p");
    name.className = "name";
    name.textContent = district.name;
    const track = document.createElement("div");
    track.className = "track";
    if (showMedian) {
      const mark = document.createElement("i");
      mark.className = "mark";
      mark.style.left = `${at}%`;
      mark.setAttribute("aria-hidden", "true");
      track.append(mark);
    }
    const value = document.createElement("p");
    value.className = "value";
    if (!district.published) {
      value.classList.add("quiet");
      value.textContent = "Not published";
    } else {
      const stack = stackAmount(district, codes);
      if (stack == null) {
        value.classList.add("quiet");
        value.textContent = "—";
      } else {
        for (const code of codes) {
          const level = district.levels[code];
          if (!level || !(level.amount > 0)) continue;
          track.append(segment(district, code, level.amount / district.enrolled / max * 100, clickable));
        }
        value.textContent = money0(stack / district.enrolled);
      }
    }
    grid.append(name, track, value);
  }

  if (showMedian) {
    const note = document.createElement("div");
    note.className = "median-note";
    note.style.gridColumn = "2";
    const label = document.createElement("span");
    label.textContent = `median ${money0(median)}`;
    label.style.left = `${at}%`;
    label.style.transform = at > 82 ? "translateX(-100%)" : at < 12 ? "none" : "translateX(-50%)";
    note.append(label);
    grid.append(note);
  }

  board.replaceChildren(grid);
  board.hidden = false;
  const account = path.length ? named(path.at(-1)) : "the general-fund total";
  board.setAttribute(
    "aria-label",
    `${pack.county} County, ${view().yearLabel}, ${account}.`,
  );
}

function segment(district, code, width, clickable) {
  const node = document.createElement(clickable ? "button" : "div");
  node.className = "seg";
  if (clickable) node.type = "button";
  else node.tabIndex = 0;
  node.dataset.code = code;
  node.dataset.aun = district.aun;
  node.style.flex = `0 0 ${width}%`;
  node.style.background = colorFor(code);
  const level = district.levels[code];
  node.setAttribute(
    "aria-label",
    `${named(code)}, ${moneyPer(level.perStudent)} per student, ${district.name}`,
  );
  return node;
}

function scaleMax(codes, districts) {
  let max = 0;
  for (const district of districts) {
    if (!district.published) continue;
    const amount = stackAmount(district, codes);
    if (amount == null || !(district.enrolled > 0)) continue;
    max = Math.max(max, amount / district.enrolled);
  }
  return max;
}

function stackAmount(district, codes) {
  let amount = 0;
  let any = false;
  for (const code of codes) {
    const level = district.levels?.[code];
    if (!level) continue;
    any = true;
    amount += level.amount;
  }
  return any ? amount : null;
}

function majorCodes() {
  return view().majors.map((item) => item.code).filter((code) => view().nodes[code]);
}

function ancestors(code) {
  const chain = [];
  let cursor = code;
  while (cursor) {
    chain.unshift(cursor);
    cursor = view().nodes[cursor]?.parent || null;
  }
  return chain;
}

function isMajor(code) {
  return view().majors.some((item) => item.code === code);
}

function named(code) {
  return `${code} ${labelFor(code)}`;
}

function labelFor(code) {
  return view().nodes[code]?.label || code;
}

function colorFor(code) {
  const base = view().majors.find((item) => item.code === (isMajor(code) ? code : `${code[0]}000`))?.color || "#5e574c";
  if (isMajor(code)) return base;
  const siblings = view().nodes[view().nodes[code].parent]?.children || [];
  const index = Math.max(0, siblings.indexOf(code));
  if (siblings.length <= 1) return base;
  return mixHex(base, "#fffdf8", (index / (siblings.length - 1)) * 0.55);
}

function mixHex(hex, toward, amount) {
  const read = (value) => [0, 2, 4].map((index) => parseInt(value.slice(1 + index, 3 + index), 16));
  const start = read(hex);
  const end = read(toward);
  const mixed = start.map((channel, index) => Math.round(channel + (end[index] - channel) * amount));
  return `#${mixed.map((channel) => channel.toString(16).padStart(2, "0")).join("")}`;
}

function crumbButton(text, back) {
  const button = document.createElement("button");
  button.type = "button";
  button.dataset.back = back;
  button.textContent = text;
  return button;
}

function here(text) {
  const node = document.createElement("span");
  node.className = "here";
  node.textContent = text;
  return node;
}

function slash() {
  const node = document.createElement("span");
  node.className = "slash";
  node.textContent = "/";
  return node;
}

function renderSources() {
  const shown = view();
  sources.replaceChildren();
  sources.append(shown.note);
  if (shown.source?.url) {
    const link = document.createElement("a");
    link.href = shown.source.url;
    link.textContent = `${shown.sourceLabel} ${shown.yearLabel}`;
    sources.append(link, ". ");
  }
  if (shown.enrollment?.url) {
    const link = document.createElement("a");
    link.href = shown.enrollment.url;
    link.textContent = `October 1 enrollment ${shown.yearLabel}`;
    sources.append(link, ".");
  }
  sources.hidden = false;
}

function showTip(seg, event) {
  const district = view().districts.find((item) => item.aun === seg.dataset.aun);
  const level = district?.levels?.[seg.dataset.code];
  if (!district || !level) return;
  tip.replaceChildren();
  const heading = document.createElement("strong");
  heading.textContent = named(seg.dataset.code);
  const per = document.createElement("p");
  per.textContent = `${moneyPer(level.perStudent)} per student`;
  const raw = document.createElement("p");
  raw.textContent = moneyFull(level.amount);
  const students = document.createElement("p");
  students.textContent = `${count(district.enrolled)} students on October 1`;
  const source = document.createElement("p");
  source.className = "muted";
  source.textContent = `${view().sourceLabel} ${view().yearLabel}`;
  tip.append(heading, per, raw, students, source);
  tip.hidden = false;
  placeTip(event.clientX, event.clientY);
}

function placeTip(x, y) {
  const pad = 12;
  tip.style.left = "0px";
  tip.style.top = "0px";
  const rect = tip.getBoundingClientRect();
  let left = x + 14;
  let top = y - rect.height - 10;
  if (top < pad) top = y + 16;
  if (left + rect.width > window.innerWidth - pad) left = x - rect.width - 14;
  tip.style.left = `${Math.max(pad, left)}px`;
  tip.style.top = `${Math.max(pad, top)}px`;
}

function hideTip() {
  tip.hidden = true;
}

function moneyPer(value) {
  const amount = Number(value);
  if (amount > 0 && amount < 0.5) return "under $1";
  return money0(amount);
}

function money0(value) {
  const amount = Math.round(Number(value));
  const sign = amount < 0 ? "−" : "";
  return `${sign}$${Math.abs(amount).toLocaleString("en-US")}`;
}

function moneyFull(value) {
  return Number(value).toLocaleString("en-US", { style: "currency", currency: "USD" });
}

function count(value) {
  return Number(value).toLocaleString("en-US");
}
