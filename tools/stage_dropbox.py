# -*- coding: utf-8 -*-
"""
stage_dropbox.py -- prepara e fecha a geracao dos dashboards no GitHub Actions.

  python tools/stage_dropbox.py baixar <WS>   baixa do Dropbox (API) os arquivos de entrada e o proprio
                                              gerar_dashboards.py para uma arvore identica a do PC, e copia
                                              www/ para <WS>/<SITE>/ (modelos HTML atuais).
  python tools/stage_dropbox.py voltar <WS>   compara as saidas geradas com www/ e copia so as que mudaram.
                                              Escreve changed.txt e a saida changed=true/false do workflow.

Segredos (env): DROPBOX_APP_KEY, DROPBOX_APP_SECRET, DROPBOX_REFRESH_TOKEN. Nunca imprime credenciais.
"""
import base64
import json
import os
import shutil
import sys
import urllib.error
import urllib.parse
import urllib.request

SITE = "17 - SITE E APP (DASHBOARDS)"
FROTA = "Controle de Frota - TESTE DE FORMULAÇÃO (BACK UP) - ATUAL.xlsb.xlsx"
BOL = "13 - LOGISTICA/CONTROLE DE VEÍCULOS/Zz-PRINCIPAIS/BOLETOS LOCADORAS/01. CONTROLE DE CONTAS A PAGAR UNIDAS.xlsx"
ENV_DIR = "3 - SUPRIMENTOS/01 - ALMOXARIFADO/02 - ENTREGA MATERIAIS/Controle_Logistico_Requisicoes.xlsx"
DIARIO = "CONTROLE DAS EQUIPES GERAL/Diário de Bordo (Extreme Wind).xlsx"
PEND = "CONTROLE DAS EQUIPES GERAL/pendencias_mobilizacao.json"


def reemb(ano):
    return "REEMBOLSO SEMANAL/REEMBOLSOS %d/Formulário de Reembolso Master (%d).xlsx" % (ano, ano)


# (namespace, caminho no Dropbox, caminho local dentro de WS, obrigatorio)
ITENS = [
    ("2024164339", SITE + "/_scripts/gerar_dashboards.py", SITE + "/_scripts/gerar_dashboards.py", True),
    ("2024164339", SITE + "/_scripts/gerar_checklists_busca.py", SITE + "/_scripts/gerar_checklists_busca.py", True),
    ("2024164339", SITE + "/_scripts/validar_frota.py", SITE + "/_scripts/validar_frota.py", False),
    ("2024164339", SITE + "/Checklist (Sr. Fernando)/" + FROTA, SITE + "/Checklist (Sr. Fernando)/" + FROTA, True),
    ("2024164339", SITE + "/Checklist (Sr. Fernando)/painel_combustivel_2026.html",
     SITE + "/Checklist (Sr. Fernando)/painel_combustivel_2026.html", False),
    ("2024164339", BOL, BOL, True),
    ("2024164339", "2 - RH & DP/8 - VAGAS/VAGAS MESTRE.xlsx", "2 - RH & DP/8 - VAGAS/VAGAS MESTRE.xlsx", True),
    ("2024164339", "2 - RH & DP/8 - VAGAS/controle_efetivo_independente.html",
     "2 - RH & DP/8 - VAGAS/controle_efetivo_independente.html", False),
    ("5005317713", DIARIO, DIARIO, True),
    ("5005317713", PEND, PEND, False),
    ("5005317713", reemb(2026), reemb(2026), True),
    ("5005317713", reemb(2025), reemb(2025), False),
    ("12772033633", "01 - ALMOXARIFADO/02 - ENTREGA MATERIAIS/Controle_Logistico_Requisicoes.xlsx", ENV_DIR, True),
]

# arquivos do topo de www/ que o gerador NAO produz (nunca voltam para o repositorio)
EXCLUIR = {"dashboard-reuniao-diaria.html", "dashboard-equipes-vivo.html", "mob_resumo.json", "manifest.json", "dashboard-resumo-equipes.html"}


def log(msg):
    print(msg, flush=True)


def token():
    chave = os.environ.get("DROPBOX_APP_KEY", "")
    segredo = os.environ.get("DROPBOX_APP_SECRET", "")
    refresh = os.environ.get("DROPBOX_REFRESH_TOKEN", "")
    if not (chave and segredo and refresh):
        raise RuntimeError("faltam segredos do Dropbox")
    basico = base64.b64encode(("%s:%s" % (chave, segredo)).encode()).decode()
    corpo = urllib.parse.urlencode({"grant_type": "refresh_token", "refresh_token": refresh}).encode()
    req = urllib.request.Request("https://api.dropbox.com/oauth2/token", data=corpo, method="POST",
                                 headers={"Authorization": "Basic " + basico,
                                          "Content-Type": "application/x-www-form-urlencoded"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode())["access_token"]


def baixar_um(tok, ns, caminho):
    arg = json.dumps({"path": "ns:%s/%s" % (ns, caminho)}, ensure_ascii=True)
    req = urllib.request.Request("https://content.dropboxapi.com/2/files/download", data=None, method="POST",
                                 headers={"Authorization": "Bearer " + tok, "Dropbox-API-Arg": arg})
    with urllib.request.urlopen(req, timeout=240) as r:
        return r.read()


_CACHE_DIR = {}


def listar_pasta(tok, ns, pasta):
    """Arquivos de uma pasta do Dropbox: lista de (nome, server_modified ISO)."""
    chave = (ns, pasta)
    if chave in _CACHE_DIR:
        return _CACHE_DIR[chave]
    itens = []
    url = "https://api.dropboxapi.com/2/files/list_folder"
    corpo = {"path": "ns:%s/%s" % (ns, pasta), "recursive": False, "limit": 1000}
    while True:
        req = urllib.request.Request(url, data=json.dumps(corpo).encode(), method="POST",
                                     headers={"Authorization": "Bearer " + tok, "Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=60) as r:
            res = json.loads(r.read().decode())
        itens += [(e["name"], e.get("server_modified", "")) for e in res.get("entries", []) if e.get(".tag") == "file"]
        if not res.get("has_more"):
            break
        url = "https://api.dropboxapi.com/2/files/list_folder/continue"
        corpo = {"cursor": res["cursor"]}
    _CACHE_DIR[chave] = itens
    return itens


def escolher_remoto(tok, ns, remoto):
    """Regra (Robson, 19/11/2026): havendo copia em conflito do Dropbox, vale a de horario mais recente
    (original ou copia). Retorna (caminho_a_baixar, quantas_copias_em_conflito)."""
    pasta, _, nome = remoto.rpartition("/")
    base, ponto, ext = nome.rpartition(".")
    if not ponto:
        return remoto, 0
    try:
        itens = listar_pasta(tok, ns, pasta)
    except Exception:  # noqa: BLE001
        return remoto, 0
    cands = []
    copias = 0
    for n, mod in itens:
        if n == nome:
            cands.append((mod, n))
        elif n.startswith(base + " (") and n.endswith("." + ext) and ("conflito" in n.lower() or "conflicted" in n.lower()):
            cands.append((mod, n))
            copias += 1
    if not copias:
        return remoto, 0
    cands.sort()
    escolhido = cands[-1][1]
    return ((pasta + "/" + escolhido) if pasta else escolhido), copias


def cmd_baixar(ws):
    tok = token()
    site_ws = os.path.join(ws, SITE)
    if os.path.isdir(ws):
        shutil.rmtree(ws)
    os.makedirs(site_ws)
    # modelos HTML atuais (os que o site publica)
    for nome in os.listdir("www"):
        origem = os.path.join("www", nome)
        if os.path.isfile(origem):
            shutil.copyfile(origem, os.path.join(site_ws, nome))
    falhou = 0
    for ns, remoto, local, obrig in ITENS:
        destino = os.path.join(ws, local)
        os.makedirs(os.path.dirname(destino), exist_ok=True)
        rotulo = os.path.basename(local)
        remoto_usar, copias = escolher_remoto(tok, ns, remoto)
        if copias:
            log("[conflito] %s: %d copia(s) em conflito; usando %s" % (
                rotulo, copias, "a copia em conflito mais recente" if remoto_usar != remoto else "o original (mais recente)"))
        try:
            dados = baixar_um(tok, ns, remoto_usar)
        except urllib.error.HTTPError as e:
            msg = "HTTP %s" % e.code
            if obrig:
                log("[ERRO] %s: %s (namespace %s)" % (rotulo, msg, ns))
                falhou += 1
            else:
                log("[opcional ausente] %s: %s" % (rotulo, msg))
            continue
        except Exception as e:  # noqa: BLE001
            log("[ERRO] %s: %s" % (rotulo, type(e).__name__))
            falhou += 1
            continue
        if local.lower().endswith(".xlsx") and dados[:2] != b"PK":
            log("[ERRO] %s: nao parece um .xlsx valido" % rotulo)
            falhou += 1
            continue
        with open(destino, "wb") as f:
            f.write(dados)
        log("OK %s (%d KB)" % (rotulo, len(dados) // 1024))
    if falhou:
        log("[FALHA] %d arquivo(s) obrigatorio(s) nao baixado(s); nao vou gerar." % falhou)
        return 1
    return 0


def cmd_voltar(ws):
    site_ws = os.path.join(ws, SITE)
    mudou = []
    for nome in sorted(os.listdir(site_ws)):
        origem = os.path.join(site_ws, nome)
        if not os.path.isfile(origem) or nome in EXCLUIR:
            continue
        if not (nome == "index.html" or nome.startswith("dashboard-") or nome.endswith(".json")):
            continue
        if not (nome.endswith(".html") or nome.endswith(".json")):
            continue
        alvo = os.path.join("www", nome)
        novo = open(origem, "rb").read()
        velho = open(alvo, "rb").read() if os.path.isfile(alvo) else None
        if novo != velho:
            shutil.copyfile(origem, alvo)
            mudou.append(nome)
            log("MUDOU %s (%s)" % (nome, "novo" if velho is None else "%d -> %d bytes" % (len(velho), len(novo))))
    with open("changed.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(mudou))
    saida = os.environ.get("GITHUB_OUTPUT")
    if saida:
        with open(saida, "a", encoding="utf-8") as f:
            f.write("changed=%s\n" % ("true" if mudou else "false"))
    if not mudou:
        log("Nenhum dashboard mudou em relacao ao publicado.")
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 3 or sys.argv[1] not in ("baixar", "voltar"):
        log("uso: stage_dropbox.py baixar|voltar <WS>")
        sys.exit(2)
    sys.exit(cmd_baixar(sys.argv[2]) if sys.argv[1] == "baixar" else cmd_voltar(sys.argv[2]))
