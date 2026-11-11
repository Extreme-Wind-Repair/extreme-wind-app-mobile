#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Gera data.json (e atualiza o bloco embutido no index.html) para o dashboard
estático a partir da planilha oficial:
    Controle_Calibracao_Extreme_Wind_2026_FINAL.xlsx

COMO USAR
    pip install openpyxl          (uma vez só)
    python3 generate_data.py                      # procura a planilha em ../
    python3 generate_data.py caminho/da/planilha.xlsx

Depois faça commit + push de data.json e index.html. O GitHub Pages atualiza
sozinho em alguns minutos.

O QUE MUDOU (v3)
- Lê direto do .xlsx (não precisa mais colar raw_text.txt).
- Datas vêm como data real da planilha, então não há mais ambiguidade
  dia/mês (era a causa dos erros antigos de 12/02 vs 02/12).
- "Dias para Vencer" e Status são RECALCULADOS com a data de hoje a cada
  execução, para não ficarem desatualizados se a planilha não foi aberta
  no dia. Regra: dias < 0 = VENCIDO; 0 a 90 = VENCE EM 90 DIAS; > 90 = OK;
  sem data válida = SEM DADOS.
- Fallback: se não achar a planilha nem openpyxl, usa raw_text.txt (modo
  antigo, com as regras de normalização de data).
"""
import calendar
import datetime
import glob
import json
import os
import re
import sys

OUTPUT_PATH = "data.json"
INDEX_HTML_PATH = "index.html"
RAW_TEXT_PATH = "raw_text.txt"
XLSX_NAME = "Controle_Calibracao_Extreme_Wind_2026_FINAL.xlsx"
SHEET_NAME = "Controle de Calibração"


# ---------------------------------------------------------------- utilidades
def status_class(s):
    if s == "OK":
        return "OK"
    if s.startswith("VENCE EM"):
        return "VENCE"
    if s.startswith("VENCIDO"):
        return "VENCIDO"
    return "SEM"


def to_int(v):
    try:
        return int(v)
    except Exception:
        return None


def edate(d, months):
    m = d.month - 1 + months
    y = d.year + m // 12
    m = m % 12 + 1
    return datetime.date(y, m, min(d.day, calendar.monthrange(y, m)[1]))


def fmt(d):
    return d.strftime("%d/%m/%Y")


def to_date(v):
    """Converte célula (data real ou texto) em datetime.date; None se inválido."""
    if isinstance(v, datetime.datetime):
        return v.date()
    if isinstance(v, datetime.date):
        return v
    if isinstance(v, str):
        s = v.strip()
        m = re.match(r"^(\d{4})-(\d{2})-(\d{2})", s)
        if m:
            return datetime.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        m = re.match(r"^(\d{1,2})/(\d{1,2})/(\d{2,4})$", s)
        if m:
            d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
            if y < 100:
                y += 2000
            try:
                return datetime.date(y, mo, d)
            except ValueError:
                return None
    return None


def classify(dias):
    if dias < 0:
        return "VENCIDO"
    if dias <= 90:
        return "VENCE EM 90 DIAS"
    return "OK"


# ------------------------------------------------------------ leitura (xlsx)
def find_xlsx():
    if len(sys.argv) > 1 and sys.argv[1].lower().endswith(".xlsx"):
        return sys.argv[1]
    here = os.path.dirname(os.path.abspath(__file__))
    for base in (here, os.path.join(here, ".."), os.path.join(here, "..", "..")):
        p = os.path.join(base, XLSX_NAME)
        if os.path.exists(p):
            return p
    hits = glob.glob(os.path.join(here, "..", "*.xlsx"))
    return hits[0] if hits else None


def rows_from_xlsx(path, hoje):
    import openpyxl  # import tardio para o fallback funcionar sem a lib

    wb = openpyxl.load_workbook(path, data_only=True)
    ws = wb[SHEET_NAME]
    rows, avisos = [], []
    for r in range(2, ws.max_row + 1):
        codigo = ws.cell(row=r, column=1).value
        if not codigo:
            continue
        codigo = str(codigo).strip()
        cert = str(ws.cell(row=r, column=5).value or "").strip()
        status_plan = (ws.cell(row=r, column=2).value or "")
        status_plan = str(status_plan).strip()
        d_cal = to_date(ws.cell(row=r, column=3).value)
        d_prox = to_date(ws.cell(row=r, column=4).value)
        if d_prox is None and d_cal is not None:
            d_prox = edate(d_cal, 12)

        if d_prox is None:
            status, dias_raw = "SEM DADOS", "ND"
        else:
            dias = (d_prox - hoje).days
            status, dias_raw = classify(dias), str(dias)
            if status_plan and status_plan != status:
                avisos.append(f"{codigo}: planilha={status_plan} -> recalculado={status}")

        rows.append({
            "codigo": codigo,
            "status": status,
            "dataCalibracao": fmt(d_cal) if d_cal else "ND",
            "proximaCalibracao": fmt(d_prox) if d_prox else "ND",
            "certificado": cert,
            "diasRaw": dias_raw,
        })
    return rows, avisos


# -------------------------------------------------- leitura (fallback texto)
def normalize_date_txt(raw, first_is_day_default):
    raw = (raw or "").strip()
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})[ T]", raw)
    if m:
        return f"{m.group(3)}/{m.group(2)}/{m.group(1)}"
    m = re.match(r"^(\d{1,2})/(\d{1,2})/(\d{2,4})$", raw)
    if not m:
        return raw
    a, b, y = int(m.group(1)), int(m.group(2)), m.group(3)
    if a > 12 and b <= 12:
        dia, mes = a, b
    elif b > 12 and a <= 12:
        dia, mes = b, a
    elif a > 12 and b > 12:
        return raw
    elif first_is_day_default:
        dia, mes = a, b
    else:
        dia, mes = b, a
    if len(y) == 2:
        y = "20" + y
    return f"{dia:02d}/{mes:02d}/{y}"


def us_short(raw):
    raw = (raw or "").strip()
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})[ T]", raw)
    if m:
        return f"{m.group(3)}/{m.group(2)}/{m.group(1)}"
    m = re.match(r"^(\d{1,2})/(\d{1,2})/(\d{2,4})$", raw)
    if not m:
        return raw
    mm, dd, y = m.groups()
    if len(y) == 2:
        y = "20" + y
    return f"{dd.zfill(2)}/{mm.zfill(2)}/{y}"


def rows_from_text(path):
    with open(path, "r", encoding="utf-8") as f:
        raw = f.read()
    rows, in_table = [], False
    for line in raw.split("\n"):
        if line.startswith("\tCódigo\tStatus"):
            in_table = True
            continue
        if in_table:
            if not line.startswith("\t"):
                in_table = False
                continue
            p = line.split("\t")
            if len(p) < 6:
                continue
            short = len(p) <= 7
            dc = us_short(p[3]) if short else normalize_date_txt(p[3], True)
            pc = us_short(p[4]) if short else normalize_date_txt(p[4], False)
            rows.append({
                "codigo": p[1].strip(),
                "status": p[2].strip(),
                "dataCalibracao": dc,
                "proximaCalibracao": pc,
                "diasRaw": p[-1].strip(),
            })
    return rows


# ---------------------------------------------------------------------- main
def main():
    agora = datetime.datetime.now()
    hoje = agora.date()
    rows, avisos, origem = [], [], ""

    xlsx = find_xlsx()
    if xlsx:
        try:
            rows, avisos = rows_from_xlsx(xlsx, hoje)
            origem = f"planilha {os.path.basename(xlsx)}"
        except ImportError:
            print("AVISO: openpyxl não instalado (pip install openpyxl). Tentando raw_text.txt.")
    if not rows and os.path.exists(RAW_TEXT_PATH):
        rows = rows_from_text(RAW_TEXT_PATH)
        origem = RAW_TEXT_PATH
    if not rows:
        print("ERRO: não achei a planilha .xlsx nem raw_text.txt. "
              "Passe o caminho: python3 generate_data.py caminho/planilha.xlsx")
        sys.exit(1)

    counts = {"OK": 0, "VENCE": 0, "VENCIDO": 0, "SEM": 0}
    for r in rows:
        counts[status_class(r["status"])] += 1
    due_soon = sum(1 for r in rows
                   if to_int(r["diasRaw"]) is not None and 0 <= to_int(r["diasRaw"]) <= 90)

    data = {
        "generated_at": agora.strftime("%d/%m/%Y às %H:%M"),
        "total": len(rows),
        "counts": counts,
        "due_soon": due_soon,
        "rows": rows,
    }
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    # Bloco embutido no index.html (fallback para abrir via file://)
    try:
        with open(INDEX_HTML_PATH, "r", encoding="utf-8") as f:
            html = f.read()
        emb = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
        new_html, n = re.subn(
            r'(<script id="embedded-data" type="application/json">).*?(</script>)',
            lambda m: m.group(1) + emb + m.group(2), html, flags=re.S)
        if n:
            with open(INDEX_HTML_PATH, "w", encoding="utf-8") as f:
                f.write(new_html)
        else:
            print(f"AVISO: bloco embedded-data não encontrado em {INDEX_HTML_PATH}.")
    except FileNotFoundError:
        print(f"AVISO: {INDEX_HTML_PATH} não encontrado nesta pasta.")

    print(f"Fonte: {origem}")
    if avisos:
        print(f"Status recalculado (planilha desatualizada) em {len(avisos)} linha(s).")
    print(f"OK: {OUTPUT_PATH} gerado com {len(rows)} instrumentos "
          f"(VENCIDO={counts['VENCIDO']}, VENCE EM 90 DIAS={counts['VENCE']}, "
          f"OK={counts['OK']}, SEM DADOS={counts['SEM']}).")


if __name__ == "__main__":
    main()
