const key = document.querySelector("#key");
const status = document.querySelector("#status");
const providerSelect = document.querySelector("#provider");
for (const provider of globalThis.HUB_PROVIDERS) {
  const option = document.createElement("option");
  option.value = provider.id;
  option.textContent = provider.label;
  providerSelect.append(option);
}

async function refresh() {
  const saved = await chrome.storage.local.get(["syncKey", "syncStatus"]);
  key.value = saved.syncKey || "";
  status.textContent = saved.syncStatus || "Sign in to the selected provider, then sync.";
}

document.querySelector("#save").addEventListener("click", async () => {
  await chrome.storage.local.set({syncKey: key.value.trim()});
  status.textContent = "Sync key saved on this browser.";
});
document.querySelector("#sync").addEventListener("click", async () => {
  status.textContent = "Starting sync…";
  const result = await chrome.runtime.sendMessage({type: "SYNC_NOW", provider: providerSelect.value});
  if (!result?.ok) status.textContent = result?.error || "Could not start sync";
  else setTimeout(refresh, 1000);
});
refresh();
