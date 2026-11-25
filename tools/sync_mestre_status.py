# -*- coding: utf-8 -*-
"""
sync_mestre_status.py -- grava o STATUS do portal (aba EQ_StatusTecnicos) na coluna "RESUMO GESTAO A VISTA"
da aba BANCO DE DADOS da planilha VAGAS MESTRE (Dropbox). O portal manda; a coluna fica travada para humanos.

Seguranca (o log do repositorio e PUBLICO): so imprime contagens, NUNCA nome/matricula/valor de pessoa nem credencial.
- so troca celulas da coluna de status; todo o resto do .xlsx e copiado byte a byte (patch de XML, sem openpyxl);
- nunca sobrescreve BDH / BANCO DE HORAS / BACKUP / DESQUALIFICADO / ADMINISTRATIVO (categorias que o portal nao tem);
  EM CONTRATACAO so e trocado quando a matricula ja existe no portal;
- sobe com checagem de revisao (mode=update): se o arquivo mudou no Dropbox no meio do caminho, descarta e tenta no proximo ciclo;
- sem diferenca = nao grava nada; falha NUNCA derruba o job do BDH (o passo roda com continue-on-error).

Variaveis: DROPBOX_APP_KEY/SECRET/REFRESH_TOKEN, PORTAL_STATUS_URL, PORTAL_STATUS_KEY, DRY_RUN ("true" = so testa),
ARQUIVO_LOCAL (teste offline: caminho de um .xlsx; nao toca no Dropbox).
"""
import io
import json
import os
import re
import sys
import unicodedata
import urllib.parse
import urllib.request
import zipfile

NS = "2024164339"
CAMINHO = "2 - RH & DP/8 - VAGAS/VAGAS MESTRE.xlsx"
ABA = "BANCO DE DADOS"
COL_STATUS = "RESUMO GESTAO A VISTA"
TEXTO = {"A": "AGUARDANDO CONVOCAÇÃO", "R": "RESERVAS", "T": "ATIVO PARQUE", "I": "INDISPONIVEL"}
PRESERVAR = re.compile(r"\b(BDH|BANCO DE HORAS|BACKUP|DESQUALIFICADO|ADMINISTRATIVO)\b")


def log(m):
    print(m, flush=True)


def norm(s):
    return unicodedata.normalize("NFD", str(s or "")).encode("ascii", "ignore").decode().upper().strip()


def prio_letra(nome):
    n = norm(nome)
    return "A" if n.startswith("AGUARD") else "R" if n.startswith("RESERV") else "T" if n.startswith("ATIV") else "I" if n.startswith("INDISP") else ""


# ------------------------------------------------------------ portal
def ler_portal():
    url, chave = os.environ.get("PORTAL_STATUS_URL", ""), os.environ.get("PORTAL_STATUS_KEY", "")
    if not (url and chave):
        raise RuntimeError("Faltam PORTAL_STATUS_URL e/ou PORTAL_STATUS_KEY.")
    corpo = json.dumps({"action": "indicarEquipes", "modo": "statusMestre", "chave": chave}).encode()
    req = urllib.request.Request(url, data=corpo, headers={"Content-Type": "text/plain"}, method="POST")
    with urllib.request.urlopen(req, timeout=60) as r:
        d = json.loads(r.read().decode("utf-8"))
    if not d.get("ok") or not isinstance(d.get("status"), dict):
        raise RuntimeError("Portal nao devolveu a lista de status (resposta: %s)." % str(d.get("error") or d.get("motivo") or d.get("ok"))[:40])
    out = {}
    for mat, st in d["status"].items():
        l = prio_letra(st)
        if l:
            out[str(mat).strip()] = l
    if len(out) < 50:
        raise RuntimeError("Lista do portal curta demais (%d); nao grava." % len(out))
    return out


# ------------------------------------------------------------ dropbox
def _post(url, headers, data=None, timeout=120):
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read(), dict(r.headers)
    except urllib.error.HTTPError as e:
        try:
            c = e.read().decode("utf-8", "replace")[:160]
        except Exception:
            c = ""
        raise RuntimeError("Dropbox HTTP %s em %s: %s" % (e.code, url.split("/2/")[-1], c))


def token():
    import base64
    k, s, rt = (os.environ.get(x, "") for x in ("DROPBOX_APP_KEY", "DROPBOX_APP_SECRET", "DROPBOX_REFRESH_TOKEN"))
    if not (k and s and rt):
        raise RuntimeError("Faltam segredos do Dropbox.")
    b = base64.b64encode(("%s:%s" % (k, s)).encode()).decode()
    r, _ = _post("https://api.dropbox.com/oauth2/token", {"Authorization": "Basic " + b, "Content-Type": "application/x-www-form-urlencoded"},
                 urllib.parse.urlencode({"grant_type": "refresh_token", "refresh_token": rt}).encode())
    return json.loads(r.decode())["access_token"]


def baixar(tok):
    arg = json.dumps({"path": "ns:%s/%s" % (NS, CAMINHO)}, ensure_ascii=True)
    dados, h = _post("https://content.dropboxapi.com/2/files/download", {"Authorization": "Bearer " + tok, "Dropbox-API-Arg": arg}, None, 180)
    res = json.loads({k.lower(): v for k, v in h.items()}["dropbox-api-result"])
    return dados, res["rev"]


def subir(tok, dados, rev):
    arg = json.dumps({"path": "ns:%s/%s" % (NS, CAMINHO), "mode": {".tag": "update", "update": rev}, "autorename": False, "mute": True}, ensure_ascii=True)
    _post("https://content.dropboxapi.com/2/files/upload", {"Authorization": "Bearer " + tok, "Dropbox-API-Arg": arg, "Content-Type": "application/octet-stream"}, dados, 240)


# ------------------------------------------------------------ xlsx (patch de XML)
def achar_aba(z):
    wb = z.read("xl/workbook.xml").decode("utf-8")
    rels = z.read("xl/_rels/workbook.xml.rels").decode("utf-8")
    for nm, rid in re.findall(r'<sheet [^>]*?name="([^"]*)"[^>]*?r:id="([^"]*)"', wb):
        if norm(nm) == norm(ABA):
            m = re.search(r'<Relationship [^>]*?Id="%s"[^>]*?Target="([^"]*)"' % rid, rels) or re.search(r'<Relationship [^>]*?Target="([^"]*)"[^>]*?Id="%s"' % rid, rels)
            return "xl/" + m.group(1).lstrip("/").replace("xl/", "")
    raise RuntimeError("Aba nao encontrada.")


def patch(dados, port):
    z = zipfile.ZipFile(io.BytesIO(dados))
    caminho = achar_aba(z)
    ss = z.read("xl/sharedStrings.xml").decode("utf-8")
    T = ["".join(re.findall(r"<t[^>]*>(.*?)</t>", s, flags=re.S)).replace("&amp;", "&") for s in re.findall(r"<si>(.*?)</si>", ss, flags=re.S)]
    idx = {}
    for l, t in TEXTO.items():
        if t not in T:
            raise RuntimeError("Texto de status ausente nas strings da planilha (%s)." % l)
        idx[l] = T.index(t)
    x = z.read(caminho).decode("utf-8")
    # acha a coluna pelo titulo (linha 2), nao por posicao fixa
    col = None
    for m in re.finditer(r'<c r="([A-Z]+)2"([^>]*?)(?:/>|>(.*?)</c>)', x, flags=re.S):
        v = re.search(r"<v>(\d+)</v>", m.group(3) or "")
        if v and 't="s"' in m.group(2) and norm(T[int(v.group(1))]) == norm(COL_STATUS):
            col = m.group(1)
    if not col:
        raise RuntimeError("Coluna de status nao encontrada pelo titulo.")
    mats = {m.group(1): m.group(2) for m in re.finditer(r'<c r="A(\d+)"[^>]*><v>(\d+)</v>', x)}
    stats = {"trocadas": 0, "iguais": 0, "preservadas": 0, "sem_portal": 0}

    def rep(m):
        r, a, b = m.group(1), m.group(2), m.group(3) or ""
        mat = mats.get(r)
        if not mat or mat not in port:
            stats["sem_portal"] += 1
            return m.group(0)
        v = re.search(r"<v>(\d+)</v>", b)
        atual = T[int(v.group(1))] if v and 't="s"' in a else ""
        if PRESERVAR.search(norm(atual)):
            stats["preservadas"] += 1
            return m.group(0)
        if atual == TEXTO[port[mat]]:
            stats["iguais"] += 1
            return m.group(0)
        stats["trocadas"] += 1
        return '<c r="%s%s"%s t="s"><v>%d</v></c>' % (col, r, re.sub(r'\s*t="[^"]*"', "", a), idx[port[mat]])

    x2 = re.sub(r'<c r="%s(\d+)"([^>]*?)(?:/>|>(.*?)</c>)' % col, rep, x, flags=re.S)
    if x2 == x:
        return None, stats
    saida = io.BytesIO()
    zo = zipfile.ZipFile(saida, "w", zipfile.ZIP_DEFLATED)
    for it in z.infolist():
        d = z.read(it.filename)
        ni = zipfile.ZipInfo(it.filename, it.date_time)
        ni.compress_type, ni.external_attr = zipfile.ZIP_DEFLATED, it.external_attr
        zo.writestr(ni, x2.encode("utf-8") if it.filename == caminho else d)
    zo.close()
    # conferencia: reabre e confere que so a coluna de status mudou
    z2 = zipfile.ZipFile(io.BytesIO(saida.getvalue()))
    if z2.testzip() is not None:
        raise RuntimeError("zip invalido apos o patch")
    for it in z.infolist():
        if it.filename != caminho and z.read(it.filename) != z2.read(it.filename):
            raise RuntimeError("TRAVA: outra parte do arquivo mudou.")
    a = re.sub(r'<c r="%s\d+"[^>]*?(?:/>|>.*?</c>)' % col, "", x, flags=re.S)
    b = re.sub(r'<c r="%s\d+"[^>]*?(?:/>|>.*?</c>)' % col, "", x2, flags=re.S)
    if a != b:
        raise RuntimeError("TRAVA: o patch alterou algo fora da coluna de status.")
    return saida.getvalue(), stats


def main():
    dry = os.environ.get("DRY_RUN", "false").strip().lower() == "true"
    try:
        port = ler_portal() if not os.environ.get("PORTAL_LOCAL") else json.load(open(os.environ["PORTAL_LOCAL"]))
        log("Portal: %d tecnico(s) com status." % len(port))
        local = os.environ.get("ARQUIVO_LOCAL")
        if local:
            dados, rev, tok = open(local, "rb").read(), None, None
        else:
            tok = token()
            dados, rev = baixar(tok)
        novo, st = patch(dados, port)
        log("Resultado: %s" % json.dumps(st))
        if novo is None:
            log("Sem mudanca: o Mestre ja esta igual ao portal.")
            return 0
        if dry or local:
            log("[TESTE] haveria gravacao de %d celula(s); nada foi gravado." % st["trocadas"])
            if local:
                open(os.environ.get("SAIDA_LOCAL", "/tmp/mestre_sync_out.xlsx"), "wb").write(novo)
            return 0
        subir(tok, novo, rev)
        log("Gravado no Dropbox (%d celula(s), revisao conferida)." % st["trocadas"])
        return 0
    except Exception as e:  # noqa: BLE001
        log("[ERRO] %s" % str(e)[:300])
        return 1


if __name__ == "__main__":
    sys.exit(main())
