#!/usr/bin/env python3
"""Aplica o login (Acesso EW) numa pasta www do site. Idempotente: pode rodar de novo depois que
a automação sobrescrever o index.html. NUNCA grava nada se uma âncora não for encontrada.

  python aplicar_login_site.py <pasta_www> --verificar     # só confere, não grava
  python aplicar_login_site.py <pasta_www>                 # aplica (faz cópia .bak_login antes)
  Opções: --sem-reuniao  (não toca na Reunião Diária)   --sem-backup  (não cria .bak_login; usado no deploy do GitHub,
          onde um .bak_login dentro de www seria PUBLICADO)
Arquivos tocados: index.html, dashboard-reuniao-diaria.html (se existir), sw.js (se existir), ew-auth.js (cria).
Não toca em nenhuma automação. A URL do backend fica SÓ em ew-auth.js (constante URL_BACKEND)."""
import os, re, sys, shutil

AQUI = os.path.dirname(os.path.abspath(__file__))
def tpl(n): return open(os.path.join(AQUI, 'tpl', n), encoding='utf8').read()
def ler(p):
    b = open(p, 'rb').read(); crlf = b'\r\n' in b
    return b.decode('utf8').replace('\r\n', '\n'), crlf
def gravar(p, t, crlf):
    open(p, 'wb').write((t.replace('\n', '\r\n') if crlf else t).encode('utf8'))

def patch_index(t):
    if 'ewLogin' in t:
        if 'ewL_lem' in t: return t, 'já aplicado'
        a1 = '<button class="go" id="ewL_go">'
        a2 = "return EWAuth.login($('ewL_mat').value.trim(), s); });"
        a3 = '  #ewLogin .go{'
        if t.count(a1) != 1 or t.count(a2) != 1 or t.count(a3) != 1: raise SystemExit('ABORTADO (nada gravado): âncoras do login já aplicado não encontradas (atualização "Manter conectado")')
        t = t.replace(a1, '<label class="lem"><input type="checkbox" id="ewL_lem"> Manter conectado neste aparelho</label>\n      ' + a1, 1)
        t = t.replace(a2, "return EWAuth.login($('ewL_mat').value.trim(), s, $('ewL_lem').checked); });", 1)
        t = t.replace(a3, '  #ewLogin label.lem{display:flex; align-items:center; gap:8px; margin:12px 0 0; font-size:13px; color:#b4c3d0; cursor:pointer;}\n  #ewLogin label.lem input{width:auto; margin:0; padding:0; accent-color:#0b5cad;}\n' + a3, 1)
        return t, 'login já aplicado: acrescentado "Manter conectado"'
    erros = []
    for a in ['</head>', '<body>', '<div class="app">', '<div class="badge" id="topBadge">', 'console.log("EW-APP-SCRIPT-BOOT-OK");']:
        if t.count(a) != 1: erros.append(f'âncora ausente/duplicada: {a!r} ({t.count(a)}x)')
    n_if = len(re.findall(r'<iframe id="view-[a-z\-]+" src=', t))
    if n_if < 5: erros.append(f'poucos iframes de painel encontrados ({n_if})')
    if erros: raise SystemExit('ABORTADO (nada gravado):\n  ' + '\n  '.join(erros))
    t = t.replace('</head>', '<script src="ew-auth.js"></script>\n' + tpl('login.css.html') + '</head>', 1)
    t = t.replace('<body>', '<body class="ew-locked">\n' + tpl('overlay.html'), 1)
    t = re.sub(r'(<iframe id="view-[a-z\-]+" )src=', r'\1data-src=', t)
    i = t.index('<div class="badge" id="topBadge">'); j = t.index('</div>', i) + 6
    t = t[:i] + '<div style="display:flex;align-items:center;">' + t[i:j] + '<button class="ew-sair" id="ewSair" type="button">Sair</button></div>' + t[j:]
    k = t.index('<script>\n  console.log("EW-APP-SCRIPT-BOOT-OK");')
    t = t[:k] + tpl('logic.html') + t[k:]
    return t, f'aplicado ({n_if} iframes ficam carregados só após o login)'

def patch_reuniao(t):
    if 'EWAuth' in t: return t, 'já aplicado'
    m = re.search(r"  const API_URL = '[^']*';[^\n]*\n", t)          # aceita comentário depois do ';' (versão atual da página)
    g = t.find('  async function apiGet(){'); s = t.find('  function setSyncStatus')
    k = t.find('<script>\n  /* ============ CONFIG')
    if not m or g < 0 or s < 0 or k < 0: raise SystemExit('ABORTADO (nada gravado): âncoras da Reunião Diária não encontradas')
    novo_api = '''  async function apiGet(){
    if (!API_URL){
      const r = await fetch(MOCK_JSON_PATH);
      return r.json();
    }
    const r = await EWAuth.post({ action:'lerTudo' });
    if (!r || !r.ok) throw new Error(r && r.motivo === 'NEGADO' ? 'Sem permissão para ver estes dados.' : ('Falha ao ler (' + (r && r.motivo) + ')'));
    return r;
  }
  async function apiPost(payload){
    if (!API_URL){
      console.log('[MODO TESTE — não salvo de verdade]', payload);
      return { ok:true, result:{ newRow: 100000 + (PARK_SEQ++) } };
    }
    const r = await EWAuth.post(payload);
    if (r && r.motivo === 'NEGADO') setSyncStatus('Seu perfil não tem permissão para editar. A alteração NÃO foi salva.', true);
    else if (r && !r.ok) setSyncStatus('Não foi possível salvar (' + r.motivo + ').', true);
    return r;
  }

'''
    t = t.replace(m.group(0), "  const API_URL = (window.EWAuth && EWAuth.url) || '';   // backend de login (ew-auth.js)\n", 1)
    g = t.index('  async function apiGet(){'); s = t.index('  function setSyncStatus')
    t = t[:g] + novo_api + t[s:]
    k = t.index('<script>\n  /* ============ CONFIG')
    t = t[:k] + '<script src="ew-auth.js"></script>\n' + t[k:]
    return t, 'aplicado'

def patch_sw(t):
    if 'ew-auth.js' in t: return t, 'já aplicado'
    m = re.search(r'const CACHE_NAME = "extreme-wind-v(\d+)";', t)
    a = 'const isHTML = req.mode === "navigate" || (req.headers.get("accept") || "").includes("text/html");'
    if not m or a not in t or '  "./manifest.json",' not in t: raise SystemExit('ABORTADO (nada gravado): âncoras do sw.js não encontradas')
    t = t.replace(m.group(0), f'const CACHE_NAME = "extreme-wind-v{int(m.group(1)) + 1}";', 1)
    t = t.replace('  "./manifest.json",', '  "./ew-auth.js",\n  "./manifest.json",', 1)
    t = t.replace(a, a[:-1] + ' || /\\.js(\\?|$)/.test(req.url);', 1)
    return t, 'aplicado (versão do cache incrementada)'

def main():
    if len(sys.argv) < 2: raise SystemExit(__doc__)
    www = sys.argv[1]; so_ver = '--verificar' in sys.argv
    sem_bak = '--sem-backup' in sys.argv
    plano = [('index.html', patch_index), ('dashboard-reuniao-diaria.html', patch_reuniao), ('sw.js', patch_sw)]
    if '--sem-reuniao' in sys.argv: plano = [x for x in plano if x[0] != 'dashboard-reuniao-diaria.html']
    saidas = []
    for nome, fn in plano:
        p = os.path.join(www, nome)
        if not os.path.isfile(p):
            print(f'- {nome}: não existe nesta pasta (pulado)'); continue
        t, crlf = ler(p); novo, st = fn(t)
        print(f'- {nome}: {st}'); saidas.append((p, novo, crlf, novo != t))
    if so_ver: print('\nSó verificação: nada foi gravado.'); return
    for p, novo, crlf, mudou in saidas:
        if mudou:
            if not sem_bak: shutil.copyfile(p, p + '.bak_login')
            gravar(p, novo, crlf)
    dst = os.path.join(www, 'ew-auth.js'); src = os.path.join(AQUI, 'tpl', 'ew-auth.js')
    if not os.path.exists(dst):
        shutil.copyfile(src, dst)
    else:                                                         # atualiza o código, PRESERVANDO a URL já colada
        velho, crlf = ler(dst); novo = open(src, encoding='utf8').read()
        mu = re.search(r"var URL_BACKEND = '([^']*)';", velho)
        if 'lerLS' not in velho and mu:
            novo = re.sub(r"var URL_BACKEND = '[^']*';", lambda _m: "var URL_BACKEND = '" + mu.group(1) + "';", novo, count=1)
            if not sem_bak: shutil.copyfile(dst, dst + '.bak_login')
            gravar(dst, novo, crlf); print('- ew-auth.js: atualizado (URL preservada)')
    print('\nPronto. Edite a constante URL_BACKEND em ew-auth.js com a URL do aplicativo da Web (/exec).')
main()
