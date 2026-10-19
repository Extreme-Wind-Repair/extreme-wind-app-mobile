/* Acesso Extreme Wind — cliente do backend de login (Apps Script).
 * Um único lugar com a URL do backend. O token fica em sessionStorage (some ao fechar o navegador) ou, só se a pessoa
 * marcar "Manter conectado", em localStorage (vale os dias definidos no servidor; Sair apaga). */
(function () {
  var URL_BACKEND = 'https://script.google.com/macros/s/AKfycbxRBVgyZWN74VcswYUfMTfEXQEdz91Y0WFXfrZqFXeprtpjSugzVJ0dMbrNrd_JCTgjiw/exec';   // URL do aplicativo da Web (termina em /exec)
  var K_TOK = 'ew_tok', K_INFO = 'ew_info', K_SVC = 'ew_svc';   // ew_svc = token de SERVIÇO das automações (só localStorage, colado uma vez em config-servico.html)

  function lerSS(k) { try { return sessionStorage.getItem(k); } catch (e) { return null; } }
  function gravarSS(k, v) { try { sessionStorage.setItem(k, v); } catch (e) {} }
  function apagarSS(k) { try { sessionStorage.removeItem(k); } catch (e) {} }
  function lerLS(k) { try { return localStorage.getItem(k); } catch (e) { return null; } }
  function gravarLS(k, v) { try { localStorage.setItem(k, v); } catch (e) {} }
  function apagarLS(k) { try { localStorage.removeItem(k); } catch (e) {} }
  function ler(k) { var v = lerSS(k); return v !== null ? v : lerLS(k); }

  var EWAuth = {
    url: URL_BACKEND,
    configurado: function () { return /^https:\/\/script\.google\.com\//.test(URL_BACKEND); },
    token: function () { return ler(K_TOK); },
    servico: function () { return lerLS(K_SVC); },
    info: function () {
      try { var i = JSON.parse(ler(K_INFO) || 'null'); if (i) return i; } catch (e) {}
      return (!ler(K_TOK) && lerLS(K_SVC)) ? { perfil: 'SERVICO', nome: 'Automação', funcao: '' } : null;
    },
    guardar: function (r, lembrar) {
      if (r && r.ok && r.token) {
        EWAuth.limpar();
        var g = lembrar === true && r.lembrado === true ? gravarLS : gravarSS;   // só vai para localStorage se o servidor confirmou
        g(K_TOK, r.token); g(K_INFO, JSON.stringify({ perfil: r.perfil, nome: r.nome || '', funcao: r.funcao || '' }));
      }
      return r;
    },
    limpar: function () { apagarSS(K_TOK); apagarSS(K_INFO); apagarLS(K_TOK); apagarLS(K_INFO); },
    /* chamada crua (sem token). text/plain evita o "preflight" que o Apps Script não aceita */
    raw: function (corpo) {
      if (!EWAuth.configurado()) return Promise.resolve({ ok: false, motivo: 'NAO_CONFIGURADO' });
      return fetch(URL_BACKEND, { method: 'POST', headers: { 'Content-Type': 'text/plain;charset=utf-8' }, body: JSON.stringify(corpo), redirect: 'follow' })
        .then(function (r) { return r.text(); })
        .then(function (t) { try { return JSON.parse(t); } catch (e) { return { ok: false, motivo: 'RESPOSTA_INVALIDA' }; } })
        .catch(function () { return { ok: false, motivo: 'SEM_REDE' }; });
    },
    /* chamada autenticada: junta o token e trata sessão vencida */
    post: function (corpo) {
      var c = {}; for (var k in corpo) c[k] = corpo[k];
      var t = EWAuth.token(), sv = EWAuth.servico();
      if (t) c.token = t; else if (sv) c.tokenServico = sv;     // pessoa logada vale mais; sem login, o token de serviço (automação)
      return EWAuth.raw(c).then(function (r) {
        if (r && r.motivo === 'SESSAO') { if (t) EWAuth.limpar(); EWAuth.aoPerderSessao(); }
        return r;
      });
    },
    aoPerderSessao: function () {
      try { if (window.top !== window) { window.top.postMessage({ ew: 'sessao-perdida' }, '*'); return; } } catch (e) {}
      if (!/index\.html$|\/$/.test(location.pathname)) location.href = 'index.html';
      else location.reload();
    },
    login: function (m, s, lembrar) { return EWAuth.raw({ action: 'login', matricula: m, senha: s, lembrar: lembrar === true }).then(function (r) { return EWAuth.guardar(r, lembrar === true); }); },
    ativar: function (d) { d.action = 'ativar'; return EWAuth.raw(d).then(EWAuth.guardar); },
    entrarConvite: function (cod) { return EWAuth.raw({ action: 'loginConvite', codigo: cod }).then(EWAuth.guardar); },
    pedirRecuperacao: function (m) { return EWAuth.raw({ action: 'recuperarPedir', matricula: m }); },
    confirmarRecuperacao: function (d) { d.action = 'recuperarConfirmar'; return EWAuth.raw(d); },
    validar: function () {
      if (!EWAuth.token() && !EWAuth.servico()) return Promise.resolve(null);
      return EWAuth.post({ action: 'sessao' }).then(function (r) { return r && r.ok ? r : null; });
    },
    sair: function () {
      var t = EWAuth.token(); EWAuth.limpar();
      return t ? EWAuth.raw({ action: 'sair', token: t }) : Promise.resolve({ ok: true });
    }
  };
  window.EWAuth = EWAuth;
})();
