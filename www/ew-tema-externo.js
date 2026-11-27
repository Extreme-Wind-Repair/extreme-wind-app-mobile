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

  /* Correcoes SO do modo escuro: estas paginas tem fundos claros fixos no codigo (nao usam variaveis). */
  var EQ = 'html.ew-dark:root:root{--ew-gelo:#055384;--ew-noite:#E1EEF6;}\nhtml.ew-dark #ganttCampo .gc-fixa{background:#03456F !important;}\n'+
    'html.ew-dark .card, html.ew-dark .grid-gantt, html.ew-dark select, html.ew-dark input{background:#03456F !important;color:#E1EEF6 !important;border-color:#055384 !important;}\n'+
    'html.ew-dark th, html.ew-dark th.gc-fixa, html.ew-dark th.ocultar, html.ew-dark h3, html.ew-dark .chip, html.ew-dark .niv, html.ew-dark .kpi.claro{background:#055384 !important;color:#E1EEF6 !important;}\n'+
    'html.ew-dark th.gc-hoje{background:#2F6E9C !important;color:#fff !important;}\n'+
    'html.ew-dark td, html.ew-dark td.k, html.ew-dark td.hj, html.ew-dark td.nt{background:#03456F !important;color:#E1EEF6 !important;}\n'+
    'html.ew-dark button:not(.ew-keep){background:#055384 !important;color:#E1EEF6 !important;border-color:#2F6E9C !important;}';
  var CAL = 'html.ew-dark:root:root{--green-bg:rgba(18,168,116,.20);--amber-bg:rgba(216,154,43,.22);--red-bg:rgba(224,72,60,.22);}\n'+
    'html.ew-dark td.row-ok{background:rgba(18,168,116,.20) !important;color:#E1EEF6 !important;}\n'+
    'html.ew-dark td.row-vence{background:rgba(216,154,43,.22) !important;color:#E1EEF6 !important;}\n'+
    'html.ew-dark .status-badge.ok{background:rgba(18,168,116,.22) !important;color:#5EE0B0 !important;}\n'+
    'html.ew-dark .status-badge.vence{background:rgba(216,154,43,.25) !important;color:#F0B84F !important;}\n'+
    'html.ew-dark a.cert-btn{background:#055384 !important;color:#E1EEF6 !important;}\n'+
    'html.ew-dark th.gridjs-th, html.ew-dark .gridjs-th{background:#055384 !important;color:#E1EEF6 !important;}\n'+
    'html.ew-dark .gridjs-wrapper, html.ew-dark .gridjs-table, html.ew-dark tbody.gridjs-tbody, html.ew-dark td.gridjs-td, html.ew-dark .gridjs-footer, html.ew-dark .gridjs-container{background:#03456F !important;color:#E1EEF6 !important;border-color:#055384 !important;}\n'+
    'html.ew-dark .gridjs-search-input, html.ew-dark .gridjs-pagination button, html.ew-dark .gridjs-pagination .gridjs-summary{background:#055384 !important;color:#E1EEF6 !important;border-color:#2F6E9C !important;}';
  var EST = 'html.ew-dark th, html.ew-dark th.num{background:#055384 !important;color:#E1EEF6 !important;}\n'+
    'html.ew-dark div.kpi-body{background:#055384 !important;color:#E1EEF6 !important;}\n'+
    'html.ew-dark span.badge{background:rgba(237,125,49,.22) !important;color:#F4A261 !important;}\n'+
    'html.ew-dark span.badge.fard, html.ew-dark span.badge.na{background:rgba(156,199,232,.18) !important;color:#9CC7E8 !important;}\n'+
    'html.ew-dark span.badge.acc{background:rgba(160,110,220,.24) !important;color:#C9A8F0 !important;}';
  var EXTRA = {'view-equipes':EQ, 'view-busca-tecnico':EQ, 'view-calibracao':CAL, 'view-estoque':EST};

  /* Padronizacao (ambos os modos): Montserrat nos titulos/cabecalhos, Open Sans no texto; tamanhos unificados (exceto Equipes, que e denso). */
  var FAM = 'html body :where(*:not(svg):not(svg *):not(code):not(pre):not(kbd)){font-family:\'Open Sans\',\'Segoe UI\',Arial,sans-serif !important;}\n'+
    'html body h1, html body h2, html body h3, html body th, html body .pw-modal-title{font-family:\'Montserrat\',\'Segoe UI\',Arial,sans-serif !important;}\n';
  var TAM = 'html body h1{font-size:24px !important;font-weight:800;}\nhtml body h2{font-size:17px !important;}\nhtml body h3{font-size:15px !important;}\n'+
    'html body th{font-size:11.5px !important;font-weight:700;}\nhtml body td{font-size:13px !important;}\n';
  var SEM_TAM = {'view-equipes':1, 'view-busca-tecnico':1};
  /* status mais claros no escuro (mesmo significado) */
  var ST_ESC = 'html.ew-dark:root:root{--green:#3DDC97;--red:#FF7B72;--amber:#F2B84B;--gray:#9CC7E8;--crit-text:#FF7B72;--good-text:#3DDC97;}\n';
  var CAL2 = 'html.ew-dark .kpi .label{color:#9CC7E8 !important;}\nhtml.ew-dark .kpi .value{color:#E1EEF6 !important;}\nhtml.ew-dark .kpi.warn .value{color:#F2B84B !important;}\nhtml.ew-dark .kpi.risk .value{color:#FF7B72 !important;}\nhtml.ew-dark .panel:not(.panel-dark) h2{color:#E1EEF6 !important;}\n';
  var EST2 = 'html.ew-dark:root:root{--c-red:#FF7B72;}\n'+
    'html.ew-dark .dash-title .t1, html.ew-dark .updated b{color:#E1EEF6 !important;}\nhtml.ew-dark .kpi-body .value{color:#E1EEF6 !important;}\n';
  var EQ2 = 'html.ew-dark td[style*="background"]{background:#03456F !important;}\n';
  /* diurno: textos de status mais escuros para ler sobre fundo branco (cores de status inalteradas no escuro) */
  var STATUS_DIURNO = '--green:#0B7A55;--amber:#8A5A00;--red:#B3261E;--gray:#5E6B7A;--good-text:#0B7A55;--crit-text:#B3261E;';
  function css(id){
    var m = MAPA[id], d = '', l = '';
    Object.keys(m).forEach(function(k){ d += '--'+k+':'+D[m[k]]+';'; l += '--'+k+':'+L[m[k]]+';'; });
    var corpo = function(P){ return 'background:'+P.BG+' !important;color:'+P.TX+' !important;'; };
    var ex = (EXTRA[id] ? '\n'+EXTRA[id] : '') + '\n' + FAM + (SEM_TAM[id] ? '' : TAM) + ST_ESC + (id==='view-calibracao'?CAL2:'') + (id==='view-estoque'?EST2:'') + (/equipes|busca/.test(id)?EQ2:'');
    return 'html.ew-dark:root:root{color-scheme:dark;'+d+'}\n'+
           'html.ew-light:root:root{color-scheme:light;'+l+STATUS_DIURNO+'}\n'+
           'html.ew-dark body{'+corpo(D)+'}\nhtml.ew-light body{'+corpo(L)+'}\n'+
           'html.ew-dark body, html.ew-light body{font-family:\'Open Sans\',\'Segoe UI\',Arial,sans-serif;}'+ex;
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
