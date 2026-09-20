const CACHE="astro-nifty-mobile-v1";
self.addEventListener("install",e=>e.waitUntil(caches.open(CACHE).then(c=>c.addAll(["./","./index.html","./manifest.webmanifest","./icons/icon.svg"]))));
self.addEventListener("activate",e=>e.waitUntil(self.clients.claim()));
self.addEventListener("fetch",e=>{if(e.request.method!=="GET")return;e.respondWith(caches.match(e.request).then(c=>c||fetch(e.request).catch(()=>caches.match("./"))));});
