/* EW-TEMA-EXTERNO v1 (27/11/2026) - aplica o padrao unico (escuro/diurno) nas paginas copiadas de outros sistemas,
   SEM editar os arquivos delas (sao regeneradas por sincronizacao). Roda so no portal (index.html): injeta, em cada iframe
   de mesma origem, uma folha de estilo que remapeia as variaveis de cor da propria pagina para a paleta do Manual de Marca.
   Cores de status (verde/amarelo/vermelho) nao sao remapeadas no escuro; no diurno so o tom do texto e escurecido. */
(function(){
  var D = {BG:'#1E2B38', S:'#03456F', S2:'#055384', LN:'#055384', TX:'#E1EEF6', MU:'#9CC7E8', AC:'#9CC7E8', AX:'#2F6E9C', RING:'rgba(225,238,246,.14)', HOV:'rgba(225,238,246,.07)', SOFT:'rgba(156,199,232,.16)', A1:'#3477C3', A2:'#9CC7E8'};
  var L = {BG:'#FFFFFF', S:'#FFFFFF', S2:'#E1EEF6', LN:'#E1EEF6', TX:'#1E2B38', MU:'#5E6B7A', AC:'#016596', AX:'#9CC7E8', RING:'rgba(5,83,132,.14)', HOV:'rgba(5,83,132,.06)', SOFT:'#E1EEF6', A1:'#016596', A2:'#055384'};
  /* nome da variavel da pagina -> chave da paleta */
  var MAPA = {
    'view-combustivel': {bg:'BG', surface:'S', ink:'TX', ink2:'MU', muted:'MU', grid:'LN', axis:'AX', ring:'RING', hover:'HOV', track:'S2', mid:'S2'},
    'view-efetivo': {bg:'BG', panel:'S', 'panel-2':'S2', border:'LN', text:'TX', muted:'MU', accent:'A1', 'accent-2':'A2'},
    'view-contratacao': {bg:'BG', panel:'S', 'panel-2':'S2', border:'LN', text:'TX', muted:'MU', accent:'A1', 'accent-2':'A2'},
    'view-calibracao': {bg:'BG', card:'S', border:'LN', text:'TX', muted:'MU'},
    'view-estoque': {bg:'BG', card:'S', border:'LN', text:'TX', muted:'MU'},
    'view-equipes': {card:'S', text:'TX', muted:'MU', line:'LN'},
    'view-busca-tecnico': {card:'S', text:'TX', muted:'MU', line:'LN'},
    'view-radar-campo': {bg:'BG', surface:'S', 'surface-2':'S2', border:'LN', text:'TX', 'text-muted':'MU', accent:'AC', 'accent-strong':'AC', 'accent-soft':'SOFT'},
    'view-ehs': {bg:'BG', surface:'S', 'surface-2':'S2', line:'LN', 'line-2':'LN', ink:'TX', 'ink-2':'MU', 'ink-3':'MU', brand:'AC', 'brand-2':'AC', 'brand-soft':'SOFT'},
    'view-ehs-painel': {page:'BG', surface:'S', 'surface-2':'S2', ink:'TX', 'ink-2':'MU', muted:'MU', grid:'LN', border:'RING', accent:'AC', 'accent-soft':'S2'}
  };
  /* diurno: textos de status mais escuros para ler sobre fundo branco (cores de status inalteradas no escuro) */
  var STATUS_DIURNO = '--green:#0B7A55;--amber:#8A5A00;--red:#B3261E;--gray:#5E6B7A;--good-text:#0B7A55;--crit-text:#B3261E;';
  function css(id){
    var m = MAPA[id], d = '', l = '';
    Object.keys(m).forEach(function(k){ d += '--'+k+':'+D[m[k]]+';'; l += '--'+k+':'+L[m[k]]+';'; });
    var corpo = function(P){ return 'background:'+P.BG+' !important;color:'+P.TX+' !important;'; };
    return 'html.ew-dark:root:root{color-scheme:dark;'+d+'}\n'+
           'html.ew-light:root:root{color-scheme:light;'+l+STATUS_DIURNO+'}\n'+
           'html.ew-dark body{'+corpo(D)+'}\nhtml.ew-light body{'+corpo(L)+'}\n'+
           'html.ew-dark body, html.ew-light body{font-family:\'Open Sans\',\'Segoe UI\',Arial,sans-serif;}';
  }
  var FONTE = 'https://fonts.googleapis.com/css2?family=Montserrat:wght@600;700;800&family=Open+Sans:wght@400;600&display=swap';
  function claro(){ return document.body.classList.contains('light-mode'); }
  function marca(fr){
    try{ var d = fr.contentDocument; if (d && d.documentElement){
      d.documentElement.classList.toggle('ew-light', claro()); d.documentElement.classList.toggle('ew-dark', !claro()); } }catch(e){}
  }
  function esconde(d){
    try{
      var re = /(modo\s*(claro|escuro|diurno|noturno))|(tema\s*(claro|escuro))|^[☼☀🌙🌞🌚☾\s]+$/i;
      d.querySelectorAll('button,[role=button],a').forEach(function(b){
        var t = (b.textContent||'').trim(), a = (b.getAttribute('aria-label')||'')+' '+(b.title||'')+' '+(b.id||'');
        if ((t.length < 24 && re.test(t)) || /theme|tema/i.test(a)) b.style.display = 'none';
      });
    }catch(e){}
  }
  function injeta(fr){
    try{
      var id = fr.id, d = fr.contentDocument;
      if (!MAPA[id] || !d || !d.head || d.getElementById('ew-tema-ext')) { marca(fr); return; }
      var st = d.createElement('style'); st.id = 'ew-tema-ext'; st.textContent = css(id); d.head.appendChild(st);
      var lk = d.createElement('link'); lk.rel = 'stylesheet'; lk.href = FONTE; d.head.appendChild(lk);
      marca(fr); esconde(d); setTimeout(function(){ esconde(d); }, 1500);
    }catch(e){}
  }
  function todos(){ Object.keys(MAPA).forEach(function(id){ var fr = document.getElementById(id); if (fr) marca(fr); }); }
  (window.EW_HOOKS = window.EW_HOOKS || []).push(todos);
  Object.keys(MAPA).forEach(function(id){
    var fr = document.getElementById(id); if (!fr) return;
    fr.addEventListener('load', function(){ injeta(fr); });
    injeta(fr);
  });
})();
