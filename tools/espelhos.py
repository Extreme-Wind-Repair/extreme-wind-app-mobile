# -*- coding: utf-8 -*-
"""
espelhos.py -- espelha portais estaticos do Dropbox para www/ (roda no GitHub Actions, sem PC).

Portais cobertos hoje: Calibracao (www/calibracao/index.html + data.json).

Calibracao:
  - index.html vem do Dropbox como esta (contem os certificados embutidos), depois de checagens de sanidade.
  - data.json e reconstruido a cada ciclo com a data de HOJE (Brasilia): status e "dias para vencer" sao
    recalculados a partir das datas da planilha, entao nunca ficam parados no dia em que alguem gerou o arquivo.
    Fonte das linhas: planilha Controle_Calibracao_Extreme_Wind_2026_FINAL.xlsx (aba "Controle de Calibracao");
    se a planilha nao puder ser lida, usa o data.json do Dropbox.
  - So grava se algo mudou. Falha (exit 1) se a sanidade nao passar: nunca publica arquivo suspeito.

Variaveis: DROPBOX_APP_KEY, DROPBOX_APP_SECRET, DROPBOX_REFRESH_TOKEN, DRY_RUN (true = so mostra).
Nunca imprime credenciais.
"""
import calendar
import datetime
import io
import json
import os
import re
import sys
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from stage_dropbox import baixar_um, token  # noqa: E402  (reaproveita a autenticacao do Dropbox)

NS = "12772033633"  # 3 - SUPRIMENTOS
BASE = "01 - ALMOXARIFADO/04 - ETIQUETAS/4 - ETIQUETAS CALIBRAÇÃO"
XLSX = BASE + "/Controle_Calibracao_Extreme_Wind_2026_FINAL.xlsx"
PAGINA = BASE + "/calibracao/index.html"
DADOS = BASE + "/calibracao/data.json"
ABA = "Controle de Calibração"
DEST = os.path.join("www", "calibracao")
MIN_LINHAS = 100


def log(msg):
    print(msg, flush=True)


def agora_sp():
    return datetime.datetime.now(ZoneInfo("America/Sao_Paulo"))


def fmt(d):
    return d.strftime("%d/%m/%Y")


def parse_br(s):
    m = re.match(r"^(\d{1,2})/(\d{1,2})/(\d{4})$", str(s or "").strip())
    if not m:
        return None
    try:
        return datetime.date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
    except ValueError:
        return None


def edate(d, meses):
    m = d.month - 1 + meses
    y = d.year + m // 12
    m = m % 12 + 1
    return datetime.date(y, m, min(d.day, calendar.monthrange(y, m)[1]))


def to_date(v):
    if isinstance(v, datetime.datetime):
        return v.date()
    if isinstance(v, datetime.date):
        return v
    if isinstance(v, str):
        s = v.strip()
        m = re.match(r"^(\d{4})-(\d{2})-(\d{2})", s)
        if m:
            return datetime.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        return parse_br(s)
    return None


def classificar(dias):
    if dias < 0:
        return "VENCIDO"
    if dias <= 90:
        return "VENCE EM 90 DIAS"
    return "OK"


def classe(status):
    if status == "OK":
        return "OK"
    if status.startswith("VENCE EM"):
        return "VENCE"
    if status.startswith("VENCIDO"):
        return "VENCIDO"
    return "SEM"


def linhas_da_planilha(dados):
    import openpyxl  # so e necessario aqui

    wb = openpyxl.load_workbook(io.BytesIO(dados), data_only=True)
    ws = wb[ABA]
    linhas = []
    for r in range(2, ws.max_row + 1):
        codigo = ws.cell(row=r, column=1).value
        if not codigo:
            continue
        cert = str(ws.cell(row=r, column=5).value or "").strip()
        d_cal = to_date(ws.cell(row=r, column=3).value)
        d_prox = to_date(ws.cell(row=r, column=4).value)
        if d_prox is None and d_cal is not None:
            d_prox = edate(d_cal, 12)
        linhas.append({
            "codigo": str(codigo).strip(),
            "dataCalibracao": fmt(d_cal) if d_cal else "ND",
            "proximaCalibracao": fmt(d_prox) if d_prox else "ND",
            "certificado": cert,
        })
    return linhas


def linhas_do_json(dados):
    j = json.loads(dados.decode("utf-8"))
    return [{
        "codigo": r["codigo"],
        "dataCalibracao": r.get("dataCalibracao", "ND"),
        "proximaCalibracao": r.get("proximaCalibracao", "ND"),
        "certificado": r.get("certificado", ""),
    } for r in j["rows"]]


def chave(r):
    return (r["codigo"], r["dataCalibracao"], r["proximaCalibracao"], r["certificado"])


def montar(linhas, agora):
    hoje = agora.date()
    rows = []
    cont = {"OK": 0, "VENCE": 0, "VENCIDO": 0, "SEM": 0}
    prox = 0
    for r in linhas:
        d = parse_br(r["proximaCalibracao"])
        if d is None:
            status, dias = "SEM DADOS", "ND"
        else:
            n = (d - hoje).days
            status, dias = classificar(n), str(n)
            if 0 <= n <= 90:
                prox += 1
        cont[classe(status)] += 1
        rows.append({
            "codigo": r["codigo"],
            "status": status,
            "dataCalibracao": r["dataCalibracao"],
            "proximaCalibracao": r["proximaCalibracao"],
            "certificado": r["certificado"],
            "diasRaw": dias,
        })
    return {
        "generated_at": agora.strftime("%d/%m/%Y às %H:%M"),
        "total": len(rows),
        "counts": cont,
        "due_soon": prox,
        "rows": rows,
    }


def sem_hora(d):
    x = dict(d)
    x.pop("generated_at", None)
    return x


def checar_pagina(b):
    erros = []
    if len(b) < 1000000:
        erros.append("index.html pequeno demais (%d bytes)" % len(b))
    for trecho in (b"<title>Controle de Calibra", b"cert-modal"):
        if trecho not in b:
            erros.append("index.html sem o trecho %r" % trecho)
    if not b.rstrip().lower().endswith(b"</html>"):
        erros.append("index.html nao termina em </html>")
    return erros


def checar_dados(d):
    erros = []
    if d["total"] < MIN_LINHAS:
        erros.append("so %d instrumentos (esperado >= %d)" % (d["total"], MIN_LINHAS))
    if sum(d["counts"].values()) != d["total"]:
        erros.append("contagens nao fecham com o total")
    if sum(1 for r in d["rows"] if r["status"] == "SEM DADOS") > d["total"] * 0.2:
        erros.append("mais de 20% das linhas sem data valida")
    return erros


def ler_local(caminho):
    return open(caminho, "rb").read() if os.path.isfile(caminho) else None


def main():
    dry = os.environ.get("DRY_RUN", "false").lower() != "false"
    agora = agora_sp()
    tok = token()

    pagina = baixar_um(tok, NS, PAGINA)
    dados_dbx = baixar_um(tok, NS, DADOS)
    log("Dropbox: index.html %d KB; data.json %d KB." % (len(pagina) // 1024, len(dados_dbx) // 1024))

    linhas_j = linhas_do_json(dados_dbx)
    fonte = "data.json do Dropbox"
    linhas = linhas_j
    try:
        linhas_x = linhas_da_planilha(baixar_um(tok, NS, XLSX))
        if len(linhas_x) >= MIN_LINHAS:
            dif = len(set(map(chave, linhas_x)) ^ set(map(chave, linhas_j)))
            log("Planilha: %d linhas; data.json do Dropbox: %d; diferencas de conteudo: %d." % (
                len(linhas_x), len(linhas_j), dif))
            linhas, fonte = linhas_x, "planilha .xlsx"
        else:
            log("[AVISO] planilha com so %d linhas; uso o data.json do Dropbox." % len(linhas_x))
    except Exception as e:  # noqa: BLE001
        log("[AVISO] nao consegui ler a planilha (%s); uso o data.json do Dropbox." % type(e).__name__)

    novo = montar(linhas, agora)
    erros = checar_pagina(pagina) + checar_dados(novo)
    if erros:
        for e in erros:
            log("[ERRO] " + e)
        log("Nada foi publicado: sanidade falhou.")
        return 1

    c = novo["counts"]
    log("Calibracao (fonte: %s, data %s): %d instrumentos, VENCIDO=%d, VENCE=%d, OK=%d, SEM=%d." % (
        fonte, fmt(agora.date()), novo["total"], c["VENCIDO"], c["VENCE"], c["OK"], c["SEM"]))
    amostra = next((r for r in novo["rows"] if r["codigo"] == "DEG-001"), None)
    if amostra:
        log("Amostra DEG-001: %s, %s dias." % (amostra["status"], amostra["diasRaw"]))

    mudou = []
    alvo_html = os.path.join(DEST, "index.html")
    alvo_json = os.path.join(DEST, "data.json")
    if pagina != ler_local(alvo_html):
        mudou.append("calibracao/index.html")
    atual = ler_local(alvo_json)
    try:
        igual = atual is not None and sem_hora(json.loads(atual.decode("utf-8"))) == sem_hora(novo)
    except Exception:  # noqa: BLE001
        igual = False
    if not igual:
        mudou.append("calibracao/data.json")

    if dry:
        log("DRY RUN: mudaria %s" % (", ".join(mudou) if mudou else "nada"))
        mudou = []
    else:
        os.makedirs(DEST, exist_ok=True)
        if "calibracao/index.html" in mudou:
            with open(alvo_html, "wb") as f:
                f.write(pagina)
        if "calibracao/data.json" in mudou:
            with open(alvo_json, "w", encoding="utf-8") as f:
                json.dump(novo, f, ensure_ascii=False, indent=2)
        for m in mudou:
            log("MUDOU www/" + m)
        if not mudou:
            log("Nenhuma mudanca em relacao ao site.")

    with open("changed.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(mudou) + ("\n" if mudou else ""))
    saida = os.environ.get("GITHUB_OUTPUT")
    if saida:
        with open(saida, "a", encoding="utf-8") as f:
            f.write("changed=%s\n" % ("true" if mudou else "false"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
