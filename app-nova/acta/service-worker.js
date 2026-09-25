// Service Worker — CNT Waterpolo v2 (acta en directe)
// Network-first amb fallback a cache. Només recursos GET del mateix origen.
const CACHE_NAME = 'cntv2-acta-v2';

const PRECACHE = [
  './',
  './index.html'
];

self.addEventListener('install', event => {
  console.log('[SW acta] Instal·lant', CACHE_NAME);
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then(cache => cache.addAll(PRECACHE))
      .catch(err => console.warn('[SW acta] Precache incomplet:', err))
  );
  self.skipWaiting();
});

self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys().then(keys => Promise.all(
      keys.map(key => {
        if (key !== CACHE_NAME && key.startsWith('cntv2-acta-')) {
          console.log('[SW acta] Eliminant cache antiga:', key);
          return caches.delete(key);
        }
      })
    ))
  );
  return self.clients.claim();
});

self.addEventListener('fetch', event => {
  const url = new URL(event.request.url);

  // No interceptar: peticions no-GET (Firebase/Firestore escriuen amb POST)
  // ni altres orígens (gstatic, RTDB, CDNs...). Fetch directe.
  if (event.request.method !== 'GET' || url.origin !== self.location.origin) {
    return;
  }

  // Network-first amb fallback a cache: sempre intentar la versió nova
  // primer, però funcionar a la piscina sense cobertura.
  event.respondWith(
    fetch(event.request)
      .then(response => {
        if (response && response.status === 200) {
          const clone = response.clone();
          caches.open(CACHE_NAME).then(cache => cache.put(event.request, clone));
        }
        return response;
      })
      .catch(() => caches.match(event.request).then(cached => {
        if (cached) return cached;
        if ((event.request.headers.get('accept') || '').includes('text/html')) {
          return new Response(
            '<!DOCTYPE html><html lang="ca"><head><meta charset="UTF-8"><title>Sense connexió</title></head>' +
            '<body style="font-family:sans-serif;background:#f1f5f9;color:#0f172a;text-align:center;padding:60px 20px;">' +
            '<h1>📡 Sense connexió</h1><p>No es pot carregar l\'acta. Revisa la connexió i torna-ho a provar.</p></body></html>',
            { headers: { 'Content-Type': 'text/html; charset=utf-8' } }
          );
        }
      }))
  );
});
