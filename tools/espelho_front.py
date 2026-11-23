# -*- coding: utf-8 -*-
"""
espelho_front.py -- espelha arquivos de front (JS) do Dropbox para www/ (roda no GitHub Actions, sem PC).

Hoje cobre: rdo-equipes.js (Reuniao Diaria > Equipes).
Fonte: 17 - SITE E APP (DASHBOARDS)/Gerenciamento de Equipes/Novo_Projeto_e_Busca/rdo-equipes.js

Regras:
- So publica se a sanidade passar: tamanho minimo, nao encolher mais que 30% em relacao ao publicado,
  marcador esperado presente e sintaxe valida (node --check). Se falhar, sai com erro e NAO grava nada.
- Em copia em conflito do Dropbox, vale a de horario mais recente (mesma regra do stage_dropbox).
- So grava se o conteudo mudou.
- Nunca imprime credenciais.

Variaveis: DROPBOX_APP_KEY, DROPBOX_APP_SECRET, DROPBOX_REFRESH_TOKEN, DRY_RUN (true = so mostra).
"""
import os
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from stage_dropbox import baixar_um, escolher_remoto, token  # noqa: E402

NS = "2024164339"
SITE = "17 - SITE E APP (DASHBOARDS)"
PASTA = SITE + "/Gerenciamento de Equipes/Novo_Projeto_e_Busca"

# (caminho no Dropbox, nome em www/, tamanho minimo em bytes, marcador que precisa existir)
ARQUIVOS = [
    (PASTA + "/rdo-equipes.js", "rdo-equipes.js", 20000, "rdoeq"),
]


def log(msg):
    print(msg, flush=True)


def sintaxe_ok(dados):
    with tempfile.NamedTemporaryFile(suffix=".js", delete=False) as f:
        f.write(dados)
        caminho = f.name
    try:
        r = subprocess.run(["node", "--check", caminho], capture_output=True, text=True, timeout=60)
        if r.returncode != 0:
            log("[ERRO] node --check: " + (r.stderr or "").strip().splitlines()[-1][:200])
        return r.returncode == 0
    finally:
        os.unlink(caminho)


def main():
    dry = os.environ.get("DRY_RUN", "false").strip().lower() == "true"
    tok = token()
    mudou = []
    falhou = 0
    for remoto, nome, minimo, marcador in ARQUIVOS:
        usar, copias = escolher_remoto(tok, NS, remoto)
        if copias:
            log("[conflito] %s: %d copia(s) em conflito; usando %s" % (
                nome, copias, "a copia em conflito mais recente" if usar != remoto else "o original (mais recente)"))
        dados = baixar_um(tok, NS, usar)
        alvo = os.path.join("www", nome)
        atual = open(alvo, "rb").read() if os.path.isfile(alvo) else None
        erros = []
        if len(dados) < minimo:
            erros.append("%s: so %d bytes (minimo %d)" % (nome, len(dados), minimo))
        if atual is not None and len(dados) < 0.7 * len(atual):
            erros.append("%s: encolheu de %d para %d bytes (mais de 30%%)" % (nome, len(atual), len(dados)))
        if marcador.encode() not in dados:
            erros.append("%s: marcador '%s' ausente" % (nome, marcador))
        if not erros and not sintaxe_ok(dados):
            erros.append("%s: sintaxe invalida" % nome)
        if erros:
            for e in erros:
                log("[ERRO] " + e)
            falhou += 1
            continue
        if atual == dados:
            log("Sem mudanca: %s (%d bytes)." % (nome, len(dados)))
            continue
        log("MUDOU www/%s (%s)" % (nome, "novo" if atual is None else "%d -> %d bytes" % (len(atual), len(dados))))
        if dry:
            log("DRY RUN: nao gravei.")
            continue
        with open(alvo, "wb") as f:
            f.write(dados)
        mudou.append(nome)

    with open("changed_front.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(mudou) + ("\n" if mudou else ""))
    saida = os.environ.get("GITHUB_OUTPUT")
    if saida:
        with open(saida, "a", encoding="utf-8") as f:
            f.write("changed=%s\n" % ("true" if mudou else "false"))
    if falhou:
        log("Nada foi publicado para os arquivos com erro.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
