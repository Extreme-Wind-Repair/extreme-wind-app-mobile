# -*- coding: utf-8 -*-
"""
sync_bdh.py -- PILOTO (fase 1: DESCOBERTA). Roda no GitHub Actions.

Objetivo final: manter a lista BDH_VAGAS_MESTRE da Reuniao Diaria sempre igual ao que a planilha
"VAGAS MESTRE" (aba BANCO DE DADOS, coluna "RESUMO GESTAO A VISTA" = "BDH") diz, sem depender de
tarefa agendada nem do PC.

Esta fase NAO altera nada no repositorio. Ela so:
  1. acha o arquivo VAGAS MESTRE do mes (maior numero no prefixo, em 2 - RH & DP/8 - VAGAS/2026);
  2. imprime os TITULOS das colunas e CONTAGENS agregadas (quantos BDH, quantos tem cada certificacao,
     quantos tem cada parque aprovado) para eu mapear as colunas certas.

O log deste repositorio e PUBLICO: este script NUNCA imprime nomes, matriculas ou valores de celulas
de pessoas -- so titulos de colunas e numeros. Nunca imprime credenciais.

Segredos: DROPBOX_APP_KEY, DROPBOX_APP_SECRET, DROPBOX_REFRESH_TOKEN (os mesmos do piloto de Envios).
"""
import base64
import json
import os
import re
import sys
import tempfile
import unicodedata
import urllib.error
import urllib.parse
import urllib.request

NS = "2024164339"
PASTA_BASE = "2 - RH & DP/8 - VAGAS"
ARQ_VIVO = "VAGAS MESTRE.xlsx"
PASTA = PASTA_BASE + "/2026"   # arquivos mensais (fallback)
ABA = "BANCO DE DADOS"
COL_STATUS = "RESUMO GESTAO A VISTA"
CERT_ALIAS = {
    "BST": "BST", "BTT": "BTT", "BRT": "BRT", "ART": "ART", "ARTE": "ART", "BTT-E": "BTT-E",
    "LIFT USER": "LIFT USER", "USUARIO DE ELEVADOR": "LIFT USER",
    "LOTO GE TEORICO": "LOTO GE Teorico", "LOTO AUTORIZADO GE": "LOTO Autorizado GE",
}
RX_PARQUE = re.compile(r"^(GE|SIE|NX)\s*-\s*(.+)$")


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
    arg = json.dumps({"path": "ns:%s/%s" % (ns, caminho)}, ensure_ascii=True)
    dados = _post("https://content.dropboxapi.com/2/files/download",
                  {"Authorization": "Bearer " + token, "Dropbox-API-Arg": arg}, None, timeout=180)
    with open(destino, "wb") as f:
        f.write(dados)
    return len(dados)


# ---------------------------------------------------------------- utilidades
def norm(s):
    s = "" if s is None else str(s)
    s = unicodedata.normalize("NFD", s)
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", s).strip().upper()


def norm_titulo(s):
    """Como norm(), mas tira parenteses/pontuacao solta (ex.: 'LOTO GE (TEORICO)' -> 'LOTO GE TEORICO')."""
    return re.sub(r"\s+", " ", re.sub(r"[()]", " ", norm(s))).strip()


def escolher_arquivo(nomes):
    """Arquivos '<NN> - VAGAS MESTRE <MES>.xlsx': escolhe o de maior NN."""
    cand = []
    for n in nomes:
        m = re.match(r"^(\d{1,2})\s*-\s*VAGAS MESTRE.*\.xlsx$", n, re.I)
        if m and not n.startswith("~$"):
            cand.append((int(m.group(1)), n))
    return (sorted(cand)[-1][1] if cand else None), sorted(n for _, n in cand)


def achar_cabecalho(ws, max_linhas=15):
    for i, linha in enumerate(ws.iter_rows(min_row=1, max_row=max_linhas, values_only=True), start=1):
        if any(norm(c) == COL_STATUS for c in linha):
            return i, [("" if c is None else str(c)) for c in linha]
    return None, None


def valor_um(v):
    try:
        return float(str(v).replace(",", ".").strip()) == 1.0
    except Exception:
        return False


def descobrir(caminho_xlsx):
    import openpyxl
    wb = openpyxl.load_workbook(caminho_xlsx, read_only=True, data_only=True)
    log("Abas: " + " | ".join("%s (%sx%s)" % (ws.title, ws.max_row, ws.max_column) for ws in wb.worksheets))
    alvo = next((ws for ws in wb.worksheets if norm(ws.title) == norm(ABA)), None)
    if alvo is None:
        log("[ERRO] aba '%s' nao encontrada." % ABA)
        return 1
    linha_cab, cab = achar_cabecalho(alvo)
    if not linha_cab:
        log("[ERRO] nao achei a coluna '%s' nas 15 primeiras linhas da aba." % COL_STATUS)
        return 1
    log("Aba '%s': cabecalho na linha %d; %d colunas." % (alvo.title, linha_cab, len(cab)))
    log("Colunas (numero: titulo): " + " | ".join("%d: %s" % (i + 1, t.strip()[:40]) for i, t in enumerate(cab) if t.strip()))
    ncab = [norm(t) for t in cab]
    i_status = ncab.index(COL_STATUS)
    log("Coluna '%s' = coluna %d." % (COL_STATUS, i_status + 1))
    cand_mat = [i + 1 for i, t in enumerate(ncab) if t in ("MAT.", "MAT") or "MATRIC" in t or t in ("CHAPA", "ID")]
    cand_nome = [i + 1 for i, t in enumerate(ncab) if t.startswith("NOME") or "COLABORADOR" in t or t == "FUNCIONARIO"]
    log("Colunas candidatas a MATRICULA: %s | a NOME: %s" % (cand_mat or "nenhuma", cand_nome or "nenhuma"))
    cols_cert = {}   # nome canonico -> lista de (indice, titulo)
    for i, t in enumerate(cab):
        canon = CERT_ALIAS.get(norm_titulo(t))
        if canon:
            cols_cert.setdefault(canon, []).append(i)
    log("Certificacoes encontradas (%d de %d): %s" % (
        len(cols_cert), len(set(CERT_ALIAS.values())),
        " | ".join("%s <- coluna(s) %s" % (k, ",".join(str(i + 1) for i in v)) for k, v in sorted(cols_cert.items()))))
    cols_parque = {}
    for i, t in enumerate(cab):
        m = RX_PARQUE.match(re.sub(r"\s+", " ", t.strip().upper()))
        if m:
            cols_parque[re.sub(r"\s+", " ", t.strip())] = i
    log("Colunas de parque (%d): %s" % (len(cols_parque), " | ".join("%d: %s" % (i + 1, k) for k, i in sorted(cols_parque.items(), key=lambda kv: kv[1]))))

    contagem_status, bdh_linhas = {}, []
    total = 0
    for linha in alvo.iter_rows(min_row=linha_cab + 1, values_only=True):
        if not linha or all(c is None for c in linha):
            continue
        total += 1
        st = norm(linha[i_status]) if i_status < len(linha) else ""
        contagem_status[st or "(vazio)"] = contagem_status.get(st or "(vazio)", 0) + 1
        if st == "BDH":
            bdh_linhas.append(linha)
    top = sorted(contagem_status.items(), key=lambda kv: -kv[1])[:12]
    log("Linhas de dados: %d. Valores de '%s': %s" % (total, COL_STATUS, ", ".join("%s=%d" % kv for kv in top)))
    log("BDH: %d pessoa(s)." % len(bdh_linhas))
    if bdh_linhas:
        c = {}
        for nome, idxs in cols_cert.items():
            for i in idxs:
                c["%s(col %d)" % (nome, i + 1)] = sum(1 for l in bdh_linhas if i < len(l) and valor_um(l[i]))
        log("Certificacoes entre os BDH (contagem): " + ", ".join("%s=%d" % kv for kv in sorted(c.items())))
        p = {n: sum(1 for l in bdh_linhas if i < len(l) and l[i] not in (None, "", 0, "0")) for n, i in cols_parque.items()}
        p = {k: v for k, v in p.items() if v}
        log("Parques aprovados entre os BDH (contagem): " + (", ".join("%s=%d" % kv for kv in sorted(p.items())) or "nenhum"))
    return 0


def main():
    try:
        token = obter_access_token()
        log("Dropbox: acesso obtido.")
        raiz = dbx_listar(token, NS, PASTA_BASE)
        if ARQ_VIVO in raiz:
            origem, escolhido = PASTA_BASE, ARQ_VIVO
            log("Usando a planilha VIVA: %s/%s" % (PASTA_BASE, ARQ_VIVO))
        else:
            nomes = dbx_listar(token, NS, PASTA)
            escolhido, todos = escolher_arquivo(nomes)
            origem = PASTA
            log("Planilha viva nao encontrada. Arquivos do mes em %s: %s" % (PASTA, "; ".join(todos) or "nenhum"))
            if not escolhido:
                log("[ERRO] nenhum arquivo VAGAS MESTRE encontrado.")
                return 1
            log("Usando o arquivo do mes (maior numero no prefixo): %s" % escolhido)
        destino = os.path.join(tempfile.mkdtemp(prefix="bdh_"), "vagas.xlsx")
        tam = dbx_baixar(token, NS, origem + "/" + escolhido, destino)
        with open(destino, "rb") as f:
            cab = f.read(2)
        if tam < 10000 or cab != b"PK":
            log("[ERRO] o arquivo baixado nao parece um .xlsx valido (%d bytes)." % tam)
            return 1
        log("Planilha baixada: %d KB." % (tam // 1024))
    except Exception as e:
        log("[ERRO] %s" % str(e)[:300])
        return 1
    try:
        return descobrir(destino)
    except Exception as e:  # noqa: BLE001
        log("[ERRO] ao ler a planilha (%s): %s" % (type(e).__name__, str(e)[:160]))
        return 1


if __name__ == "__main__":
    sys.exit(main())
