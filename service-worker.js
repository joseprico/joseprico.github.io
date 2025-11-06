// Service Worker per CN Terrassa - Versió sense caché de JSON externs
const CACHE_NAME = 'cnt-v3';

// Només recursos locals del repo CNT
const urlsToCache = [
  './index.html',
  './debug-pwa.html',
  'https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js',
  'https://cdnjs.cloudflare.com/ajax/libs/jspdf/2.5.1/jspdf.umd.min.js',
  'https://cdnjs.cloudflare.com/ajax/libs/html2canvas/1.4.1/html2canvas.min.js',
  'https://clubnatacioterrassa.cat/wp-content/uploads/CNT_Escut_Blau.png.webp'
];

// Instal·lació
self.addEventListener('install', event => {
  console.log('[SW] Instal·lant v3...');
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then(cache => {
        console.log('[SW] Guardant recursos bàsics');
        return cache.addAll(urlsToCache);
      })
      .catch(error => {
        console.warn('[SW] Alguns recursos no s\'han pogut cachear:', error);
      })
  );
  self.skipWaiting();
});

// Activació
self.addEventListener('activate', event => {
  console.log('[SW] Activant v3...');
  event.waitUntil(
    caches.keys().then(keys => {
      return Promise.all(
        keys.map(key => {
          if (key !== CACHE_NAME) {
            console.log('[SW] Eliminant caché antiga:', key);
            return caches.delete(key);
          }
        })
      );
    })
  );
  return self.clients.claim();
});

// Fetch - CLAU: No interceptar JSON d'altres repos
self.addEventListener('fetch', event => {
  const url = new URL(event.request.url);
  
  // NO interceptar si és:
  // 1. JSON d'altres repos de GitHub Pages
  // 2. APIs externes
  if (
    (url.hostname === 'joseprico.github.io' && !url.pathname.startsWith('/CNT/')) ||
    url.hostname !== 'joseprico.github.io'
  ) {
    // Deixar passar sense interceptar - fetch directe
    return;
  }
  
  // Per recursos del repo CNT: Network First amb fallback a caché
  event.respondWith(
    fetch(event.request)
      .then(response => {
        // Cachear només si és exitós
        if (response && response.status === 200) {
          const responseClone = response.clone();
          caches.open(CACHE_NAME).then(cache => {
            cache.put(event.request, responseClone);
          });
        }
        return response;
      })
      .catch(() => {
        // Si falla la xarxa, buscar en caché
        return caches.match(event.request)
          .then(cachedResponse => {
            if (cachedResponse) {
              console.log('[SW] Servint des de caché:', event.request.url);
              return cachedResponse;
            }
            
            // Pàgina offline per HTML
            if (event.request.headers.get('accept').includes('text/html')) {
              return new Response(
                `<!DOCTYPE html>
                <html lang="ca">
                <head>
                  <meta charset="UTF-8">
                  <meta name="viewport" content="width=device-width, initial-scale=1.0">
                  <title>Offline - CNT Stats</title>
                  <style>
                    * { margin: 0; padding: 0; box-sizing: border-box; }
                    body {
                      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                      background: linear-gradient(135deg, #1e3a8a 0%, #0891b2 100%);
                      color: white;
                      display: flex;
                      justify-content: center;
                      align-items: center;
                      min-height: 100vh;
                      padding: 20px;
                      text-align: center;
                    }
                    .card {
                      background: rgba(255,255,255,0.1);
                      backdrop-filter: blur(10px);
                      border-radius: 20px;
                      padding: 40px;
                      max-width: 400px;
                    }
                    h1 { font-size: 64px; margin: 0 0 20px; }
                    p { margin: 10px 0; font-size: 16px; }
                    button {
                      background: white;
                      color: #1e3a8a;
                      border: none;
                      border-radius: 8px;
                      padding: 15px 30px;
                      font-weight: bold;
                      font-size: 16px;
                      cursor: pointer;
                      margin-top: 20px;
                    }
                    button:hover { opacity: 0.9; }
                  </style>
                </head>
                <body>
                  <div class="card">
                    <h1>📡</h1>
                    <p><strong>Sense connexió</strong></p>
                    <p style="font-size: 14px; opacity: 0.8; margin-top: 15px;">
                      Aquesta pàgina necessita Internet per carregar les dades dels partits
                    </p>
                    <button onclick="location.reload()">🔄 Tornar a intentar</button>
                  </div>
                </body>
                </html>`,
                {
                  headers: { 
                    'Content-Type': 'text/html; charset=utf-8',
                    'Cache-Control': 'no-store'
                  }
                }
              );
            }
            
            // Per altres recursos, retornar error
            return new Response('Network error', {
              status: 408,
              statusText: 'Network timeout'
            });
          });
      })
  );
});

console.log('[SW] Service Worker v3 carregat - JSON externs NO interceptats');
