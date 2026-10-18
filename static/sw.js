const CACHE='khamaswadi-v2';
self.addEventListener('install',event=>event.waitUntil(caches.open(CACHE).then(cache=>cache.addAll(['/','/static/style.css']))));
self.addEventListener('fetch',event=>event.respondWith(fetch(event.request).catch(()=>caches.match(event.request))));
