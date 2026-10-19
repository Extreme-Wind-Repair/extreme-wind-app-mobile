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
 * Técnicos titulares de equipes do Bloco 3 ("Em tramitação") são excluídos NO SERVIDOR, a cada consulta.
 */
(function () {
  'use strict';
  if (window.__rdoEquipesLoaded) return; window.__rdoEquipesLoaded = true;

  var CLIENTES = [['ge', 'GE'], ['siemens', 'Siemens'], ['nordex', 'Nordex']];
  var ATIVIDADES = [
    ['inspecao_cordas', 'Inspeção (cordas)', 'c'], ['mcu', 'MCU (cordas)', 'c'], ['reparo_cordas', 'Reparo (cordas)', 'c'],
    ['troca_tip', 'Troca de TIP (cordas)', 'c'], ['tower_light', 'Tower light (cordas)', 'c'],
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
    '.rdoeq-field{display:block;font-size:12px;color:var(--muted);text-transform:uppercase;letter-spacing:.02em;margin-bottom:12px}',
    '.rdoeq-field[hidden]{display:none}',
    '.rdoeq-memb{padding:2px 0}',
    '.rdoeq-memb small,.rdoeq-tag{color:var(--muted);font-size:11.5px}',
    '.rdoeq-foot{font-size:11.5px;color:var(--muted);margin-top:6px}',
    '.rdoeq-foot a{color:var(--brand);cursor:pointer;text-decoration:underline}',
    '.rdoeq-warn{border-left:4px solid var(--warn,#d89a1f);background:var(--panel2);padding:10px 12px;border-radius:6px;margin:0 0 12px;font-size:13px}',
    '.rdoeq-bar{display:flex;flex-wrap:wrap;gap:12px;margin-bottom:14px}',
    '.rdoeq-bar .rdoeq-field{flex:1 1 180px;min-width:0;margin:0}',
    '.rdoeq-team{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:12px 14px;margin-bottom:10px}',
    '.rdoeq-team h3{margin:0 0 6px;font-size:13px;display:flex;justify-content:space-between;gap:8px;flex-wrap:wrap}',
    '.rdoeq-team.folga{opacity:.82;border-style:dashed}',
    '.rdoeq-meta{font-size:11.5px;color:var(--muted);margin:0 0 12px}'
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
    return EWAuth.post({ action: 'indicarEquipes', cli: f.cli, atv: f.atv, abr: f.abr, qtd: f.qtd, n: n || 0 }).then(function (j) {
      if (j && (j.motivo === 'NEGADO' || j.motivo === 'SESSAO')) throw negadoErr();
      if (!j || j.ok !== true || !j.equipes) throw new Error(j && j.error ? j.error : (j && j.motivo ? 'servidor: ' + j.motivo : 'resposta inesperada'));
      return { c: { faltam: j.faltam, aviso_contratacao: j.aviso_contratacao, perfis_contratar: [] }, equipes: j.equipes, vivo: true, gerado_em: j.gerado_em };
    });
  }
  function msgErro(e, prefixo) { return e && e.negado ? MSG_NEGADO : prefixo + ' (' + (e && e.message) + ').'; }
  function membrosHtml(eq, atv) {
    return eq.membros.map(function (m) {
      return '<div class="rdoeq-memb">' + esc(m.nome) + ' <small>(' + esc(m.nivel) + ')' + (m.hist ? '' : ' · sem histórico comprovado na atividade') + '</small></div>';
    }).join('');
  }

  /* ---------- seletores ---------- */
  function opts(arr, vazioTxt) { return '<option value="">' + vazioTxt + '</option>' + arr.map(function (o) { return '<option value="' + o[0] + '">' + esc(o[1]) + '</option>'; }).join(''); }
  function ler(pref, root) {
    function v(id) { var e = root.querySelector('#' + pref + id); return e ? e.value : ''; }
    var atv = v('Atv'), c = ATIVIDADES.filter(function (a) { return a[0] === atv; })[0], cordas = c && c[2] === 'c';
    return { cli: v('Cli'), atv: atv, abr: v('Abr'), qtd: cordas ? '3' : v('For'), cordas: cordas };
  }
  function aplicarRegras(pref, root) {
    var abr = root.querySelector('#' + pref + 'Abr').value, selC = root.querySelector('#' + pref + 'Cli'), selA = root.querySelector('#' + pref + 'Atv'), sf = root.querySelector('#' + pref + 'For');
    function restringe(sel, fn) { Array.prototype.forEach.call(sel.options, function (o) { if (!o.value) return; o.disabled = !fn(o.value); o.hidden = o.disabled; if (o.disabled && sel.value === o.value) sel.value = ''; }); }
    restringe(selC, function (v) { return abr !== 'exterior' || v === 'nordex'; });
    restringe(selA, function (v) { var a = ATIVIDADES.filter(function (x) { return x[0] === v; })[0]; return abr !== 'exterior' || a[2] === 'c'; });
    var f = ler(pref, root), ehSolo = f.atv && !f.cordas;
    sf.closest('.rdoeq-field').hidden = !ehSolo; if (!ehSolo) sf.value = '';
  }
  function camposHtml(pref) {
    return '<label class="rdoeq-field">Cliente (para equipe)<select class="rdoeq-sel" id="' + pref + 'Cli">' + opts(CLIENTES, 'Selecione…') + '</select></label>' +
      '<label class="rdoeq-field">Atividade<select class="rdoeq-sel" id="' + pref + 'Atv">' + opts(ATIVIDADES, 'Selecione…') + '</select></label>' +
      '<label class="rdoeq-field">Abrangência<select class="rdoeq-sel" id="' + pref + 'Abr"><option value="">Selecione…</option><option value="brasil">Brasil</option><option value="exterior">Exterior</option></select></label>' +
      '<label class="rdoeq-field" hidden>Formação<select class="rdoeq-sel" id="' + pref + 'For"><option value="">Selecione…</option><option value="2">Dupla</option><option value="3">Trio</option></select></label>';
  }
  function completo(f) { return f.cli && f.atv && f.abr && f.qtd; }

  /* ---------- 2) campos no modal "Novo Projeto" ---------- */
  function montarModal() {
    if (!permitido()) return;
    var ov = document.getElementById('novoProjetoOverlay'); if (!ov || ov.querySelector('#rdoeqCard')) return;
    var erro = ov.querySelector('#npErro'); if (!erro) return;
    var wrap = document.createElement('div'); wrap.id = 'rdoeqCard';
    wrap.innerHTML = '<div class="rdoeq-box"><div class="rdoeq-rot">Indicação de equipe</div>' + camposHtml('rdoeqM') +
      '<div class="rdoeq-rot">Equipe</div><div id="rdoeqMEq" class="rdoeq-memb" aria-live="polite">Escolha cliente, atividade e abrangência.</div>' +
      '<div class="rdoeq-foot">Indicação do sistema · <a id="rdoeqMVer">ver outras alternativas</a></div></div>';
    erro.parentNode.insertBefore(wrap, erro);
    wrap.addEventListener('change', function () { aplicarRegras('rdoeqM', wrap); atualizarCard(wrap); });
    wrap.querySelector('#rdoeqMVer').addEventListener('click', function () {
      var f = ler('rdoeqM', wrap); ov.hidden = true; irParaEquipes(f);
    });
    atualizarCard(wrap);
  }
  var seqCard = 0, seqBusca = 0;
  function atualizarCard(wrap) {
    var box = wrap.querySelector('#rdoeqMEq'), f = ler('rdoeqM', wrap), id = ++seqCard;
    if (!completo(f)) { box.textContent = 'Escolha cliente, atividade e abrangência.'; return; }
    box.textContent = 'Montando equipe…';
    obter(f, 1).then(function (r) {
      if (id !== seqCard) return;
      if (!r.equipes.length) { box.textContent = 'Nenhuma alternativa disponível agora (técnicos em tramitação no Bloco 3).'; return; }
      box.innerHTML = membrosHtml(r.equipes[0], f.atv) + (r.c.faltam ? '<div class="rdoeq-tag">' + esc(r.c.aviso_contratacao) + '</div>' : '') +
        (r.equipes[0].avisos && r.equipes[0].avisos.length ? '<div class="rdoeq-tag">' + esc(r.equipes[0].avisos.join(' · ')) + '</div>' : '');
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
    out.innerHTML = '<div class="rdoeq-meta">Montando equipes…</div>';
    obter(f, 0).then(function (r) {
      if (id !== seqBusca) return;
      var ger = r.gerado_em || '';
      var h = '<div class="rdoeq-meta">' + 'Calculado agora, com o Bloco 3 do momento. Base de técnicos da rodada de ' + esc(ger) + '. Titulares de equipes do Bloco 3 estão fora das alternativas.' + '</div>';
      if (r.c.faltam) h += '<div class="rdoeq-warn"><b>' + esc(r.c.aviso_contratacao) + '</b>' + (r.c.perfis_contratar && r.c.perfis_contratar.length ? '<br>' + r.c.perfis_contratar.map(esc).join('<br>') : '') + '</div>';
      if (!r.equipes.length) h += '<div class="rdoeq-warn">Nenhuma alternativa disponível agora.</div>';
      r.equipes.forEach(function (eq, i) {
        h += '<div class="rdoeq-team' + (eq.base ? '' : ' folga') + '"><h3><span>Alternativa ' + (i + 1) + '</span><span class="rdoeq-tag">' + (eq.base ? 'base' : 'reserva') + '</span></h3>' + membrosHtml(eq, f.atv) +
          (eq.avisos && eq.avisos.length ? '<div class="rdoeq-tag">' + esc(eq.avisos.join(' · ')) + '</div>' : '') + '</div>';
      });
      out.innerHTML = h + '<div class="rdoeq-foot">Indicação do sistema</div>';
    }).catch(function (e) { if (id === seqBusca) out.innerHTML = '<div class="rdoeq-warn">' + esc(msgErro(e, 'Não foi possível montar as equipes agora')) + '</div>'; });
  }
  function irParaEquipes(f) {
    if (!tab) return;
    if (f) {
      var set = function (id, v) { var e = page.querySelector('#rdoeqB' + id); if (e && v) e.value = v; };
      set('Abr', f.abr); aplicarRegras('rdoeqB', page); set('Cli', f.cli); set('Atv', f.atv); aplicarRegras('rdoeqB', page); set('For', f.cordas ? '' : f.qtd);
    }
    tab.click();
  }

  var iniciado = false;
  function init() {
    if (!permitido()) return false;
    if (!iniciado) {
      iniciado = true;
      montarBarra(); montarModal();
      var ov = document.getElementById('novoProjetoOverlay');
      if (ov) new MutationObserver(function () { if (!ov.hidden) montarModal(); }).observe(ov, { attributes: true, attributeFilter: ['hidden'] });
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
