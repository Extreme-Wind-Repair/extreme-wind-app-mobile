# -*- coding: utf-8 -*-
"""
sync_bdh.py -- FASE 2. Mantem a lista BDH_VAGAS_MESTRE da Reuniao Diaria igual ao que a planilha
"VAGAS MESTRE" diz (aba BANCO DE DADOS, coluna "RESUMO GESTAO A VISTA" = "BDH"), rodando no GitHub Actions
(sem PC e sem tarefa agendada).

Fluxo:
  1. baixa a planilha VIVA: 2 - RH & DP/8 - VAGAS/VAGAS MESTRE.xlsx (fallback: arquivo do mes);
  2. acha as colunas PELO TITULO (as posicoes mudam a cada versao da planilha);
  3. monta o bloco  const BDH_VAGAS_MESTRE = { ... };  no formato que a pagina ja usa;
  4. troca SOMENTE esse bloco (e a data "Ultima atualizacao" do comentario) em
     www/dashboard-reuniao-diaria.html;
  5. trava: se qualquer outra parte da pagina mudar, NAO grava;
  6. se mudou e nao e teste: grava o arquivo e avisa o workflow (changed=true) para commit, push e deploy.

Variaveis: DROPBOX_APP_KEY, DROPBOX_APP_SECRET, DROPBOX_REFRESH_TOKEN (segredos) e DRY_RUN ("true" = so testa).

O log deste repositorio e PUBLICO: o script imprime so titulos de colunas e contagens, NUNCA nomes,
matriculas ou valores de celulas de pessoas. Nunca imprime credenciais.
"""
import base64
import datetime
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
REL = "www/dashboard-reuniao-diaria.html"

CERT_ALIAS = {
    "BST": "BST", "BTT": "BTT", "BRT": "BRT", "ART": "ART", "ARTE": "ART", "BTT-E": "BTT-E",
    "LIFT USER": "LIFT USER", "USUARIO DE ELEVADOR": "LIFT USER",
    "LOTO GE TEORICO": "LOTO GE Teorico", "LOTO AUTORIZADO GE": "LOTO Autorizado GE",
}
RX_PARQUE = re.compile(r"^(GE|SIE|NX)\s*-\s*(.+)$")
RX_BLOCO = re.compile(r"(  const BDH_VAGAS_MESTRE = \{)(.*?)(\n  \};)", re.S)
RX_DATA = re.compile(r"(\u00daltima atualiza\u00e7\u00e3o: )\d{2}/\d{2}/\d{4}(\.\s*\*/\s*\n\s*const BDH_VAGAS_MESTRE)")
PEQUENAS = {"DO", "DA", "DE", "DOS", "DAS", "E"}


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
    return re.sub(r"\s+", " ", re.sub(r"[()]", " ", norm(s))).strip()


def escolher_arquivo(nomes):
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


def celula_preenchida(v):
    return v is not None and str(v).strip() not in ("", "0", "-", "0.0")


def matricula(v):
    if v is None:
        return ""
    s = str(v).strip()
    try:
        return str(int(float(s.replace(",", "."))))
    except Exception:
        return s


def js_str(s):
    return "'" + str(s).replace("\\", "\\\\").replace("'", "\\'") + "'"


def fmt_parque(titulo):
    """'SIE - SAO VITOR - BA' -> ('Sao Vitor - BA', 'SIE'). Mantem acentos do titulo; sufixo de UF em maiusculas."""
    m = RX_PARQUE.match(re.sub(r"\s+", " ", titulo.strip().upper()))
    cliente, resto = m.group(1), m.group(2).strip()
    partes = [p.strip() for p in resto.split(" - ")]
    saida = []
    for k, p in enumerate(partes):
        if k > 0 and len(p) == 2 and p.isalpha():
            saida.append(p.upper())
            continue
        pal = []
        for j, w in enumerate(p.split()):
            pal.append(w.lower() if (j > 0 and w in PEQUENAS) else w.capitalize())
        saida.append(" ".join(pal))
    return " - ".join(saida), cliente


# ---------------------------------------------------------------- leitura da planilha
def ler_bdh(caminho_xlsx):
    """Retorna (lista_de_pessoas, resumo_para_log). Pessoa = dict(mat, nome, certs, parques)."""
    import openpyxl
    wb = openpyxl.load_workbook(caminho_xlsx, read_only=True, data_only=True)
    alvo = next((ws for ws in wb.worksheets if norm(ws.title) == norm(ABA)), None)
    if alvo is None:
        raise RuntimeError("aba '%s' nao encontrada." % ABA)
    linha_cab, cab = achar_cabecalho(alvo)
    if not linha_cab:
        raise RuntimeError("nao achei a coluna '%s' nas 15 primeiras linhas." % COL_STATUS)
    ncab = [norm(t) for t in cab]
    i_status = ncab.index(COL_STATUS)
    i_mat = next((i for i, t in enumerate(ncab) if t in ("MAT.", "MAT") or "MATRIC" in t), None)
    i_nome = next((i for i, t in enumerate(ncab) if t.startswith("NOME")), None)
    if i_mat is None or i_nome is None:
        raise RuntimeError("nao achei as colunas de matricula e/ou nome.")
    certs = []   # (indice, nome canonico) na ordem das colunas
    for i, t in enumerate(cab):
        canon = CERT_ALIAS.get(norm_titulo(t))
        if canon and canon not in [c for _, c in certs]:
            certs.append((i, canon))
    parques = []  # (indice, parque, cliente)
    for i, t in enumerate(cab):
        if RX_PARQUE.match(re.sub(r"\s+", " ", t.strip().upper())):
            p, c = fmt_parque(t)
            parques.append((i, p, c))
    pessoas, sem_mat = [], 0
    for linha in alvo.iter_rows(min_row=linha_cab + 1, values_only=True):
        if not linha or i_status >= len(linha) or norm(linha[i_status]) != "BDH":
            continue
        mat = matricula(linha[i_mat]) if i_mat < len(linha) else ""
        nome = re.sub(r"\s+", " ", str(linha[i_nome] or "")).strip().upper() if i_nome < len(linha) else ""
        if not mat or not nome:
            sem_mat += 1
            continue
        pessoas.append({
            "mat": mat, "nome": nome,
            "certs": [c for i, c in certs if i < len(linha) and valor_um(linha[i])],
            "parques": [(p, c) for i, p, c in parques if i < len(linha) and celula_preenchida(linha[i])],
        })
    resumo = "colunas: %d certificacao(oes), %d parque(s); BDH na planilha: %d; sem matricula ou nome: %d" % (
        len(certs), len(parques), len(pessoas) + sem_mat, sem_mat)
    return pessoas, resumo


# ---------------------------------------------------------------- montagem e troca do bloco
def montar_corpo(pessoas):
    """Texto entre '{' e '\\n  };', no mesmo estilo da pagina."""
    if not pessoas:
        return ""
    vistos, linhas = set(), []
    for p in sorted(pessoas, key=lambda x: (len(x["mat"]), x["mat"])):
        if p["mat"] in vistos:
            continue
        vistos.add(p["mat"])
        certs = "[" + ", ".join(js_str(c) for c in p["certs"]) + "]"
        parq = "[" + ", ".join("{ parque: %s, cliente: %s }" % (js_str(a), js_str(b)) for a, b in p["parques"]) + "]"
        linhas.append("    %s: { nome: %s,\n             certificacoes: %s,\n             parques: %s }" % (
            js_str(p["mat"]), js_str(p["nome"]), certs, parq))
    return "\n" + ",\n".join(linhas)


def trocar_bloco(html, pessoas, hoje):
    """Retorna (html_novo, mudou). Troca so o bloco e a data do comentario (quando o bloco muda)."""
    m = RX_BLOCO.search(html)
    if not m:
        raise RuntimeError("bloco 'const BDH_VAGAS_MESTRE = {...};' nao encontrado na pagina.")
    if len(RX_BLOCO.findall(html)) != 1:
        raise RuntimeError("mais de um bloco BDH_VAGAS_MESTRE na pagina.")
    novo_corpo = montar_corpo(pessoas)
    if re.sub(r"\s+", "", m.group(2)) == re.sub(r"\s+", "", novo_corpo):
        return html, False
    novo = html[:m.start(2)] + novo_corpo + html[m.end(2):]
    novo = RX_DATA.sub(lambda mm: mm.group(1) + hoje + mm.group(2), novo, count=1)
    return novo, True


def so_o_bloco_mudou(antigo, novo):
    def sem(t):
        t = RX_BLOCO.sub(lambda m: m.group(1) + "@@" + m.group(3), t, count=1)
        return RX_DATA.sub(lambda mm: mm.group(1) + "@@" + mm.group(2), t, count=1)
    return sem(antigo) == sem(novo)


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
        html = open(pub, encoding="utf-8").read()
    except FileNotFoundError:
        log("[ERRO] %s nao encontrado: o workflow precisa fazer o checkout do repositorio." % REL)
        return 1
    try:
        token = obter_access_token()
        log("Dropbox: acesso obtido.")
        raiz = dbx_listar(token, NS, PASTA_BASE)
        if ARQ_VIVO in raiz:
            origem, escolhido = PASTA_BASE, ARQ_VIVO
            log("Usando a planilha VIVA: %s/%s" % (PASTA_BASE, ARQ_VIVO))
        else:
            escolhido, todos = escolher_arquivo(dbx_listar(token, NS, PASTA))
            origem = PASTA
            if not escolhido:
                log("[ERRO] nenhum arquivo VAGAS MESTRE encontrado.")
                return 1
            log("Planilha viva nao encontrada; usando o arquivo do mes: %s" % escolhido)
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
        pessoas, resumo = ler_bdh(destino)
        log("Leitura: " + resumo)
    except Exception as e:  # noqa: BLE001
        log("[ERRO] ao ler a planilha (%s): %s" % (type(e).__name__, str(e)[:160]))
        return 1
    log("BDH a publicar: %d pessoa(s); certificacoes (total): %d; parques aprovados (total): %d." % (
        len(pessoas), sum(len(p["certs"]) for p in pessoas), sum(len(p["parques"]) for p in pessoas)))
    try:
        hoje = datetime.datetime.now().strftime("%d/%m/%Y")
        novo, mudou = trocar_bloco(html, pessoas, hoje)
    except Exception as e:  # noqa: BLE001
        log("[ERRO] %s" % str(e)[:200])
        return 1
    if not mudou:
        log("Sem mudanca: a lista BDH da pagina ja esta igual a planilha.")
        return 0
    if not so_o_bloco_mudou(html, novo):
        log("[TRAVA] a troca alteraria mais do que o bloco BDH -- NAO publicado.")
        return 1
    log("Mudanca confirmada: so o bloco BDH_VAGAS_MESTRE (e a data do comentario) mudam.")
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
