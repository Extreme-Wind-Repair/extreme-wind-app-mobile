/* rdo-equipes.js — card "Novo projeto" (campos de escolha) + Busca de equipes (#equipes)
 * Reunião Diária / Extreme Wind.  Autônomo: não altera campos, blocos nem funções existentes.
 *
 * O que faz
 *  1) Barra de blocos: acrescenta o 6º item "Equipes" (lupa em SVG). Usa o mesmo mecanismo dos
 *     outros itens (data-block="equipes" -> <div class="block-view" id="equipes">), então o
 *     código existente da barra continua valendo sem nenhuma alteração.
 *  2) Modal "Novo Projeto": mantém Projeto/Cliente/Supervisor/Técnico 1-3 como estão e acrescenta
 *     os campos de escolha (Cliente p/ equipe, Atividade, Abrangência, Formação) e o campo
 *     somente leitura "Equipe" (indicação do sistema; só a alternativa nº 1).
 *  3) Página #equipes: Busca com as mesmas escolhas; lista todas as alternativas.
 *
 * Dados: NÃO ficam neste arquivo, nem no repositório, nem em URL pública. Não há JSON estático nem URL de dados no front.
 *  - Cada consulta é um POST autenticado: EWAuth.post({action:'indicarEquipes', cli, atv, abr, qtd, n}) no backend de LOGIN
 *    (Equipes_login.gs). O servidor só responde a ADMIN, EDITOR e SERVICO; qualquer outro caso volta {ok:false,motivo:'NEGADO'}.
 *  - Perfil sem permissão (ou EWAuth ausente): a lupa e o card NÃO aparecem. Mesmo assim, se o servidor devolver NEGADO/SESSAO
 *    (sessão expirada, perfil alterado), a tela mostra "sem permissão ou sessão expirada" e nunca inventa equipe.
 *  - Requer a página carregar ew-auth.js (EWAuth) antes deste arquivo, ou ao menos até 15 s depois.
 *
 * Técnicos titulares de equipes de qualquer parque do RDO (Blocos 1, 2 e 3) são excluídos NO SERVIDOR, a cada consulta.
 */
(function () {
  'use strict';
  if (window.__rdoEquipesLoaded) return; window.__rdoEquipesLoaded = true;

  var CLIENTES = [['ge', 'GE'], ['siemens', 'Siemens'], ['nordex', 'Nordex']];
  var ATIVIDADES = [
    ['inspecao_cordas', 'Inspeção (cordas)', 'c'], ['mcu', 'MCU (cordas)', 'c'], ['reparo_cordas', 'Reparo (cordas)', 'c'],
    ['troca_tip', 'Troca de TIP (cordas)', 'c'], ['tower_light', 'Tower light (cordas)', 'c'],
    ['hibrida', 'Híbrida (cordas + solo/interna)', 'c'],
    ['reparo_solo', 'Reparo solo', 's'], ['inspecao_solo', 'Inspeção solo', 's'], ['inspecao_interna', 'Inspeção interna', 's']
  ];
  
  function esc(s) { return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]; }); }
  function norm(s) {
    return String(s || '').split(/\s[—–-]\s/)[0].normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase().replace(/[^a-z ]/g, '').replace(/\s+/g, ' ').trim();
  }

  /* ---------- CSS (prefixo rdoeq-, só variáveis já existentes na página) ---------- */
  var css = [
    '.block-btn.rdoeq-tab svg{width:16px;height:16px;flex:none;margin-right:5px;stroke:currentColor;fill:none;stroke-width:2.4;stroke-linecap:round}',
    '.rdoeq-box{background:var(--panel2);border:1px solid var(--line);border-radius:8px;padding:10px 12px;margin:0 0 12px;font-size:13px;color:var(--text)}',
    '.rdoeq-box .rdoeq-rot{font-size:12px;color:var(--muted);text-transform:uppercase;letter-spacing:.02em;margin-bottom:5px}',
    '.rdoeq-sel{display:block;width:100%;margin-top:5px;padding:8px 10px;font-size:14px;background:var(--panel2);border:1px solid var(--line);border-radius:6px;color:var(--text);font-family:inherit}',
    '.rdoeq-sel:focus{outline:none;border-color:var(--brand)}',
    '.rdoeq-pos{margin-top:3px;display:flex;flex-wrap:wrap;gap:2px 12px;font-size:12px;line-height:1.4}',
    '.rdoeq-pos span{color:var(--ok)}',
    'body.light-mode .rdoeq-pos span{color:#0b6b4a}',
    '.rdoeq-cinto{margin-top:10px;padding-top:8px;border-top:1px solid var(--line);font-size:13px;line-height:1.5}',
    '.rdoeq-cinto small{color:var(--muted)}',
    '.rdoeq-cinto .rdoeq-cg{margin-top:6px}',
    '.rdoeq-field{display:block;font-size:12px;color:var(--muted);text-transform:uppercase;letter-spacing:.02em;margin-bottom:12px}',
    '.rdoeq-field[hidden]{display:none}',
    '.rdoeq-memb{padding:2px 0}',
    '.rdoeq-rh small{color:#b42318;font-weight:600;font-size:11.5px}',
    '.rdoeq-memb small,.rdoeq-tag{color:var(--muted);font-size:11.5px}',
    '.rdoeq-foot{font-size:11.5px;color:var(--muted);margin-top:6px}',
    '.rdoeq-foot a{color:var(--brand);cursor:pointer;text-decoration:underline}',
    '.rdoeq-warn{border-left:4px solid var(--warn,#d89a1f);background:var(--panel2);padding:10px 12px;border-radius:6px;margin:0 0 12px;font-size:13px}',
    '.rdoeq-bar{display:flex;flex-wrap:wrap;gap:12px;margin-bottom:14px}',
    '.rdoeq-bar .rdoeq-field{flex:1 1 180px;min-width:0;margin:0}',
    '.rdoeq-team{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:12px 14px;margin-bottom:10px}',
    '.rdoeq-team h3{margin:0 0 6px;font-size:13px;display:flex;justify-content:space-between;gap:8px;flex-wrap:wrap}',
    '.rdoeq-team.folga{opacity:.82;border-style:dashed}',
    '.rdoeq-meta{font-size:11.5px;color:var(--muted);margin:0 0 12px}',
    '.rdoeq-mascote{display:flex;align-items:center;gap:12px;color:var(--muted);font-size:13px;padding:4px 0}',
    '.rdoeq-mascote img{height:72px;width:auto;flex:none;animation:rdoeqFlutua 1.6s ease-in-out infinite;filter:drop-shadow(0 3px 4px rgba(0,0,0,.35))}',
    '.rdoeq-foot img.rdoeq-mini{height:26px;width:auto;vertical-align:middle;margin-right:6px}',
    '@keyframes rdoeqFlutua{0%,100%{transform:translateY(0)}50%{transform:translateY(-5px)}}',
    /* Bloco 3: sem colunas de Bonificação (projetos ainda não iniciados) e certificações na mesma linha do técnico */
    '#b3 .bonus-th,#b3 .bonus-group,#b3 .bonus-td,#b3 .bonus-fill,#b3 .bonus-mot-th,#b3 .bonus-mot-td{display:none !important}',
    '#b3 table thead tr + tr{display:none}',
    '#b3 td.cert-td{white-space:nowrap;min-width:max-content}',
    '#b3 td.cert-td .tech-cert-badges{flex-wrap:nowrap;display:inline-flex;gap:4px;align-items:center}',
    '#b3 td.cert-td .badge-cert{white-space:nowrap}',
    '#b3 .ab-daycol:has(>[data-rh-box]){flex:1 1 630px;min-width:210px;max-width:630px}',
    '#b3 .rh-box[data-rh-box]{width:100%;min-width:0;box-sizing:border-box}',
    '#b3 .rh-box[data-rh-box] .rh-txt{min-width:0;overflow-wrap:anywhere;word-break:break-word;white-space:pre-wrap}',   /* 26/10/2026 (Robson): Observações gerais do Bloco 3 com 3x o comprimento (210 -> 630 px), para o texto não crescer para baixo */
    '@media (prefers-reduced-motion:reduce){.rdoeq-mascote img{animation:none}}'
  ].join('\n');
  var st = document.createElement('style'); st.textContent = css; document.head.appendChild(st);

  /* ---------- dados (sempre ao vivo, POST autenticado) ---------- */
  var PERFIS_OK = ['ADMIN', 'EDITOR', 'SERVICO'];
  function permitido() {
    try { var i = (typeof EWAuth === 'object' && EWAuth && EWAuth.info) ? EWAuth.info() : null; return !!(i && PERFIS_OK.indexOf(String(i.perfil)) >= 0); } catch (e) { return false; }
  }
  var MSG_NEGADO = 'Sem permissão ou sessão expirada.';
  function negadoErr() { var e = new Error(MSG_NEGADO); e.negado = true; return e; }
  function obter(f, n) {
    if (typeof EWAuth !== 'object' || !EWAuth || !EWAuth.post) return Promise.reject(negadoErr());
    return EWAuth.post({ action: 'indicarEquipes', cli: f.cli, atv: f.atv, abr: f.abr, qtd: f.qtd, uf: f.abr === 'exterior' ? '' : (f.uf || ''), n: n || 0 }).then(function (j) {
      if (j && (j.motivo === 'NEGADO' || j.motivo === 'SESSAO')) throw negadoErr();
      if (!j || j.ok !== true || !j.equipes) throw new Error(j && j.error ? j.error : (j && j.motivo ? 'servidor: ' + j.motivo : 'resposta inesperada'));
      return { c: { faltam: j.faltam, aviso_contratacao: j.aviso_contratacao, perfis_contratar: [] }, equipes: j.equipes, vivo: true, gerado_em: j.gerado_em };
    });
  }
  function msgErro(e, prefixo) { return e && e.negado ? MSG_NEGADO : prefixo + ' (' + (e && e.message) + ').'; }
  var CLI_NOME = { ge: 'GE', siemens: 'Siemens', nordex: 'Nordex' };
  function nota1(n) { return (typeof n === 'number' && isFinite(n)) ? n.toFixed(1).replace('.', ',') : ''; }
  function membrosHtml(eq, atv, cli) {
    return eq.membros.map(function (m) {
      var fortes = [];
      if (m.hist) fortes.push('Experiência comprovada na atividade');
      if (m.dias > 0) fortes.push(esc(m.dias) + ' dias em ' + esc(CLI_NOME[cli] || 'cliente'));
      var pos = (m.pontos && m.pontos.length) ? m.pontos : fortes;   // pontos positivos calculados no servidor; sem eles, usa os antigos
      return '<div class="rdoeq-memb">' + esc(m.nome) + ' <small>(' + esc(m.nivel) + ')' + (nota1(m.nota) ? ' · Nota ' + nota1(m.nota) : '') + (m.hist ? '' : ' · sem histórico comprovado na atividade') + '</small>' +
        (m.indisp ? '<div class="rdoeq-rh"><small>INDISPONÍVEL hoje — RH entrar em contato (mat. ' + esc(m.mat) + (m.rh ? ' · ' + esc(m.rh) : '') + ')</small></div>' : '') +
        (pos.length ? '<div class="rdoeq-pos">' + pos.map(function (x) { return '<span>\u2713 ' + esc(x) + '</span>'; }).join('') + '</div>' : '') + '</div>';
    }).join('');
  }

  /* ---------- seletores ---------- */
  function opts(arr, vazioTxt) { return '<option value="">' + vazioTxt + '</option>' + arr.map(function (o) { return '<option value="' + o[0] + '">' + esc(o[1]) + '</option>'; }).join(''); }
  function ler(pref, root) {
    function v(id) { var e = root.querySelector('#' + pref + id); return e ? e.value : ''; }
    var atv = v('Atv'), c = ATIVIDADES.filter(function (a) { return a[0] === atv; })[0], cordas = c && c[2] === 'c';
    return { cli: v('Cli'), atv: atv, abr: v('Abr'), uf: v('Uf'), qtd: cordas ? '3' : v('For'), cordas: cordas };
  }
  function aplicarRegras(pref, root) {
    var abr = root.querySelector('#' + pref + 'Abr').value, selC = root.querySelector('#' + pref + 'Cli'), selA = root.querySelector('#' + pref + 'Atv'), sf = root.querySelector('#' + pref + 'For');
    function restringe(sel, fn) { Array.prototype.forEach.call(sel.options, function (o) { if (!o.value) return; o.disabled = !fn(o.value); o.hidden = o.disabled; if (o.disabled && sel.value === o.value) sel.value = ''; }); }
    restringe(selC, function (v) { return abr !== 'exterior' || v === 'nordex'; });
    restringe(selA, function (v) { var a = ATIVIDADES.filter(function (x) { return x[0] === v; })[0]; return abr !== 'exterior' || a[2] === 'c'; });
    var f = ler(pref, root), ehSolo = f.atv && !f.cordas;
    sf.closest('.rdoeq-field').hidden = !ehSolo; if (!ehSolo) sf.value = '';
    var su = root.querySelector('#' + pref + 'Uf'); if (su) { su.closest('.rdoeq-field').hidden = abr === 'exterior'; if (abr === 'exterior') su.value = ''; }   // UF só vale para projeto no Brasil
  }
  var UFS = 'AC AL AM AP BA CE DF ES GO MA MG MS MT PA PB PE PI PR RJ RN RO RR RS SC SE SP TO'.split(' ');
  function camposHtml(pref) {
    return '<label class="rdoeq-field">Cliente<select class="rdoeq-sel" id="' + pref + 'Cli">' + opts(CLIENTES, 'Selecione…') + '</select></label>' +
      '<label class="rdoeq-field">Atividade<select class="rdoeq-sel" id="' + pref + 'Atv">' + opts(ATIVIDADES, 'Selecione…') + '</select></label>' +
      '<label class="rdoeq-field">Abrangência<select class="rdoeq-sel" id="' + pref + 'Abr"><option value="">Selecione…</option><option value="brasil">Brasil</option><option value="exterior">Exterior</option></select></label>' +
      '<label class="rdoeq-field">Local do projeto (UF)<select class="rdoeq-sel" id="' + pref + 'Uf"><option value="">Não informar</option>' + UFS.map(function (u) { return '<option value="' + u + '">' + u + '</option>'; }).join('') + '</select></label>' +
      '<label class="rdoeq-field" hidden>Formação<select class="rdoeq-sel" id="' + pref + 'For"><option value="">Selecione…</option><option value="2">Dupla</option><option value="3">Trio</option></select></label>';
  }
  function completo(f) { return f.cli && f.atv && f.abr && f.qtd; }

  /* ---------- 2) campos no modal "Novo Projeto" ----------
     Só o necessário: Projeto, Supervisor (originais) + Cliente (lista), Atividade, Abrangência (e Formação p/ solo) + equipe indicada.
     Os campos originais Cliente (texto) e Técnico 1-3 (manuais) ficam ocultos e são PREENCHIDOS por este arquivo, então o
     "Acrescentar" original grava o cliente e os técnicos indicados sem nenhuma mudança na função da página. */

  /* ---------- cintos / EPI por projeto (lista vinda do servidor, atrás do login) ---------- */
  var CINTOS = null, cintosPedido = false;
  var UF_RE = /\s(al|ba|ce|ma|pe|pi|rn|rs|mx|pb|se|sp|rj|es|mg|pr|sc|go|mt|ms|df|to|pa|am|ap|ac|ro|rr)$/;
  function partes(txt) {
    var s = String(txt || '').normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase().replace(/\s+/g, ' ').trim().replace(/^parques?\s+/, '');
    var m = s.match(UF_RE);
    return { full: s, base: m ? s.replace(UF_RE, '') : s, uf: m ? m[1] : '' };
  }
  function carregarCintos() {
    if (CINTOS || cintosPedido || typeof EWAuth !== 'object' || !EWAuth || !EWAuth.post) return;
    cintosPedido = true;
    EWAuth.post({ action: 'indicarEquipes', modo: 'cintos' }).then(function (j) {
      if (!j || j.ok !== true || !j.cintos) { cintosPedido = false; return; }
      CINTOS = j.cintos.map(function (r) { var p = partes(r[1]); return { cli: r[0], nome: r[1].trim(), tec: r[2], linha: r[3], cinto: r[4], ca: r[5], trava: r[6], tal: r[7], full: p.full, base: p.base, uf: p.uf }; });
      var dl = document.getElementById('rdoeqProjList');
      if (dl) { var vistos = {}; dl.innerHTML = CINTOS.filter(function (e) { if (vistos[e.nome]) return false; vistos[e.nome] = 1; return true; }).map(function (e) { return '<option value="' + esc(e.nome) + '" label="' + esc(e.cli) + '"></option>'; }).join(''); }
      mostrarCinto();
    }).catch(function () { cintosPedido = false; });
  }
  function achaCintos(txt) {
    if (!CINTOS) return [];
    var t = partes(txt); if (t.full.length < 3) return [];
    var ex = CINTOS.filter(function (e) { return e.full === t.full; });
    if (ex.length) return ex;
    return CINTOS.filter(function (e) { return e.base === t.base && (!t.uf || !e.uf || t.uf === e.uf); });
  }
  var cintoSujo = false;   // true quando a pessoa digitou no campo: a lista nunca sobrescreve edição humana
  function linhaCinto(e) {
    var l = [];
    if (e.linha) l.push('Linha de vida: ' + e.linha);
    if (e.cinto) l.push('Cinto: ' + e.cinto + (e.ca ? ' (CA ' + e.ca + ')' : ''));
    if (e.trava) l.push('Trava-quedas: ' + e.trava);
    if (e.tal) l.push('Talabarte: ' + e.tal);
    return l.join(' · ');
  }
  function mostrarCinto() {
    var box = document.getElementById('rdoeqMCinto'), inp = document.getElementById('npProjeto'), ta = document.getElementById('npCintos'); if (!box) return;
    var ach = inp ? achaCintos(inp.value) : [];
    if (!ach.length) { box.hidden = true; box.innerHTML = ''; if (ta && !cintoSujo) ta.value = ''; return; }
    var grupos = [], idx = {};
    ach.forEach(function (e) { var k = linhaCinto(e); if (idx[k] === undefined) { idx[k] = grupos.length; grupos.push({ e: e, nomes: [] }); } grupos[idx[k]].nomes.push(e.nome); });
    if (ta && !cintoSujo) ta.value = grupos.map(function (g) { return linhaCinto(g.e); }).join('\n');
    var nomes = []; grupos.forEach(function (g) { g.nomes.forEach(function (n) { if (nomes.indexOf(n) < 0) nomes.push(n); }); });
    var h = '<small>Da lista de cintos: ' + esc(nomes.join(', ')) + ' · ' + esc(ach[0].cli) + '</small>';
    if (grupos.length > 1) h += '<div class="rdoeq-tag">Este nome tem ' + grupos.length + ' configurações na lista. Apague abaixo as linhas que não valem para o projeto.</div>';
    var CLI_ID = { siemens: 'siemens', ge: 'ge', nordex: 'nordex' }, clis = {}; ach.forEach(function (e) { clis[CLI_ID[String(e.cli).toLowerCase()] || ''] = 1; });
    var ids = Object.keys(clis).filter(Boolean), selC = document.getElementById('rdoeqMCli');
    if (selC && ids.length === 1) {
      if (!selC.value) { selC.value = ids[0]; if (selC.value === ids[0]) selC.dispatchEvent(new Event('change', { bubbles: true })); }   // projeto da lista => Cliente preenchido
      else if (selC.value !== ids[0]) h += '<div class="rdoeq-tag">Atenção: na lista de cintos este projeto é do cliente ' + esc(ach[0].cli) + '.</div>';
    }
    box.innerHTML = h; box.hidden = false;
  }

  var ALTS = [], POS = 0;
  function oculta(ov, id) { var e = ov.querySelector('#' + id); if (e) { var l = e.closest('label') || e; l.style.display = 'none'; } return e; }
  function setv(ov, id, v) { var e = ov.querySelector('#' + id); if (e) e.value = v; }
  function tecnicoTxt(m) { return m.nome + (m.uf ? ' \u2014 ' + m.uf : ''); }
  function preencherOriginais(ov, f) {
    setv(ov, 'npCliente', f && f.cli ? (CLI_NOME[f.cli] || '') : '');
    var eq = ALTS[POS];
    for (var i = 1; i <= 3; i++) setv(ov, 'npTecnico' + i, eq && eq.membros[i - 1] ? tecnicoTxt(eq.membros[i - 1]) : '');
  }
  function montarModal() {
    if (!permitido()) return;
    var ov = document.getElementById('novoProjetoOverlay'); if (!ov || ov.querySelector('#rdoeqCard')) return;
    var t1 = ov.querySelector('#npTecnico1'); if (!t1) return;
    var ref = t1.closest('label') || t1;
    oculta(ov, 'npCliente'); oculta(ov, 'npTecnico1'); oculta(ov, 'npTecnico2'); oculta(ov, 'npTecnico3');
    var wrap = document.createElement('div'); wrap.id = 'rdoeqCard';
    wrap.innerHTML = '<label class="modal-field" id="rdoeqDataLbl">Data Prevista Início<input type="date" id="npDataInicio"></label>' + '<div class="rdoeq-box">' + camposHtml('rdoeqM') +
      '<div class="rdoeq-rot">Equipe indicada</div><div id="rdoeqMEq" class="rdoeq-memb" aria-live="polite">Escolha cliente, atividade e abrangência.</div>' +
      '<div class="rdoeq-foot"><a id="rdoeqMProx" hidden>Trocar por outra alternativa</a> <span id="rdoeqMPos"></span></div>' +
      '<div id="rdoeqMCinto" class="rdoeq-cinto" hidden></div>' +
      '<div class="rdoeq-rot" style="margin-top:10px">Cintos de alpinismo (editável)</div><textarea id="npCintos" class="rdoeq-sel" rows="3" placeholder="Preenchido pela lista quando o projeto consta nela. Você pode ajustar, apagar ou escrever."></textarea></div><datalist id="rdoeqProjList"></datalist>';
    ref.parentNode.insertBefore(wrap, ref);
    var inpP = ov.querySelector('#npProjeto');
    if (inpP) { inpP.setAttribute('list', 'rdoeqProjList'); inpP.setAttribute('autocomplete', 'off'); inpP.addEventListener('input', mostrarCinto); inpP.addEventListener('change', mostrarCinto); }
    var taC = wrap.querySelector('#npCintos'); if (taC) taC.addEventListener('input', function () { cintoSujo = true; });
    carregarCintos();
    if (!ganchoData()) { var lblD = wrap.querySelector('#rdoeqDataLbl'); if (lblD) lblD.remove(); }
    wrap.addEventListener('change', function () { aplicarRegras('rdoeqM', wrap); atualizarCard(wrap); });
    wrap.querySelector('#rdoeqMProx').addEventListener('click', function () {
      if (!ALTS.length) return; POS = (POS + 1) % ALTS.length; mostrarEquipe(wrap);
    });
    resetModal();
  }
  /* Data Prevista Início: calendário no modal; grava no campo Data da RD_Parques do novo card (texto dd/mm/aaaa, como o card faz) */
  var gData = false;
  function brData(iso) { var m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(iso || ''); return m ? m[3] + '/' + m[2] + '/' + m[1] : ''; }
  function ganchoData() {
    if (gData) return true;
    if (typeof window.apiPost !== 'function') return false;
    gData = true;
    var orig = window.apiPost;
    window.apiPost = function (payload) {
      var inp = document.getElementById('npDataInicio'), br = inp ? brData(inp.value) : '';
      var novo = payload && payload.action === 'addRow' && payload.sheet === 'RD_Parques' && payload.template && /^b3-novo-/.test(String(payload.template.ParkID));
      var campos = {};
      if (novo) {   /* 26/10/2026: o card novo nascia sem Estado/Tipo/Data/Fabricante; Exterior: Local/Estado/País ficam para digitação manual */
        var ov0 = document.getElementById('novoProjetoOverlay'), f0 = ov0 ? ler('rdoeqM', ov0) : null;
        if (br) campos.Data = "'" + br;
        if (f0) {
          var at0 = ATIVIDADES.filter(function (x) { return x[0] === f0.atv; })[0], cl0 = CLIENTES.filter(function (x) { return x[0] === f0.cli; })[0];
          if (f0.abr === 'brasil' && f0.uf) campos.Estado = f0.uf;
          if (at0) campos.Tipo = at0[1];
          if (cl0) campos.Fabricante = cl0[1];
        }
      }
      var pr = orig.apply(this, arguments);
      if (!novo || !Object.keys(campos).length) return pr;
      var id = payload.template.ParkID;
      return Promise.resolve(pr).then(function (resp) {
        if (!(resp && resp.ok !== false && resp.result && resp.result.newRow)) return resp;
        var seq = Promise.resolve();
        Object.keys(campos).forEach(function (k) { seq = seq.then(function () { return orig({ action: 'updateCell', sheet: 'RD_Parques', row: resp.result.newRow, field: k, value: campos[k] }); }).catch(function () {}); });
        return seq.then(function () {
          var n = 0, t = setInterval(function () {
            var L = (typeof DATA !== 'undefined' && DATA && DATA.parques) || [], p = L.filter(function (x) { return x.ParkID === id; })[0];
            if (p) { Object.keys(campos).forEach(function (k) { p[k] = String(campos[k]).replace(/^'/, ''); }); clearInterval(t); if (typeof renderBlock === 'function') renderBlock('b3'); } else if (++n > 75) clearInterval(t);
          }, 200);
          return resp;
        });
      });
    };
    return true;
  }
  function resetModal() {
    var ov = document.getElementById('novoProjetoOverlay'), wrap = ov && ov.querySelector('#rdoeqCard'); if (!wrap) return;
    ++seqCard; ALTS = []; POS = 0;
    Array.prototype.forEach.call(wrap.querySelectorAll('select'), function (s) { s.value = ''; });
    aplicarRegras('rdoeqM', wrap);
    wrap.querySelector('#rdoeqMEq').textContent = 'Escolha cliente, atividade e abrangência.';
    wrap.querySelector('#rdoeqMProx').hidden = true; wrap.querySelector('#rdoeqMPos').textContent = '';
    cintoSujo = false; var taR = wrap.querySelector('#npCintos'); if (taR) taR.value = '';
    var dI = wrap.querySelector('#npDataInicio'); if (dI) dI.value = '';
    preencherOriginais(ov, null); mostrarCinto();
  }
  var seqCard = 0, seqBusca = 0;
  function mostrarEquipe(wrap) {
    var ov = document.getElementById('novoProjetoOverlay'), box = wrap.querySelector('#rdoeqMEq'), f = ler('rdoeqM', wrap), eq = ALTS[POS];
    box.innerHTML = membrosHtml(eq, f.atv, f.cli) + (eq.avisos && eq.avisos.length ? '<div class="rdoeq-tag">' + esc(eq.avisos.join(' · ')) + '</div>' : '');
    wrap.querySelector('#rdoeqMProx').hidden = ALTS.length < 2;
    wrap.querySelector('#rdoeqMPos').textContent = ALTS.length > 1 ? '(' + (POS + 1) + ' de ' + ALTS.length + ')' : '';
    preencherOriginais(ov, f);
  }
  var MASCOTE = 'assets/mascote-ew-web.png';
  function carregando(txt) { return '<div class="rdoeq-mascote"><img src="' + MASCOTE + '" alt="" aria-hidden="true"><span>' + txt + '</span></div>'; }
  function atualizarCard(wrap) {
    var ov = document.getElementById('novoProjetoOverlay'), box = wrap.querySelector('#rdoeqMEq'), f = ler('rdoeqM', wrap), id = ++seqCard;
    ALTS = []; POS = 0; wrap.querySelector('#rdoeqMProx').hidden = true; wrap.querySelector('#rdoeqMPos').textContent = '';
    preencherOriginais(ov, f);                                        // cliente já vale; técnicos ficam vazios até a equipe chegar
    if (!completo(f)) { box.textContent = 'Escolha cliente, atividade e abrangência.'; return; }
    box.innerHTML = carregando('Montando equipe…');
    obter(f, 5).then(function (r) {
      if (id !== seqCard) return;
      if (!r.equipes.length) { box.textContent = 'Nenhuma alternativa disponível agora (técnicos já alocados em parques).'; return; }
      ALTS = r.equipes; POS = 0; mostrarEquipe(wrap);
      if (r.c.faltam) box.innerHTML += '<div class="rdoeq-tag">' + esc(r.c.aviso_contratacao) + '</div>';
    }).catch(function (e) { if (id === seqCard) box.textContent = msgErro(e, 'Não foi possível montar a equipe agora'); });
  }

  /* ---------- 1) item "Equipes" na barra + 3) página #equipes ---------- */
  var tab, page;
  function montarBarra() {
    if (!permitido()) return;
    var nav = document.getElementById('blockNav'); if (!nav || nav.querySelector('.rdoeq-tab')) return;
    tab = document.createElement('button'); tab.type = 'button'; tab.className = 'block-btn rdoeq-tab'; tab.setAttribute('data-block', 'equipes');
    tab.innerHTML = '<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="10.5" cy="10.5" r="6.5"/><line x1="15.5" y1="15.5" x2="21" y2="21"/></svg>Equipes';
    nav.appendChild(tab);
    page = document.createElement('div'); page.className = 'block-view'; page.id = 'equipes';
    var ultimo = document.getElementById('b5'); (ultimo ? ultimo.parentNode : document.body).insertBefore(page, ultimo ? ultimo.nextSibling : null);
    page.innerHTML = '<div class="rdoeq-bar">' + camposHtml('rdoeqB') + '</div><div id="rdoeqBRes"></div>';
    page.addEventListener('change', function () { aplicarRegras('rdoeqB', page); renderBusca(); });
    tab.addEventListener('click', function () {
      /* O handler original da barra é ligado só aos botões que já existiam; reproduzimos o mesmo efeito. */
      document.querySelectorAll('.block-btn').forEach(function (b) { b.classList.remove('active'); });
      document.querySelectorAll('.block-view').forEach(function (v) { v.classList.remove('active'); });
      tab.classList.add('active'); page.classList.add('active');
      var tb = document.getElementById('b3Toolbar'); if (tb) tb.style.display = 'none';
      try { if (location.hash !== '#equipes') history.replaceState(null, '', location.pathname + location.search + '#equipes'); } catch (e) { }
      renderBusca();
    });
    nav.addEventListener('click', function (e) {
      var b = e.target.closest ? e.target.closest('.block-btn') : null;
      if (b && b !== tab && location.hash === '#equipes') { try { history.replaceState(null, '', location.pathname + location.search); } catch (x) { } }
    });
  }
  function renderBusca() {
    var out = document.getElementById('rdoeqBRes'); if (!out) return;
    var f = ler('rdoeqB', page), id = ++seqBusca;
    if (!completo(f)) { out.innerHTML = '<div class="rdoeq-meta">Escolha cliente, atividade e abrangência.</div>'; return; }
    out.innerHTML = carregando('Montando equipes…');
    obter(f, 0).then(function (r) {
      if (id !== seqBusca) return;
      var ger = r.gerado_em || '';
      var h = '<div class="rdoeq-meta">' + 'Calculado agora, com o Bloco 3 do momento. Base de técnicos da rodada de ' + esc(ger) + '. Técnicos titulares em qualquer parque (ativos, mobilização e tramitação) estão fora das alternativas.' + '</div>';
      if (r.c.faltam) h += '<div class="rdoeq-warn"><b>' + esc(r.c.aviso_contratacao) + '</b>' + (r.c.perfis_contratar && r.c.perfis_contratar.length ? '<br>' + r.c.perfis_contratar.map(esc).join('<br>') : '') + '</div>';
      if (!r.equipes.length) h += '<div class="rdoeq-warn">Nenhuma alternativa disponível agora.</div>';
      r.equipes.forEach(function (eq, i) {
        h += '<div class="rdoeq-team' + (eq.base ? '' : ' folga') + '"><h3><span>Alternativa ' + (i + 1) + '</span><span class="rdoeq-tag">' + (eq.base ? 'base' : 'reserva') + '</span></h3>' + membrosHtml(eq, f.atv, f.cli) +
          (eq.avisos && eq.avisos.length ? '<div class="rdoeq-tag">' + esc(eq.avisos.join(' · ')) + '</div>' : '') + '</div>';
      });
      out.innerHTML = h + '<div class="rdoeq-foot"><img class="rdoeq-mini" src="' + MASCOTE + '" alt="" aria-hidden="true">Indicação do sistema</div>';
    }).catch(function (e) { if (id === seqBusca) out.innerHTML = '<div class="rdoeq-warn">' + esc(msgErro(e, 'Não foi possível montar as equipes agora')) + '</div>'; });
  }
  function irParaEquipes(f) {
    if (!tab) return;
    if (f) {
      var set = function (id, v) { var e = page.querySelector('#rdoeqB' + id); if (e && v) e.value = v; };
      set('Abr', f.abr); set('Uf', f.uf); aplicarRegras('rdoeqB', page); set('Cli', f.cli); set('Atv', f.atv); aplicarRegras('rdoeqB', page); set('For', f.cordas ? '' : f.qtd);
    }
    tab.click();
  }

  /* ---------- autocomplete do nome do técnico na tabela de equipe (26/10/2026, Robson) ----------
     Lista vem ao vivo (POST autenticado, modo 'tecnicos'), fica só em memória; nada embutido no arquivo. */
  var TEC = null, tecAt = 0, tecPedido = null;
  function carregarTecnicos() {
    if (typeof EWAuth !== 'object' || !EWAuth || !EWAuth.post) return;
    if (tecPedido || (TEC && Date.now() - tecAt < 300000)) return;
    tecPedido = EWAuth.post({ action: 'indicarEquipes', modo: 'tecnicos' }).then(function (j) {
      if (j && j.ok && j.tecnicos) { TEC = j.tecnicos.map(function (r) { return { mat: String(r[0]), nome: String(r[1] || ''), nivel: r[2] || '', uf: r[3] || '', sit: r[4] || '', certs: r[5] || [], n: norm(r[1]) }; }); tecAt = Date.now(); }
    }).catch(function () {}).then(function () { tecPedido = null; });
  }
  function buscaTecnicos(q) {
    if (!TEC) return [];
    var t = norm(q).split(' ').filter(Boolean), dig = String(q).trim().replace(/\D/g, '');
    if (!t.length && !dig) return [];
    var somenteNum = /^\s*\d+\s*$/.test(q);
    var r = TEC.filter(function (x) {
      if (somenteNum) return x.mat.indexOf(dig) === 0;
      var w = x.n.split(' ');
      return t.every(function (tk) { return w.some(function (p) { return p.indexOf(tk) === 0; }); });
    });
    r.sort(function (a, b) { var pa = /^Dispon|Reserva/.test(a.sit) ? 0 : 1, pb = /^Dispon|Reserva/.test(b.sit) ? 0 : 1; return pa - pb || a.nome.localeCompare(b.nome); });
    return r.slice(0, 8);
  }
  function autocompleteTecnicos() {
    var box = document.createElement('div'), alvo = null, lista = [], idx = -1;
    box.className = 'rdoeq-ac'; box.hidden = true; document.body.appendChild(box);
    var st2 = document.createElement('style');
    st2.textContent = '.rdoeq-ac{position:fixed;z-index:9999;background:var(--panel,#fff);color:var(--text,#111);border:1px solid var(--line,#ccc);border-radius:8px;box-shadow:0 6px 18px rgba(0,0,0,.35);max-height:290px;overflow:auto;min-width:300px;max-width:min(560px,94vw);font-size:13px}.rdoeq-ac[hidden]{display:none}.rdoeq-ac div{padding:7px 10px;cursor:pointer;border-bottom:1px solid var(--line,#ddd);line-height:1.35}.rdoeq-ac div:last-child{border-bottom:0}.rdoeq-ac div.on,.rdoeq-ac div:hover{background:var(--panel2,#eee)}.rdoeq-ac b{font-variant-numeric:tabular-nums}.rdoeq-ac small{display:block;color:var(--muted,#666);font-size:11.5px}.rdoeq-ac .ok{color:var(--ok,#0b6b4a)}.rdoeq-ac .no{color:#b42318}';
    document.head.appendChild(st2);
    function ehVal1(el) { return el && el.nodeType === 1 && el.matches && el.matches('td[contenteditable][data-field="Val1"]') && el.closest('[data-row]'); }
    function fecha() { box.hidden = true; idx = -1; lista = []; }
    function posiciona() { if (!alvo) return; var r = alvo.getBoundingClientRect(), h = box.offsetHeight || 200, abaixo = window.innerHeight - r.bottom; box.style.left = Math.max(4, Math.min(r.left, window.innerWidth - box.offsetWidth - 4)) + 'px'; box.style.top = (abaixo >= Math.min(h, 220) ? r.bottom + 2 : Math.max(4, r.top - h - 2)) + 'px'; }
    function consulta(td) {
      var txt = td.textContent, seg = txt.split('=')[0], nome = seg.split(/\s[—–-]\s/)[0];
      if (txt.indexOf('=') >= 0 && td.ownerDocument.getSelection && td.ownerDocument.getSelection().anchorOffset > seg.length) return '';   // digitando o substituto: sem sugestão
      return nome.replace(/^\s*\d+\s*·\s*/, '');
    }
    function desenha(td) {
      alvo = td; var q = consulta(td);
      lista = q.trim().length >= 2 ? buscaTecnicos(q) : [];
      if (!lista.length) { fecha(); return; }
      idx = 0;
      box.innerHTML = lista.map(function (x, i) {
        var bad = /Indispon|Em projeto|Alocado/.test(x.sit) && !/encerrando/.test(x.sit);
        return '<div data-i="' + i + '"' + (i === 0 ? ' class="on"' : '') + '><b>' + esc(x.mat) + '</b> · ' + esc(x.nome) + '<small>' + esc((x.uf || '—') + (x.nivel ? '/' + x.nivel : '')) + ' · <span class="' + (bad ? 'no' : 'ok') + '">' + esc(x.sit || '—') + '</span></small></div>';
      }).join('');
      box.hidden = false; posiciona();
    }
    function marca(i) { idx = (i + lista.length) % lista.length; Array.prototype.forEach.call(box.children, function (c, k) { c.className = k === idx ? 'on' : ''; if (k === idx) c.scrollIntoView({ block: 'nearest' }); }); }
    function escolhe(i) {
      var x = lista[i], td = alvo; if (!x || !td) return;
      var partes2 = td.textContent.split('='), resto = partes2.slice(1).join('=').trim();
      var v = x.nome + (x.uf ? ' — ' + x.uf + (x.nivel ? '/' + x.nivel : '') : '');
      td.textContent = v + (resto ? ' = ' + resto : '');
      td.dataset.raw = td.textContent;
      fecha(); td.blur();          // o blur da própria página grava (updateCell RD_Equipe/Val1) e reabrevia o nome
    }
    document.addEventListener('focusin', function (e) { if (ehVal1(e.target)) carregarTecnicos(); });
    document.addEventListener('input', function (e) { if (ehVal1(e.target)) { carregarTecnicos(); desenha(e.target); } });
    document.addEventListener('keydown', function (e) {
      if (box.hidden || !ehVal1(e.target)) return;
      if (e.key === 'ArrowDown') { e.preventDefault(); marca(idx + 1); }
      else if (e.key === 'ArrowUp') { e.preventDefault(); marca(idx - 1); }
      else if (e.key === 'Enter') { e.preventDefault(); escolhe(idx); }
      else if (e.key === 'Escape') { fecha(); }
    }, true);
    document.addEventListener('focusout', function (e) { if (ehVal1(e.target)) setTimeout(fecha, 120); });
    box.addEventListener('pointerdown', function (e) { var d = e.target.closest('[data-i]'); if (!d) return; e.preventDefault(); escolhe(+d.dataset.i); });
    window.addEventListener('scroll', posiciona, true); window.addEventListener('resize', posiciona);
  }

  /* ---------- certificações automáticas na tabela de equipe (26/10/2026, Robson) ----------
     Células "Certificação" VAZIAS mostram selos (BST/ART/IRATA/LOTO GEP/ASO) vindos ao vivo da base de equipes pela matrícula/nome.
     Só exibição: nada é gravado na planilha; texto digitado à mão continua mandando. */
  function certsAuto() {
    var tb = document.querySelectorAll('#b3 td.cert-td'); if (!tb.length) return;   /* só Bloco 3 (Robson, 26/10/2026) */
    if (!TEC) { carregarTecnicos(); if (tecPedido) tecPedido.then(certsAuto); return; }
    Array.prototype.forEach.call(tb, function (td) {
      var tr = td.closest('tr[data-row]'); if (!tr || td.isContentEditable || String(td.dataset.raw || '').trim()) return;
      var n = tr.querySelector('td[data-field="Val1"]'); if (!n) return;
      var txt = String(n.dataset.raw != null && n.dataset.raw !== '' ? n.dataset.raw : n.textContent).split('=')[0];
      var mm = /^\s*(\d+)\s*·/.exec(txt), mat = mm ? mm[1] : null, k = norm(txt.replace(/^\s*\d+\s*·\s*/, '')), x = null;
      if (mat) x = TEC.filter(function (t) { return t.mat === mat; })[0];
      if (!x && k) { var c = TEC.filter(function (t) { return t.n === k; }); if (c.length === 1) x = c[0]; }
      var h = (x && x.certs && x.certs.length) ? '<span class="tech-cert-badges" title="Automático (base de equipes)">' + x.certs.map(function (c) { var st = /vencido/.test(c) ? ' style="border-color:#e0483c;color:#e0483c"' : (/a vencer/.test(c) ? ' style="border-color:#d9b234;color:#d9b234"' : ''); return '<span class="badge-cert"' + st + '>' + esc(c) + '</span>'; }).join('') + '</span>' : '<span class="tech-cert-empty">—</span>';
      if (td.dataset.autoHtml !== h) { td.dataset.autoHtml = h; td.innerHTML = h; }
    });
  }
  function observarCerts() {
    var agenda = 0;
    function roda() { if (agenda) return; agenda = requestAnimationFrame(function () { agenda = 0; try { certsAuto(); } catch (e) {} }); }
    new MutationObserver(roda).observe(document.body, { childList: true, subtree: true });
    document.addEventListener('focusout', function (e) { if (e.target && e.target.matches && e.target.matches('td[data-field="Val1"],td.cert-td')) setTimeout(roda, 250); });
    roda();
  }

  var iniciado = false;
  function init() {
    if (!permitido()) return false;
    if (!iniciado) {
      iniciado = true;
      montarBarra(); montarModal();
      autocompleteTecnicos();
      observarCerts();
      var ov = document.getElementById('novoProjetoOverlay');
      if (ov) new MutationObserver(function () { if (!ov.hidden) { montarModal(); resetModal(); } }).observe(ov, { attributes: true, attributeFilter: ['hidden'] });
      window.addEventListener('hashchange', function () { if (location.hash === '#equipes' && tab) tab.click(); });
    }
    if (location.hash === '#equipes' && tab) tab.click();
    return true;
  }
  function iniciar() {                       // EWAuth/sessão podem chegar depois do DOM: tenta por até 15 s
    if (init()) return;
    var t = 0, h = setInterval(function () { if (init() || ++t >= 15) clearInterval(h); }, 1000);
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', iniciar); else iniciar();
})();
