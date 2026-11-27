# -*- coding: utf-8 -*-
"""
espelho_radar.py -- espelha o Radar de Campo do Dropbox para www/radar-campo/index.html
(roda no GitHub Actions, sem PC e sem Claude).

O index.html e gerado por outra maquina e salvo no Dropbox (3 - SUPRIMENTOS). Aqui ele e copiado byte a byte,
depois de checagens de sanidade. Nunca recalcula nem edita o HTML.

Sanidade (se falhar: exit 1 e NADA e publicado):
  - tamanho minimo; <div> pareados; termina em </html>; contem 'const DATA = {...};' com JSON valido.

Variaveis: DROPBOX_APP_KEY, DROPBOX_APP_SECRET, DROPBOX_REFRESH_TOKEN, DRY_RUN (true = so mostra).
Nunca imprime credenciais.
"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from stage_dropbox import baixar_um, token  # noqa: E402  (reaproveita a autenticacao do Dropbox)

NS = "12772033633"  # 3 - SUPRIMENTOS
ORIGEM = "01 - ALMOXARIFADO/05 - BD/6 - PENDENCIA DE CHECKLIST/radar-de-campo/index.html"
ALVO = os.path.join("www", "radar-campo", "index.html")
NOME = "radar-campo/index.html"
MIN_BYTES = 50000


def log(msg):
    print(msg, flush=True)


def checar(raw):
    erros = []
    if len(raw) < MIN_BYTES:
        erros.append("arquivo pequeno demais (%d bytes; minimo %d)" % (len(raw), MIN_BYTES))
    try:
        h = raw.decode("utf-8")
    except UnicodeDecodeError:
        return erros + ["arquivo nao e UTF-8 valido"]
    if h.count("<div") != h.count("</div>"):
        erros.append("<div> desbalanceado (%d x %d)" % (h.count("<div"), h.count("</div>")))
    if not h.rstrip().lower().endswith("</html>"):
        erros.append("nao termina em </html>")
    m = re.search(r"const DATA\s*=\s*(\{.*?\});\s*\n", h, re.S)
    if not m:
        erros.append("nao encontrei 'const DATA = {...};'")
    else:
        try:
            meta = json.loads(m.group(1)).get("meta", {})
            log("Radar: semana %s, periodo %s." % (meta.get("semana", "?"), meta.get("periodo", "?")))
        except ValueError:
            erros.append("'const DATA' nao e JSON valido")
    return erros


def main():
    dry = os.environ.get("DRY_RUN", "false").lower() != "false"
    raw = baixar_um(token(), NS, ORIGEM)
    log("Dropbox: radar-de-campo/index.html %d KB." % (len(raw) // 1024))

    erros = checar(raw)
    if erros:
        for e in erros:
            log("[ERRO] " + e)
        log("Nada foi publicado: sanidade falhou.")
        return 1

    atual = open(ALVO, "rb").read() if os.path.isfile(ALVO) else None
    mudou = [] if atual == raw else [NOME]
    if dry:
        log("DRY RUN: mudaria %s" % (NOME if mudou else "nada"))
        mudou = []
    elif mudou:
        os.makedirs(os.path.dirname(ALVO), exist_ok=True)
        with open(ALVO, "wb") as f:
            f.write(raw)
        log("MUDOU www/" + NOME)
    else:
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
