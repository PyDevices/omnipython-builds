// SPDX-FileCopyrightText: 2026 Brad Barnett
//
// SPDX-License-Identifier: MIT

// The all-apps page's service worker. It keeps one copy of the page and its
// runtime per build, so the page opens offline. scripts/build_wasm_allapps.py
// writes the build's hash in place of BUILD, so a new build is a new worker:
// the browser installs it beside the running one, the page offers a reload,
// and the old build's copy is deleted once the new one takes over.
const BUILD = "__BUILD__";
const CACHE = "allapps-" + BUILD;
const FILES = [
  "./",
  "manifest.webmanifest",
  "icon.svg",
  "icon-maskable.svg",
  "micropython.mjs",
  "micropython.wasm",
  "allapps.json",
];
// Kept when first fetched rather than with the page.
const LATER = /\/(detect\.mjs|ort\/[^/]+)$/;

self.addEventListener("install", (event) => {
  // "no-cache" asks the server whether its copy changed, so a build never
  // stores a file the HTTP cache kept from the build before.
  event.waitUntil(caches.open(CACHE).then((cache) =>
    cache.addAll(FILES.map((url) => new Request(url, { cache: "no-cache" })))));
});

self.addEventListener("activate", (event) => {
  event.waitUntil(caches.keys().then((keys) => Promise.all(
    keys.filter((key) => key.startsWith("allapps-") && key !== CACHE).map((key) => caches.delete(key)),
  )).then(() => self.clients.claim()));
});

self.addEventListener("message", (event) => {
  if (event.data === "update") self.skipWaiting();
});

self.addEventListener("fetch", (event) => {
  const request = event.request;
  if (request.method !== "GET" || new URL(request.url).origin !== location.origin) return;
  // Every address of the page (?home=watch, ?app=clock) is the same page.
  const key = request.mode === "navigate" ? "./" : request;
  event.respondWith(caches.open(CACHE).then((cache) =>
    cache.match(key, { ignoreSearch: true }).then((hit) => hit || fetch(request).then((response) => {
      // Object detection's ONNX Runtime (30 MB) isn't fetched with the page:
      // it is kept the first time Detect loads it, so Detect opens offline
      // after that too. Its model is kept by the page itself.
      if (response.ok && LATER.test(new URL(request.url).pathname)) cache.put(request, response.clone());
      return response;
    }))));
});
