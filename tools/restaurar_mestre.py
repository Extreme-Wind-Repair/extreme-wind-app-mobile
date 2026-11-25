# -*- coding: utf-8 -*-
"""
restaurar_mestre.py -- lista e restaura versoes da VAGAS MESTRE no Dropbox (25/11/2026, Robson).
Log PUBLICO: so imprime revisao, data, tamanho e quem gravou o .xlsx (Excel x automacao), nunca nomes nem conteudo.
MODO=listar  -> mostra as ultimas versoes
MODO=restaurar REV=<rev> -> restaura a versao indicada (o Dropbox guarda a atual como versao anterior; nada se perde)
"""
import io
import json
import os
import sys
import zipfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sync_mestre_status as s  # noqa: E402

ARQ = "ns:%s/%s" % (s.NS, s.CAMINHO)


def api(tok, rota, corpo):
    r, _ = s._post("https://api.dropboxapi.com/2/" + rota, {"Authorization": "Bearer " + tok, "Content-Type": "application/json"}, json.dumps(corpo).encode())
    return json.loads(r.decode())


def quem_gravou(tok, rev):
    arg = json.dumps({"path": "rev:" + rev}, ensure_ascii=True)
    dados, _ = s._post("https://content.dropboxapi.com/2/files/download", {"Authorization": "Bearer " + tok, "Dropbox-API-Arg": arg}, None, 180)
    try:
        z = zipfile.ZipFile(io.BytesIO(dados))
        cs = {i.create_system for i in z.infolist()}
        abas = z.read("xl/workbook.xml").decode("utf-8", "replace").count("<sheet ")
        return ("Excel" if cs == {0} else "automacao" if cs == {3} else "misto"), abas, z.testzip() is None
    except Exception as e:  # noqa: BLE001
        return "ilegivel(%s)" % str(e)[:40], 0, False


def main():
    modo = os.environ.get("MODO", "listar").strip().lower()
    tok = s.token()
    if modo == "listar":
        d = api(tok, "files/list_revisions", {"path": ARQ, "limit": 25})
        s.log("Versoes (mais nova primeiro):")
        for e in d.get("entries", []):
            q, abas, ok = quem_gravou(tok, e["rev"])
            s.log("  rev=%s  %s  %8d bytes  gravado por: %-9s abas=%d zip_ok=%s" % (e["rev"], e["server_modified"], e["size"], q, abas, ok))
        return 0
    if modo == "restaurar":
        rev = os.environ.get("REV", "").strip()
        if not rev:
            s.log("[ERRO] informe REV.")
            return 1
        r = api(tok, "files/restore", {"path": ARQ, "rev": rev})
        s.log("Restaurado: rev=%s  %s  %d bytes" % (r.get("rev"), r.get("server_modified"), r.get("size", 0)))
        return 0
    s.log("[ERRO] MODO invalido.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
