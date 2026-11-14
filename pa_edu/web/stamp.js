const REPO = "https://github.com/bobruddy/pa_education_data";

async function loadBuild() {
  try {
    const response = await fetch(new URL("build.json", import.meta.url));
    if (!response.ok) return null;
    return await response.json();
  } catch {
    return null;
  }
}

function formatEastern(iso) {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return String(iso ?? "");
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone: "America/New_York",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hourCycle: "h23",
  }).formatToParts(date);
  const get = (type) => parts.find((part) => part.type === type)?.value ?? "";
  const hour = get("hour") === "24" ? "00" : get("hour");
  return `${get("year")}-${get("month")}-${get("day")} ${hour}:${get("minute")}:${get("second")} US/Eastern`;
}

export function applyBuildStamp(stamp) {
  const el = document.querySelector("#build-stamp");
  const link = el?.querySelector("a");
  if (!el || !link || !stamp?.commit || !stamp.commitUrl) return;
  link.href = stamp.commitUrl;
  link.textContent = stamp.commitShort || String(stamp.commit).slice(0, 7);
  link.title = stamp.commit;
  const committed = el.querySelector("[data-committed]");
  const built = el.querySelector("[data-built]");
  if (committed) committed.textContent = "Committed " + formatEastern(stamp.committedAt);
  if (built) built.textContent = "Built " + formatEastern(stamp.generatedAt);
  el.hidden = false;
}

export function applyFeedbackLinks(stamp) {
  const page = location.href;
  for (const anchor of document.querySelectorAll("a.feedback")) {
    const template = anchor.dataset.template;
    if (!template) continue;
    const params = new URLSearchParams();
    params.set("template", template);
    const field = anchor.dataset.pageField;
    if (field) params.set(field, page);
    if (stamp?.commit && stamp.commitUrl && stamp.committedAt && stamp.generatedAt) {
      params.set("build", [
        `Commit: ${stamp.commit}`,
        `Commit URL: ${stamp.commitUrl}`,
        `Committed: ${formatEastern(stamp.committedAt)}`,
        `Built: ${formatEastern(stamp.generatedAt)}`,
        `Page: ${page}`,
      ].join("\n"));
    }
    anchor.href = `${REPO}/issues/new?${params}`;
  }
}

export const buildReady = loadBuild().then((stamp) => {
  if (stamp) applyBuildStamp(stamp);
  return stamp;
});
