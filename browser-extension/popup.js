/**
 * Convioo browser extension — popup logic.
 *
 * Pre-fills the form from the active tab's page metadata + selection,
 * lets the user tweak fields, and POSTs one row to the existing
 * /api/v1/searches/import-csv endpoint so the saved page lands in
 * /app/sessions and immediately shows up in the CRM.
 */

const $ = (id) => document.getElementById(id);

async function loadConfig() {
  return new Promise((resolve) => {
    chrome.storage.local.get(["apiUrl", "userId"], (data) => {
      resolve({
        apiUrl: (data.apiUrl || "").replace(/\/$/, ""),
        userId: data.userId ? parseInt(data.userId, 10) : null,
      });
    });
  });
}

async function readActiveTabContext() {
  // Get the active tab and pull a small page-meta snippet via a
  // one-shot scripting injection. Falls back to URL-only when the
  // user is on a chrome:// page where scripting is blocked.
  const [tab] = await chrome.tabs.query({
    active: true,
    currentWindow: true,
  });
  const ctx = {
    url: tab?.url || "",
    title: tab?.title || "",
    selection: "",
    description: "",
    h1: "",
  };
  if (!tab?.id) return ctx;
  try {
    const [{ result }] = await chrome.scripting.executeScript({
      target: { tabId: tab.id },
      func: () => ({
        selection: window.getSelection ? window.getSelection().toString() : "",
        description:
          document
            .querySelector('meta[name="description"]')
            ?.getAttribute("content") || "",
        h1: document.querySelector("h1")?.textContent?.trim() || "",
      }),
    });
    Object.assign(ctx, result || {});
  } catch {
    // Page blocked scripting (chrome://, etc) — keep the URL/title we have.
  }
  return ctx;
}

function bestName(ctx) {
  if (ctx.selection && ctx.selection.length <= 120 && ctx.selection.length >= 2) {
    return ctx.selection.trim();
  }
  if (ctx.h1) return ctx.h1.slice(0, 200);
  if (ctx.title) {
    // Strip "Site Name — " or " | Site Name" suffixes when present.
    return ctx.title.split(/[|—–-]/)[0].trim().slice(0, 200);
  }
  return "";
}

async function init() {
  const { apiUrl, userId } = await loadConfig();
  if (!apiUrl || !userId) {
    $("needs-config").style.display = "block";
    $("open-options").addEventListener("click", () => {
      chrome.runtime.openOptionsPage();
    });
    return;
  }
  $("form").style.display = "block";

  const ctx = await readActiveTabContext();
  $("name").value = bestName(ctx);
  $("website").value = ctx.url;
  $("notes").value = ctx.selection
    ? ctx.selection.slice(0, 500)
    : ctx.description.slice(0, 500);

  $("cancel").addEventListener("click", () => window.close());
  $("save").addEventListener("click", () => save({ apiUrl, userId }));
  $("name").focus();
}

async function save({ apiUrl, userId }) {
  const name = $("name").value.trim();
  if (!name) {
    $("status").className = "hint err";
    $("status").textContent = "Name is required.";
    return;
  }
  $("save").disabled = true;
  $("status").className = "hint";
  $("status").textContent = "Saving…";

  const today = new Date().toISOString().slice(0, 10);
  const payload = {
    user_id: userId,
    label: `Browser saves · ${today}`,
    rows: [
      {
        name,
        website: $("website").value.trim() || null,
        region: $("region").value.trim() || null,
        phone: $("phone").value.trim() || null,
        category: $("category").value.trim() || null,
        extras: {
          source: "browser_extension",
          notes: $("notes").value.trim().slice(0, 500),
        },
      },
    ],
  };

  try {
    const res = await fetch(`${apiUrl}/api/v1/searches/import-csv`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!res.ok) {
      const text = await res.text();
      throw new Error(`${res.status}: ${text.slice(0, 200)}`);
    }
    const data = await res.json();
    $("status").className = "hint ok";
    $("status").textContent = `Saved ✓  (session ${data.search_id?.slice(0, 8) || ""})`;
    setTimeout(() => window.close(), 1200);
  } catch (err) {
    $("status").className = "hint err";
    $("status").textContent = err.message || String(err);
    $("save").disabled = false;
  }
}

init();
