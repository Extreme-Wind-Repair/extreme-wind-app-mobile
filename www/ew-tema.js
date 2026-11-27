/* EW-TEMA v1 (27/11/2026) - alternancia escuro/diurno para todo o portal.
   Chave unica 'reuniaoTheme' ('light' | 'dark'; padrao = dark). Mesma origem: o evento 'storage' sincroniza as abas/iframes. */
(function(){
  if (window.__ewTema) return; window.__ewTema = 1;
  var KEY = 'reuniaoTheme', mem = null;
  function get(){ var v = null; try{ v = localStorage.getItem(KEY); }catch(e){ v = mem; } return v === 'light' ? 'light' : 'dark'; }
  function set(v){ mem = v; try{ localStorage.setItem(KEY, v); }catch(e){} }
  var inicial = get();
  /* cores para graficos Chart.js (lidas na montagem do grafico) */
  window.EWC = inicial === 'light'
    ? {text:'#1E2B38', muted:'#5E6B7A', grid:'#E1EEF6', panel:'#FFFFFF'}
    : {text:'#E1EEF6', muted:'#9CC7E8', grid:'rgba(156,199,232,.28)', panel:'#03456F'};
  function rotulo(){
    var b = document.getElementById('themeToggleBtn');
    if (b) b.textContent = document.body.classList.contains('light-mode') ? '🌙 Modo Noturno' : '☀️ Modo Diurno';
    if (typeof window.syncTopBtns === 'function'){ try{ window.syncTopBtns(); }catch(e){} }
  }
  function aplica(){
    if (!document.body) return;
    document.body.classList.toggle('light-mode', get() === 'light');
    rotulo();
    (window.EW_HOOKS || []).forEach(function(f){ try{ f(); }catch(e){} });
    if (window.EW_RECARREGA && get() !== inicial){ location.reload(); }
  }
  window.__ewTemaAplica = aplica;
  window.toggleTheme = function(){
    set(get() === 'light' ? 'dark' : 'light');
    aplica();
    try{
      var fr = document.getElementsByTagName('iframe');
      for (var i = 0; i < fr.length; i++){ try{ var w = fr[i].contentWindow; if (w && w.__ewTemaAplica) w.__ewTemaAplica(); }catch(e){} }
    }catch(e){}
  };
  window.addEventListener('storage', function(e){ if (e.key === KEY || e.key === null) aplica(); });
  function init(){
    aplica();
    if (window.self !== window.top){ var b = document.getElementById('themeToggleBtn'); if (b) b.style.display = 'none'; }
  }
  if (document.body) init();
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init); /* botao do cabecalho so existe depois */
})();
