import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import vm from "node:vm";

test("uploads a Canvas capture to Vercel without browser session credentials", async () => {
  const handlers = {};
  const stored = {syncKey: "fake-hub-key"};
  const calls = [];
  const chrome = {
    storage: {local: {
      setAccessLevel: async () => {},
      get: async () => stored,
      set: async value => Object.assign(stored, value)
    }},
    runtime: {onInstalled: {addListener: fn => { handlers.installed = fn; }},
              onMessage: {addListener: fn => { handlers.message = fn; }}},
    alarms: {create: () => {}, onAlarm: {addListener: fn => { handlers.alarm = fn; }}},
    tabs: {query: async () => [], create: async () => {}},
    scripting: {executeScript: async () => {}}
  };
  const normalized = {source: "canvas", stored: false, courses: [], items: []};
  const fetch = async (url, init) => {
    calls.push({url, init});
    return {ok: true, status: 200, json: async () => normalized};
  };
  const registry = fs.readFileSync(new URL("./providers.js", import.meta.url), "utf8");
  const context = {chrome, fetch, Date, JSON, URL, setTimeout,
    importScripts: () => vm.runInNewContext(registry, context)};
  vm.runInNewContext(fs.readFileSync(new URL("./background.js", import.meta.url), "utf8"),
                     context);
  const capture = {source: "canvas", courses: [], planner: [], undated: []};
  handlers.message({type: "CAPTURE_READY", capture},
                   {tab: {url: "https://canvas.ubc.ca/courses"}}, () => {});
  await new Promise(resolve => setTimeout(resolve, 0));
  assert.equal(calls.length, 2);
  assert.equal(calls[0].url, "https://hello-hacks26.vercel.app/api/normalize");
  assert.equal(calls[0].init.method, "POST");
  assert.deepEqual(JSON.parse(calls[0].init.body), capture);
  assert.equal(calls[1].url, "https://hello-hacks26.vercel.app/api/sync");
  assert.equal(calls[1].init.headers.Authorization, "Bearer fake-hub-key");
  assert.deepEqual(JSON.parse(calls[1].init.body), normalized);
  assert.match(stored.syncStatus, /^Canvas uploaded at /);
  assert.deepEqual(stored.latestCaptures.canvas, capture);
  assert.deepEqual(stored.latestModels.canvas, normalized);

  handlers.message({type: "CAPTURE_READY", capture},
                   {tab: {url: "https://evil.example/"}}, () => {});
  await new Promise(resolve => setTimeout(resolve, 0));
  assert.equal(calls.length, 2);
});

test("keeps a capture local when the hosted sync key is not configured", async () => {
  const handlers = {};
  const stored = {};
  const chrome = {
    storage: {local: {setAccessLevel: async () => {}, get: async () => stored,
                      set: async value => Object.assign(stored, value)}},
    runtime: {onInstalled: {addListener: () => {}},
              onMessage: {addListener: fn => { handlers.message = fn; }}},
    alarms: {create: () => {}, onAlarm: {addListener: () => {}}},
    tabs: {query: async () => [], create: async () => {}},
    scripting: {executeScript: async () => {}}
  };
  const registry = fs.readFileSync(new URL("./providers.js", import.meta.url), "utf8");
  const context = {chrome, fetch: () => { throw new Error("unexpected network call"); }, Date, JSON, URL,
    importScripts: () => vm.runInNewContext(registry, context)};
  context.fetch = async () => ({ok: true, status: 200, json: async () =>
    ({source: "canvas", stored: false, courses: [], items: []})});
  vm.runInNewContext(fs.readFileSync(new URL("./background.js", import.meta.url), "utf8"), context);
  const capture = {source: "canvas", courses: [], planner: [], undated: []};
  handlers.message({type: "CAPTURE_READY", capture},
                   {tab: {url: "https://canvas.ubc.ca/"}}, () => {});
  await new Promise(resolve => setTimeout(resolve, 0));
  assert.deepEqual(stored.latestCaptures.canvas, capture);
  assert.deepEqual(stored.latestModels.canvas.items, []);
  assert.match(stored.syncStatus, /saved locally/);
});

test("the transport runs another registered provider without provider-specific code", async () => {
  const handlers = {};
  const injections = [];
  const chrome = {
    storage: {local: {setAccessLevel: async () => {}, get: async () => ({}),
                      set: async () => {}}},
    runtime: {onInstalled: {addListener: () => {}},
              onMessage: {addListener: fn => { handlers.message = fn; }}},
    alarms: {create: () => {}, onAlarm: {addListener: () => {}}},
    tabs: {query: async query => {
      assert.equal(query.url, "https://moodle.example/*");
      return [{id: 9, status: "complete"}];
    }, create: async () => {}},
    scripting: {executeScript: async args => injections.push(args)}
  };
  const context = {chrome, URL, importScripts: () => {},
    HUB_PROVIDERS: [{id: "moodle", label: "Moodle", origin: "https://moodle.example",
                     tabPattern: "https://moodle.example/*", captureFile: "providers/moodle.js"}]};
  vm.runInNewContext(fs.readFileSync(new URL("./background.js", import.meta.url), "utf8"), context);
  const result = await new Promise(resolve =>
    handlers.message({type: "SYNC_NOW", provider: "moodle"}, {}, resolve));
  assert.equal(result.ok, true);
  assert.equal(injections[0].target.tabId, 9);
  assert.equal(injections[0].files[0], "providers/moodle.js");
});

test("a configured school origin controls custom-provider injection and sender validation", async () => {
  const handlers = {};
  const injections = [];
  const stored = {providerOrigins: {blackboard: "https://bb.example.edu"}};
  const chrome = {
    storage: {local: {setAccessLevel: async () => {}, get: async () => stored,
                      set: async value => Object.assign(stored, value)}},
    runtime: {onInstalled: {addListener: () => {}},
              onMessage: {addListener: fn => { handlers.message = fn; }}},
    alarms: {create: () => {}, onAlarm: {addListener: () => {}}},
    tabs: {query: async query => {
      assert.equal(query.url, "https://bb.example.edu/*");
      return [{id: 4, status: "complete"}];
    }, create: async () => {}},
    scripting: {executeScript: async args => injections.push(args)}
  };
  const context = {chrome, URL, fetch: async () => { throw Error("unexpected upload"); },
    HUB_PROVIDERS: [{id: "blackboard", label: "Blackboard", customOrigin: true,
      captureFile: "providers/blackboard.js"}], importScripts: () => {}};
  vm.runInNewContext(fs.readFileSync(new URL("./background.js", import.meta.url), "utf8"), context);
  const result = await new Promise(resolve =>
    handlers.message({type: "SYNC_NOW", provider: "blackboard"}, {}, resolve));
  assert.equal(result.ok, true);
  assert.equal(injections[0].files[0], "providers/blackboard.js");
  handlers.message({type: "CAPTURE_FAILED", source: "blackboard", error: "fake"},
    {tab: {url: "https://other.example/"}}, () => {});
  await new Promise(resolve => setTimeout(resolve, 0));
  assert.notEqual(stored.syncStatus, "fake");
});
