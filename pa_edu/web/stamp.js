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

function formatUtc(iso) {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return String(iso ?? "");
  const pad = (value) => String(value).padStart(2, "0");
  const day = [
    date.getUTCFullYear(),
    pad(date.getUTCMonth() + 1),
    pad(date.getUTCDate()),
  ].join("-");
  const time = [pad(date.getUTCHours()), pad(date.getUTCMinutes()), pad(date.getUTCSeconds())].join(":");
  return `${day} ${time} UTC`;
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
  if (committed) committed.textContent = "Committed " + formatUtc(stamp.committedAt);
  if (built) built.textContent = "Built " + formatUtc(stamp.generatedAt);
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
        `Committed: ${stamp.committedAt}`,
        `Built: ${stamp.generatedAt}`,
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
