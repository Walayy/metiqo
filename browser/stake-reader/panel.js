const LIST = "https://stake.bet/fr/sports/league-of-legends/all";
const status = document.querySelector("#status");
const report = document.querySelector("#report");
let running = false,
  cancelled = false,
  timer,
  currentTab;
const pause = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
const publicUrl = (value, segments) => {
  try {
    const u = new URL(value, "https://stake.bet");
    if (
      u.origin !== "https://stake.bet" ||
      u.username ||
      u.password ||
      u.search ||
      u.hash ||
      !/^\/fr\/sports\/league-of-legends(?:\/[a-z0-9-]+){1,3}\/?$/.test(u.pathname)
    )
      return null;
    const parts = u.pathname.replace(/\/$/, "").split("/").slice(1);
    if (parts.length !== segments || (segments === 6 && !/^\d+-/.test(parts.at(-1)))) return null;
    return u.origin + u.pathname.replace(/\/$/, "");
  } catch {
    return null;
  }
};
const links = (dom, size) => [...new Set(dom.links.map((s) => publicUrl(s, size)).filter(Boolean))];
const stopped = () => {
  if (cancelled) throw new Error("CANCELLED");
};
async function read(tabId, url, mode) {
  stopped();
  currentTab = tabId;
  await chrome.scripting.executeScript({
    target: { tabId },
    files: ["extract-dom.js", "reader.js"],
  });
  const [value] = await chrome.scripting.executeScript({
    target: { tabId },
    func: async (kind, expected) => {
      // Chrome ne transmet pas toujours les exceptions du script injecté.
      try {
        return { ok: true, data: await globalThis.metiquoReadStake(kind, expected) };
      } catch (error) {
        return { ok: false, error: String(error.message || error) };
      }
    },
    args: [mode, url],
  });
  if (!value?.result) throw new Error("DOM_READ_FAILED");
  if (!value.result.ok) throw new Error(value.result.error);
  return value.result.data;
}
async function navigate(tabId, url) {
  stopped();
  await chrome.tabs.update(tabId, { url });
  const end = Date.now() + 30000;
  while (Date.now() < end) {
    stopped();
    const tab = await chrome.tabs.get(tabId);
    if (tab.status === "complete" && tab.url === url) {
      await pause(1000);
      return;
    }
    if (tab.status === "complete" && tab.url && tab.url !== url && !tab.pendingUrl)
      throw new Error("UNEXPECTED_REDIRECT");
    await pause(200);
  }
  throw new Error("NAVIGATION_TIMEOUT");
}
async function save(payload) {
  const json = JSON.stringify(payload);
  if (new TextEncoder().encode(json).length > 16 * 1024 * 1024) throw new Error("EXPORT_TOO_LARGE");
  const id = await chrome.downloads.download({
    url: "data:application/json;charset=utf-8," + encodeURIComponent(json),
    filename: "Metiquo/stake-browser-latest.json",
    conflictAction: "overwrite",
    saveAs: false,
  });
  for (let i = 0; i < 100; i++) {
    const [item] = await chrome.downloads.search({ id });
    if (item?.state === "complete") return item.filename;
    if (item?.state === "interrupted") throw new Error("EXPORT_INTERRUPTED");
    await pause(200);
  }
  throw new Error("EXPORT_NOT_FINISHED");
}
async function run(mode) {
  if (running) return;
  running = true;
  cancelled = false;
  clearTimeout(timer);
  document.querySelector("#scan").disabled = document.querySelector("#opened").disabled = true;
  document.querySelector("#stop").disabled = false;
  const captures = [],
    failures = [];
  let workerTab,
    blocked = false,
    events = [];
  try {
    if (mode === "opened") {
      const tabs = await chrome.tabs.query({
        url: "https://stake.bet/fr/sports/league-of-legends/*",
      });
      const unique = new Map();
      for (const tab of tabs) {
        const url = publicUrl(tab.url, 6);
        if (url) unique.set(url, tab.id);
      }
      events = [...unique].map(([url, tabId]) => ({ url, tabId }));
    } else {
      status.textContent = "Lecture des compétitions…";
      workerTab = await chrome.tabs.create({ url: LIST, active: false });
      await navigate(workerTab.id, LIST);
      const list = await read(workerTab.id, LIST, "links");
      failures.push(...list.warnings);
      const competitions = links(list, 5);
      if (!competitions.length) throw new Error("COMPETITIONS_MISSING");
      if (competitions.length > 30) failures.push("COMPETITION_LIMIT_REACHED");
      for (const url of competitions.slice(0, 30)) {
        try {
          await navigate(workerTab.id, url);
          const page = await read(workerTab.id, url, "links");
          failures.push(...page.warnings);
          events.push(...links(page, 6).map((event) => ({ url: event, tabId: workerTab.id })));
        } catch (error) {
          if (/ACCESS_CHALLENGE|CANCELLED/.test(error.message)) throw error;
          failures.push(url.split("/").at(-1) + ":" + error.message);
        }
      }
      events = [...new Map(events.map((event) => [event.url, event])).values()];
    }
    if (!events.length) throw new Error("NO_EVENTS");
    if (events.length > 40) failures.push("EVENT_LIMIT_REACHED");
    for (const [index, event] of events.slice(0, 40).entries()) {
      stopped();
      status.textContent = `Lecture du match ${index + 1}/${Math.min(events.length, 40)}…`;
      try {
        if (workerTab) await navigate(event.tabId, event.url);
        captures.push(await read(event.tabId, event.url, "event"));
      } catch (error) {
        if (/ACCESS_CHALLENGE|CANCELLED/.test(error.message)) throw error;
        failures.push(event.url.split("/").at(-1) + ":" + error.message);
      }
    }
  } catch (error) {
    blocked = /ACCESS_CHALLENGE/.test(error.message);
    failures.push(error.message);
    document.querySelector("#repeat").checked = false;
  } finally {
    if (workerTab) await chrome.tabs.remove(workerTab.id).catch(() => {});
    currentTab = undefined;
  }
  try {
    const payload = {
      format: "metiquo.stake-browser.v1",
      exportedAt: new Date().toISOString(),
      discoveredEvents: events.length,
      captures,
      failures,
      blocked,
    };
    const filename = await save(payload);
    status.textContent = `${captures.length} match(s) exporté(s)${failures.length ? " · collecte incomplète" : ""}.`;
    report.textContent = `${filename}\n${failures.join("\n")}`;
  } catch (error) {
    status.textContent = "Export impossible : " + error.message;
    document.querySelector("#repeat").checked = false;
  } finally {
    running = false;
    document.querySelector("#scan").disabled = document.querySelector("#opened").disabled = false;
    const again = !cancelled && document.querySelector("#repeat").checked;
    document.querySelector("#stop").disabled = !again;
    if (again) {
      const slow = failures.some((s) => /TIMEOUT|PAGE_NOT_READY|UNEXPECTED_REDIRECT/.test(s));
      timer = setTimeout(
        () => {
          if (document.querySelector("#repeat").checked) run(mode);
        },
        slow ? 600000 : 60000,
      );
    }
  }
}
document.querySelector("#scan").addEventListener("click", () => run("scan"));
document.querySelector("#opened").addEventListener("click", () => run("opened"));
document.querySelector("#stop").addEventListener("click", () => {
  cancelled = true;
  clearTimeout(timer);
  document.querySelector("#repeat").checked = false;
  status.textContent = running ? "Arrêt demandé…" : "Actualisation automatique arrêtée.";
  if (!running) document.querySelector("#stop").disabled = true;
  if (currentTab)
    chrome.scripting
      .executeScript({
        target: { tabId: currentTab },
        func: () => {
          globalThis.metiquoAbortStake = true;
        },
      })
      .catch(() => {});
});
document.querySelector("#repeat").addEventListener("change", () => {
  if (!document.querySelector("#repeat").checked) {
    clearTimeout(timer);
    if (!running) document.querySelector("#stop").disabled = true;
  }
});
