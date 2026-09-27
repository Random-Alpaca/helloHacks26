/* One entry per verified browser capture adapter. The background transport and
   popup use this registry without branching on a provider name. */
const HUB_PROVIDERS = Object.freeze([
  {id: "canvas", label: "Canvas", origin: "https://canvas.ubc.ca",
   tabPattern: "https://canvas.ubc.ca/*", captureFile: "providers/canvas.js"}
]);
globalThis.HUB_PROVIDERS = HUB_PROVIDERS;
if (typeof module !== "undefined") module.exports = {HUB_PROVIDERS};
