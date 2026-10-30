# -*- coding: utf-8 -*-
"""
sync_envios.py -- PILOTO: atualiza SO o dashboard de Envios Logisticos a partir da planilha no Dropbox,
rodando no GitHub Actions (sem PC e sem tarefas agendadas).

Fluxo:
  1. troca o refresh token do Dropbox por um access token (leitura);
  2. baixa os scripts *.py de _scripts (gerar_dashboards.py e dependencias) e a planilha
     Controle_Logistico_Requisicoes.xlsx;
  3. gera o HTML novo com as MESMAS funcoes do gerar_dashboards.py (build_envios_data / render_envios),
     partindo do HTML que ja esta publicado neste repositorio;
  4. trava de seguranca: se a diferenca nao for so de dado (numeros/linhas de tabela), NAO publica;
  5. se mudou e nao e teste: grava www/dashboard-envios-logisticos.html e avisa o workflow (changed=true).
O workflow faz o commit, o push e dispara o deploy.

Variaveis de ambiente (segredos do GitHub):
  DROPBOX_APP_KEY, DROPBOX_APP_SECRET, DROPBOX_REFRESH_TOKEN
  DRY_RUN = "true"  -> gera e confere, mas NAO grava nada no repositorio.

O log deste repositorio e PUBLICO: este script imprime so contagens e mensagens genericas
(nunca nomes, textos de linha ou valores da planilha) e nunca imprime credenciais.
"""
import base64
import contextlib
import difflib
import importlib
import io
import json
import os
import re
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request

NS_SCRIPTS = "2024164339"
DIR_SCRIPTS = "17 - SITE E APP (DASHBOARDS)/_scripts"
NS_XLSX = "12772033633"
PATH_XLSX = "01 - ALMOXARIFADO/02 - ENTREGA MATERIAIS/Controle_Logistico_Requisicoes.xlsx"
REL = "www/dashboard-envios-logisticos.html"


def log(msg):
    print(msg, flush=True)


# ---------------------------------------------------------------- Dropbox
def _post(url, headers, data=None, timeout=60):
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read()
    except urllib.error.HTTPError as e:
        corpo = ""
        try:
            corpo = e.read().decode("utf-8", "replace")[:200]
        except Exception:
            pass
        raise RuntimeError("Dropbox respondeu HTTP %s em %s: %s" % (e.code, url.split("/2/")[-1], corpo))


def obter_access_token():
    chave = os.environ.get("DROPBOX_APP_KEY", "")
    segredo = os.environ.get("DROPBOX_APP_SECRET", "")
    refresh = os.environ.get("DROPBOX_REFRESH_TOKEN", "")
    if not (chave and segredo and refresh):
        raise RuntimeError("Faltam segredos: DROPBOX_APP_KEY, DROPBOX_APP_SECRET e/ou DROPBOX_REFRESH_TOKEN.")
    basico = base64.b64encode(("%s:%s" % (chave, segredo)).encode()).decode()
    corpo = urllib.parse.urlencode({"grant_type": "refresh_token", "refresh_token": refresh}).encode()
    resp = _post("https://api.dropbox.com/oauth2/token",
                 {"Authorization": "Basic " + basico, "Content-Type": "application/x-www-form-urlencoded"}, corpo)
    tok = json.loads(resp.decode()).get("access_token")
    if not tok:
        raise RuntimeError("Dropbox nao devolveu access_token.")
    return tok


def dbx_listar(token, ns, caminho):
    """Lista (sem recursao) os arquivos de uma pasta. Retorna lista de nomes de arquivo."""
    nomes = []
    url = "https://api.dropboxapi.com/2/files/list_folder"
    corpo = {"path": "ns:%s/%s" % (ns, caminho), "recursive": False, "limit": 500}
    hdr = {"Authorization": "Bearer " + token, "Content-Type": "application/json"}
    while True:
        r = json.loads(_post(url, hdr, json.dumps(corpo).encode()).decode())
        nomes += [e["name"] for e in r.get("entries", []) if e.get(".tag") == "file"]
        if not r.get("has_more"):
            return nomes
        url = "https://api.dropboxapi.com/2/files/list_folder/continue"
        corpo = {"cursor": r["cursor"]}


def dbx_baixar(token, ns, caminho, destino):
    arg = json.dumps({"path": "ns:%s/%s" % (ns, caminho)}, ensure_ascii=True)  # cabecalho precisa ser ASCII
    dados = _post("https://content.dropboxapi.com/2/files/download",
                  {"Authorization": "Bearer " + token, "Dropbox-API-Arg": arg}, None, timeout=120)
    with open(destino, "wb") as f:
        f.write(dados)
    return len(dados)


# ---------------------------------------------------------------- trava de seguranca
def sem_digitos(t):
    return re.sub(r"[0-9]+([.,][0-9]+)?", "", t)


def diferenca_estrutural(antigo, novo):
    """Linhas que diferem mesmo depois de tirar todos os digitos, fora de linhas de dado."""
    a = sem_digitos(antigo).splitlines()
    b = sem_digitos(novo).splitlines()
    difs = [l for l in difflib.unified_diff(a, b, lineterm="", n=0)
            if l[:1] in "+-" and l[:3] not in ("+++", "---")]

    def e_dado(l):
        t = l[1:].strip()
        # 30/10/2026: o grafico de evolucao ganha um mes (e uma posicao nas listas) a cada virada de mes: e dado, nao estrutura.
        return (not t) or t.startswith("<tr") or "itensEnvioData" in t or "Atualizado" in t \
            or t.startswith("[{") or t.startswith("const DATA") \
            or re.match(r"var evolucao(Meses|Req|Ent) = \[", t) is not None

    return [l for l in difs if not e_dado(l)]


# ---------------------------------------------------------------- geracao
def gerar(base_html, xlsx_local, pasta_scripts):
    """Roda o gerador existente. Toda a saida dele e capturada (nada de dado vai para o log publico)."""
    sys.path.insert(0, pasta_scripts)
    antes = os.getcwd()
    os.chdir(pasta_scripts)
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
            G = importlib.import_module("gerar_dashboards")
            G.ENVIOS_XLSX = xlsx_local
            d = G.build_envios_data()
            novo = G.render_envios(base_html, d)
    finally:
        os.chdir(antes)
    try:
        aberto = d["aberto_total"] if d.get("aberto_total") is not None else sum(q for (_, q) in d["aberto_rows"])
        log("Envios: total=%s entregues=%s canceladas=%s em_aberto=%s acoes_almox=%s acoes_log=%s" % (
            d["kpi_total"], d["kpi_entregues"], d["kpi_cancel"], aberto,
            len(d["acoes_almox"]), len(d["acoes_log"])))
    except Exception:
        log("Envios: gerado (resumo de contagens indisponivel).")
    return novo


def avisar_workflow(changed):
    saida = os.environ.get("GITHUB_OUTPUT")
    if saida:
        with open(saida, "a", encoding="utf-8") as f:
            f.write("changed=%s\n" % ("true" if changed else "false"))


def main():
    dry = os.environ.get("DRY_RUN", "false").strip().lower() == "true"
    log("Modo: %s" % ("TESTE (nao grava nada)" if dry else "PUBLICAR"))
    avisar_workflow(False)
    pub = os.path.join(os.getcwd(), REL)
    try:
        base = open(pub, encoding="utf-8").read()
    except FileNotFoundError:
        log("[ERRO] %s nao encontrado: o workflow precisa fazer o checkout do repositorio." % REL)
        return 1

    trabalho = tempfile.mkdtemp(prefix="envios_")
    pasta_scripts = os.path.join(trabalho, "_scripts")
    os.makedirs(pasta_scripts)
    try:
        token = obter_access_token()
        log("Dropbox: acesso obtido.")
        pys = [n for n in dbx_listar(token, NS_SCRIPTS, DIR_SCRIPTS)
               if n.lower().endswith(".py") and ".bak" not in n.lower()]
        if "gerar_dashboards.py" not in pys:
            log("[ERRO] gerar_dashboards.py nao esta em _scripts (achei %d arquivo(s) .py)." % len(pys))
            return 1
        for n in pys:
            dbx_baixar(token, NS_SCRIPTS, DIR_SCRIPTS + "/" + n, os.path.join(pasta_scripts, n))
        log("Scripts baixados: %d arquivo(s) .py." % len(pys))
        xlsx = os.path.join(trabalho, "Controle_Logistico_Requisicoes.xlsx")
        tam = dbx_baixar(token, NS_XLSX, PATH_XLSX, xlsx)
        with open(xlsx, "rb") as f:
            cab = f.read(2)
        if tam < 10000 or cab != b"PK":
            log("[ERRO] a planilha baixada nao parece um .xlsx valido (%d bytes)." % tam)
            return 1
        log("Planilha baixada: %d KB." % (tam // 1024))
    except Exception as e:
        log("[ERRO] %s" % str(e)[:300])
        return 1

    try:
        novo = gerar(base, xlsx, pasta_scripts)
    except SystemExit as e:
        log("[ERRO] o gerador encerrou o programa (codigo %s). Provavel caminho de pasta do ambiente das tarefas." % e.code)
        return 1
    except Exception as e:  # noqa: BLE001
        tb = e.__traceback__
        while tb and tb.tb_next:
            tb = tb.tb_next
        onde = "%s:%s" % (os.path.basename(tb.tb_frame.f_code.co_filename), tb.tb_lineno) if tb else "?"
        log("[ERRO] falha ao gerar (%s em %s): %s" % (type(e).__name__, onde, str(e)[:160]))
        return 1

    if novo == base:
        log("Sem mudanca no dashboard (nada a publicar).")
        return 0
    est = diferenca_estrutural(base, novo)
    if est:
        log("[TRAVA] %d linha(s) com diferenca ESTRUTURAL em relacao ao publicado -- NAO publicado." % len(est))
        return 1
    log("Mudanca so de dados confirmada (trava OK).")
    if dry:
        log("[TESTE] haveria publicacao; nada foi gravado.")
        return 0
    with open(pub, "w", encoding="utf-8", newline="") as f:
        f.write(novo)
    avisar_workflow(True)
    log("HTML novo gravado no workspace; o workflow fara commit, push e deploy.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
