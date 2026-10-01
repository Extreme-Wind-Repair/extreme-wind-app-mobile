// Service Worker do painel Extreme Wind — Logística & Frotas
// Estrategia: "network-first" para as paginas HTML (sempre tenta buscar a versao
// mais recente, ja que os dashboards sao atualizados diariamente), com fallback
// pro cache quando estiver offline. Para imagens/assets estaticos, usa cache-first
// (nao mudam com frequencia).

// v4 (01/10/2026, autorizado por Robson): arquivos de DADOS (.json, ex.: calibracao/data.json) e
// requisicoes a outros dominios passaram a ser "network-first". Antes eram "cache-first" e o app
// ficava preso na primeira copia do data.json (painel de Calibracao mostrava 21/09 mesmo com
// versoes novas publicadas).
// Bump este numero (v2 -> v3 -> v4...) sempre que o menu/estrutura do
// index.html mudar de forma relevante -- forca todo cliente que ja tinha o
// app/site aberto a descartar o cache antigo e buscar tudo de novo na
// proxima visita, em vez de ficar preso numa versao antiga do menu.
const CACHE_NAME = "extreme-wind-v4";
const PRECACHE_URLS = [
  "./",
  "./index.html",
  "./dashboard-nossas-demandas.html",
  "./dashboard-resumo-equipes.html",
  "./dashboard-frota-manutencao.html",
  "./dashboard-boletos.html",
  "./dashboard-envios-logisticos.html",
  "./manifest.json",
  "./assets/icon-192.png",
  "./assets/icon-512.png",
  "./assets/logo-extreme-wind-white.png",
  "./assets/logo-extreme-wind-color.png",
  "./assets/icone-helice-white.png",
  "./assets/icone-helice-color.png",
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) =>
      Promise.all(
        PRECACHE_URLS.map((url) =>
          fetch(url, { cache: "no-store" }).then((res) => cache.put(url, res)).catch(() => {})
        )
      )
    )
  );
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE_NAME).map((k) => caches.delete(k)))
    )
  );
  self.clients.claim();
});

self.addEventListener("fetch", (event) => {
  const req = event.request;
  if (req.method !== "GET") return;

  const isHTML = req.mode === "navigate" || (req.headers.get("accept") || "").includes("text/html");
  const url = new URL(req.url);
  const sameOrigin = url.origin === self.location.origin;
  const isData = !sameOrigin || url.pathname.endsWith(".json");

  if (isHTML) {
    // network-first: dados de hoje em primeiro lugar, cache so como reserva offline
    event.respondWith(
      fetch(req, { cache: "no-store" })
        .then((res) => {
          const copy = res.clone();
          caches.open(CACHE_NAME).then((cache) => cache.put(req, copy));
          return res;
        })
        .catch(() => caches.match(req).then((cached) => cached || caches.match("./index.html")))
    );
  } else if (isData) {
    // network-first pra dados (.json) e requisicoes a outros dominios: sempre o mais novo,
    // cache so como reserva offline (e so guarda respostas OK)
    event.respondWith(
      fetch(req, sameOrigin ? { cache: "no-store" } : undefined)
        .then((res) => {
          if (res && res.ok) {
            const copy = res.clone();
            caches.open(CACHE_NAME).then((cache) => cache.put(req, copy));
          }
          return res;
        })
        .catch(() => caches.match(req))
    );
  } else {
    // cache-first pra imagens/estaticos
    event.respondWith(
      caches.match(req).then((cached) => cached || fetch(req).then((res) => {
        const copy = res.clone();
        caches.open(CACHE_NAME).then((cache) => cache.put(req, copy));
        return res;
      }).catch(() => cached))
    );
  }
});
