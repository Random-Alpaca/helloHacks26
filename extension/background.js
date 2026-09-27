importScripts("providers.js");
const HUB_SYNC_URL = "https://hello-hacks26.vercel.app/api/sync";
const HUB_NORMALIZE_URL = "https://hello-hacks26.vercel.app/api/normalize";
const PROVIDERS = globalThis.HUB_PROVIDERS;

// The upload key stays in trusted extension contexts, never in a Canvas page.
chrome.storage.local.setAccessLevel({accessLevel: "TRUSTED_CONTEXTS"});

async function setStatus(message) {
  await chrome.storage.local.set({syncStatus: message});
}

async function syncNow(providerId, interactive = true) {
  const provider = PROVIDERS.find(p => p.id === providerId);
  if (!provider) throw new Error("This provider has no verified extension adapter");
  const tabs = await chrome.tabs.query({url: provider.tabPattern});
  const tab = tabs.find(t => t.status === "complete" && t.id);
  if (!tab) {
    if (interactive) {
      await chrome.tabs.create({url: `${provider.origin}/`});
      await setStatus(`${provider.label} opened. Sign in there, then press Sync again.`);
    }
    return;
  }
  await setStatus(`Reading ${provider.label} tasks…`);
  await chrome.scripting.executeScript({target: {tabId: tab.id}, files: [provider.captureFile]});
}

chrome.runtime.onInstalled.addListener(() => {
  chrome.alarms.create("provider-sync", {periodInMinutes: 30});
});
chrome.alarms.onAlarm.addListener(alarm => {
  if (alarm.name === "provider-sync") {
    for (const provider of PROVIDERS) {
      syncNow(provider.id, false).catch(error => setStatus(error.message));
    }
  }
});

chrome.runtime.onMessage.addListener((message, sender, respond) => {
  if (message?.type === "SYNC_NOW") {
    syncNow(message.provider).then(() => respond({ok: true}), error => {
      setStatus(error.message);
      respond({ok: false, error: error.message});
    });
    return true;
  }
  if (message?.type !== "CAPTURE_READY" && message?.type !== "CAPTURE_FAILED") return;
  const providerId = message.type === "CAPTURE_READY" ? message.capture?.source : message.source;
  const provider = PROVIDERS.find(p => p.id === providerId);
  if (!provider || !sender.tab?.url || new URL(sender.tab.url).origin !== provider.origin) return;
  if (message.type === "CAPTURE_FAILED") {
    setStatus(message.error || `${provider.label} sync failed`);
    return;
  }
  (async () => {
    const {latestCaptures = {}} = await chrome.storage.local.get("latestCaptures");
    latestCaptures[provider.id] = message.capture;
    await chrome.storage.local.set({latestCaptures});
    const normalized = await fetch(HUB_NORMALIZE_URL, {
      method: "POST", redirect: "error",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify(message.capture)
    });
    if (!normalized.ok) throw new Error(`Hub normalization failed (${normalized.status})`);
    const model = await normalized.json();
    if (model.source !== provider.id || model.stored !== false
        || !Array.isArray(model.courses) || !Array.isArray(model.items)) {
      throw new Error("Hub returned an invalid normalized capture");
    }
    const {latestModels = {}} = await chrome.storage.local.get("latestModels");
    latestModels[provider.id] = model;
    await chrome.storage.local.set({latestModels});
    const {syncKey} = await chrome.storage.local.get("syncKey");
    if (!syncKey) {
      // ponytail: browser-local rows until Terrace provisions authenticated durable storage.
      await setStatus(`${provider.label} normalized by Vercel and saved locally. Hosted storage is not configured yet.`);
      return;
    }
    const response = await fetch(HUB_SYNC_URL, {
      method: "POST", redirect: "error",
      headers: {"Content-Type": "application/json", Authorization: `Bearer ${syncKey}`},
      body: JSON.stringify(model)
    });
    if (!response.ok) throw new Error(`Hub upload failed (${response.status})`);
    await setStatus(`${provider.label} uploaded at ${new Date().toLocaleString()}`);
  })().catch(error => setStatus(error.message));
});
