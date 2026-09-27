const DEFAULT_HUB_BASE = "https://hello-hacks26.vercel.app";
const key = document.querySelector("#key");
const hubBaseInput = document.querySelector("#hubBase");
const status = document.querySelector("#status");
const providerSelect = document.querySelector("#provider");
const originInput = document.querySelector("#origin");
for (const provider of globalThis.HUB_PROVIDERS) {
  const option = document.createElement("option");
  option.value = provider.id;
  option.textContent = provider.label;
  providerSelect.append(option);
}

function generateKey() {
  const bytes = crypto.getRandomValues(new Uint8Array(32));
  return btoa(String.fromCharCode(...bytes)).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

async function refresh() {
  const saved = await chrome.storage.local.get(["syncKey", "syncStatus", "providerOrigins", "hubBase"]);
  if (!saved.syncKey) {
    // ponytail: a key is just a random client secret (hub/hosted.py) - generate
    // one by default so hosted sync works out of the box, same as visiting a
    // site for the first time. Shown in the field so the student can copy it
    // to use the same hub on another browser.
    saved.syncKey = generateKey();
    await chrome.storage.local.set({syncKey: saved.syncKey});
  }
  key.value = saved.syncKey;
  hubBaseInput.value = saved.hubBase || "";
  hubBaseInput.placeholder = DEFAULT_HUB_BASE;
  originInput.value = saved.providerOrigins?.[providerSelect.value] || "";
  originInput.hidden = !globalThis.HUB_PROVIDERS.find(p => p.id === providerSelect.value)?.customOrigin;
  status.textContent = saved.syncStatus
    || `Syncing to ${saved.hubBase || DEFAULT_HUB_BASE}. Sign in to the selected provider, then sync.`;
}
providerSelect.addEventListener("change", refresh);

document.querySelector("#save").addEventListener("click", async () => {
  let hubBase = "";
  if (hubBaseInput.value.trim()) {
    try {
      const parsed = new URL(hubBaseInput.value.trim());
      if (parsed.protocol !== "https:" || parsed.username || parsed.password || parsed.search || parsed.hash) throw Error();
      hubBase = parsed.origin;
    } catch {
      status.textContent = "Enter a valid HTTPS sync target, e.g. https://hello-hacks26-one.vercel.app";
      return;
    }
    if (hubBase !== DEFAULT_HUB_BASE) {
      const granted = await chrome.permissions.request({origins: [`${hubBase}/*`]});
      if (!granted) {
        status.textContent = "Site access for the sync target was not granted.";
        return;
      }
    }
  }
  await chrome.storage.local.set({syncKey: key.value.trim(), hubBase});
  status.textContent = `Saved. Syncing to ${hubBase || DEFAULT_HUB_BASE}.`;
});
document.querySelector("#sync").addEventListener("click", async () => {
  status.textContent = "Starting sync…";
  const provider = globalThis.HUB_PROVIDERS.find(p => p.id === providerSelect.value);
  if (provider.customOrigin) {
    let origin;
    try {
      const parsed = new URL(originInput.value);
      if (parsed.protocol !== "https:" || parsed.username || parsed.password || parsed.search || parsed.hash) throw Error();
      origin = parsed.origin;
    } catch {
      status.textContent = "Enter the HTTPS address of your provider site.";
      return;
    }
    const granted = await chrome.permissions.request({origins: [`${origin}/*`]});
    if (!granted) {
      status.textContent = "Site access was not granted.";
      return;
    }
    const {providerOrigins = {}} = await chrome.storage.local.get("providerOrigins");
    providerOrigins[provider.id] = origin;
    await chrome.storage.local.set({providerOrigins});
  }
  const result = await chrome.runtime.sendMessage({type: "SYNC_NOW", provider: providerSelect.value});
  if (!result?.ok) status.textContent = result?.error || "Could not start sync";
  else setTimeout(refresh, 1000);
});
refresh();
