# -*- coding: utf-8 -*-
"""
sync_mestre_status.py -- liga a VAGAS MESTRE (Dropbox) ao portal da Reuniao Diaria, nos dois sentidos:
1) LISTA (VAGAS -> portal): tecnicos de campo da aba BANCO DE DADOS (matricula, nome oficial, contrato) vao para o portal
   (modo rosterMestre). Quem nao existe no portal entra como Reserva. E esta lista que trava o titular das equipes.
2) STATUS (portal -> VAGAS): o status do portal (aba EQ_StatusTecnicos) e gravado na coluna "RESUMO GESTAO A VISTA";
   a coluna fica travada para humanos.

Seguranca (o log do repositorio e PUBLICO): so imprime contagens, NUNCA nome/matricula/valor de pessoa nem credencial.
- so troca celulas da coluna de status; todo o resto do .xlsx e copiado byte a byte (patch de XML, sem openpyxl);
- v42 (25/11/2026): BDH e Backup agora vem do portal;
- v43 (25/11/2026): DESQUALIFICADO e ADMINISTRATIVO/ ENG tambem vem do portal (manuais la); nome sem matricula = EM CONTRATACAO;
  sem nome e sem matricula = coluna vazia; a coluna recebe uma validacao que recusa digitacao (o resto da aba fica livre);
- 25/11/2026 (correcao): celula com formula ou dentro de bloco de formula NUNCA e trocada; se algum bloco ficar incompleto, cancela;
  se o Excel salvou ha menos de 30 min (alguem editando), nao grava naquele ciclo;
- sobe com checagem de revisao (mode=update): se o arquivo mudou no Dropbox no meio do caminho, descarta e tenta no proximo ciclo;
- sem diferenca = nao grava nada; falha NUNCA derruba o job do BDH (o passo roda com continue-on-error).

Variaveis: DROPBOX_APP_KEY/SECRET/REFRESH_TOKEN, DROPBOX_WRITE_REFRESH_TOKEN, PORTAL_STATUS_URL, PORTAL_STATUS_KEY,
DRY_RUN ("true" = nao grava na VAGAS; a lista ainda e enviada ao portal), ARQUIVO_LOCAL (teste offline: .xlsx; nao toca em nada).
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
import datetime

NS = "2024164339"
CAMINHO = "2 - RH & DP/8 - VAGAS/VAGAS MESTRE.xlsx"
ABA = "BANCO DE DADOS"
COL_STATUS = "RESUMO GESTAO A VISTA"
COL_NOME = "NOME"
COL_CONTRATO = "CONTRATO"
TEXTO = {"A": "AGUARDANDO CONVOCAÇÃO", "R": "RESERVAS", "T": "ATIVO PARQUE", "I": "INDISPONIVEL", "B": "BANCO DE HORAS", "K": "BACKUP",
         "D": "DESQUALIFICADO", "E": "ADMINISTRATIVO/ ENG", "X": "DESLIGADO"}
MAX_DESLIGAR = 5  # v62: trava de seguranca -- mais que isso num ciclo = algo errado, nao apaga nada
PASTA_BACKUP = "2 - RH & DP/8 - VAGAS/_backup_desligamentos"
EM_CONTRATACAO = "EM CONTRATAÇÃO"  # v43: linha com nome e sem matricula (automatico)
TRAVA_TITULO = "Coluna travada"  # v43: validacao de dados que impede digitar na coluna de status
PRESERVAR = re.compile(r"\b(DESQUALIFICADO|ADMINISTRATIVO)\b")
CONTRATO_FORA = ("MEI", "DETERMINADO")  # cargos administrativos (regra Robson 25/11/2026)


def log(m):
    print(m, flush=True)


def norm(s):
    return unicodedata.normalize("NFD", str(s or "")).encode("ascii", "ignore").decode().upper().strip()


def prio_letra(nome):
    n = norm(nome)
    if n.startswith("BDH") or n.startswith("BANCO DE HORAS"):
        return "B"
    if n.startswith("BACKUP"):
        return "K"
    if n.startswith("DESQUALIF"):
        return "D"
    if n.startswith("ADMINISTR"):
        return "E"
    if n.startswith("DESLIG"):
        return "X"  # v62: Desligado no portal -> a linha sai da VAGAS
    return "A" if n.startswith("AGUARD") else "R" if n.startswith("RESERV") else "T" if n.startswith("ATIV") else "I" if n.startswith("INDISP") else ""


# ------------------------------------------------------------ portal
def _portal(extra, timeout=90):
    url, chave = os.environ.get("PORTAL_STATUS_URL", ""), os.environ.get("PORTAL_STATUS_KEY", "")
    if not (url and chave):
        raise RuntimeError("Faltam PORTAL_STATUS_URL e/ou PORTAL_STATUS_KEY.")
    corpo = {"action": "indicarEquipes", "chave": chave}
    corpo.update(extra)
    req = urllib.request.Request(url, data=json.dumps(corpo).encode(), headers={"Content-Type": "text/plain"}, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def ler_portal():
    d = _portal({"modo": "statusMestre"})
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


def enviar_lista(lista, todas=None):
    # v63: "todas" = todas as matriculas da aba (inclusive MEI/determinado): quem nao estiver nela vira Desligado no portal
    d = _portal({"modo": "rosterMestre", "tecnicos": lista, "todas": todas or []}, timeout=180)
    if not d.get("ok"):
        raise RuntimeError("Portal recusou a lista (resposta: %s)." % str(d.get("error") or d.get("motivo") or d.get("ok"))[:40])
    return d


# ------------------------------------------------------------ dropbox
def _post(url, headers, data=None, timeout=120):
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read(), dict(r.headers)
    except urllib.error.HTTPError as e:
        try:
            c = e.read().decode("utf-8", "replace")[:400]
        except Exception:
            c = ""
        raise RuntimeError("Dropbox HTTP %s em %s: %s" % (e.code, url.split("/2/")[-1], c))


def token():
    import base64
    k, s, rt = (os.environ.get(x, "") for x in ("DROPBOX_APP_KEY", "DROPBOX_APP_SECRET", "DROPBOX_REFRESH_TOKEN"))
    wr = os.environ.get("DROPBOX_WRITE_REFRESH_TOKEN", "")
    rt = wr or rt  # 24/11/2026: token proprio com permissao de escrita (so este script); sem ele usa o token de leitura
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
    return dados, res["rev"], res.get("server_modified", "")


def em_edicao(dados, server_modified, minutos=30):
    """True se o ultimo a salvar foi o Excel (gente) ha menos de N minutos: alguem provavelmente esta com o arquivo aberto."""
    import datetime
    try:
        z = zipfile.ZipFile(io.BytesIO(dados))
        excel = {i.create_system for i in z.infolist()} == {0}
        quando = datetime.datetime.strptime(server_modified, "%Y-%m-%dT%H:%M:%SZ")
        return excel and (datetime.datetime.utcnow() - quando).total_seconds() < minutos * 60
    except Exception:  # noqa: BLE001
        return False


def subir(tok, dados, rev):
    arg = json.dumps({"path": "ns:%s/%s" % (NS, CAMINHO), "mode": {".tag": "update", "update": rev}, "autorename": False, "mute": True}, ensure_ascii=True)
    _post("https://content.dropboxapi.com/2/files/upload", {"Authorization": "Bearer " + tok, "Dropbox-API-Arg": arg, "Content-Type": "application/octet-stream"}, dados, 240)


def backup(tok, dados):
    """v62: copia da VAGAS ANTES de apagar linha de desligado (pasta _backup_desligamentos, nunca sobrescreve)."""
    nome = "VAGAS MESTRE antes desligamento %s.xlsx" % datetime.datetime.utcnow().strftime("%Y-%m-%d %H%M UTC")
    arg = json.dumps({"path": "ns:%s/%s/%s" % (NS, PASTA_BACKUP, nome), "mode": "add", "autorename": True, "mute": True}, ensure_ascii=True)
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


def _strings(z):
    ss = z.read("xl/sharedStrings.xml").decode("utf-8")
    return ["".join(re.findall(r"<t[^>]*>(.*?)</t>", s, flags=re.S)).replace("&amp;", "&") for s in re.findall(r"<si>(.*?)</si>", ss, flags=re.S)]


def _celulas(x, T):
    """{(col, linha): texto} de todas as celulas com valor."""
    out = {}
    for m in re.finditer(r'<c r="([A-Z]+)(\d+)"([^>]*?)(?:/>|>(.*?)</c>)', x, flags=re.S):
        v = re.search(r"<v>(.*?)</v>", m.group(4) or "", flags=re.S)
        if not v:
            continue
        out[(m.group(1), int(m.group(2)))] = T[int(v.group(1))] if 't="s"' in m.group(3) else v.group(1)
    return out


def _coluna(cel, titulo):
    for (c, r), v in cel.items():
        if r == 2 and norm(v) == norm(titulo):
            return c
    return None


def col_num(c):
    n = 0
    for ch in c:
        n = n * 26 + ord(ch) - 64
    return n


def _ref(ref):
    m = re.fullmatch(r"([A-Z]+)(\d+)(?::([A-Z]+)(\d+))?", ref)
    if not m:
        return None
    c1, r1 = col_num(m.group(1)), int(m.group(2))
    c2, r2 = (col_num(m.group(3)), int(m.group(4))) if m.group(3) else (c1, r1)
    return (c1, r1, c2, r2)


def _blocos_formula(x):
    """Faixas (col1, lin1, col2, lin2) de formulas compartilhadas e de matriz da aba."""
    out = []
    for m in re.finditer(r'<f\b([^>]*)>', x):
        at = m.group(1)
        if 't="shared"' in at or 't="array"' in at:
            r = re.search(r'ref="([^"]+)"', at)
            if r and _ref(r.group(1)):
                out.append(_ref(r.group(1)))
    return out


MODELO_RH = re.compile(r'^IF\(\$A\d+="","","RESERVAS"\)$')  # formula modelo do RH na coluna de status


def _bloco_shared(x, b, so_modelo=False):
    """True se o bloco b e de formula COMPARTILHADA (nao matriz). so_modelo: e ainda a formula modelo do RH."""
    for m in re.finditer(r'<f\b([^>]*)>([^<]*)</f>', x):
        at = m.group(1)
        r = re.search(r'ref="([^"]+)"', at)
        if r and _ref(r.group(1)) == b:
            return 't="shared"' in at and (not so_modelo or bool(MODELO_RH.match(m.group(2).strip())))
    return False


def _conferir_blocos(x):
    """Toda celula existente dentro de um bloco de formula tem que continuar com formula; se nao, cancela (nao sobe nada)."""
    blocos = _blocos_formula(x)
    if not blocos:
        return
    for m in re.finditer(r'<c r="([A-Z]+)(\d+)"[^>]*?(?:/>|>(.*?)</c>)', x, flags=re.S):
        c, r = col_num(m.group(1)), int(m.group(2))
        if any(c1 <= c <= c2 and r1 <= r <= r2 for (c1, r1, c2, r2) in blocos) and "<f" not in (m.group(3) or ""):
            raise RuntimeError("TRAVA: bloco de formula ficaria incompleto em %s%d; nada foi gravado." % (m.group(1), r))


def _data_iso(v):
    """Data da planilha (numero serial do Excel ou dd/mm/aaaa) -> 'aaaa-mm-dd'; vazio se nao der."""
    v = str(v or "").strip()
    try:
        if re.fullmatch(r"\d+(\.\d+)?", v):
            return (datetime.date(1899, 12, 30) + datetime.timedelta(days=int(float(v)))).isoformat()
        m = re.fullmatch(r"(\d{1,2})/(\d{1,2})/(\d{2,4})", v)
        if m:
            a = int(m.group(3)); a = a + 2000 if a < 100 else a
            return datetime.date(a, int(m.group(2)), int(m.group(1))).isoformat()
    except Exception:  # noqa: BLE001
        pass
    return ""


def lista_tecnicos(dados):
    """[[matricula, nome oficial, contrato, marca, atributos]] dos tecnicos de campo da aba BANCO DE DADOS.
    v55 (27/11/2026): atributos (UF, BST, ART, nivel, funcao, passaporte, interesse) vao junto para o portal,
    para o algoritmo enxergar na hora quem ainda nao esta na base semanal."""
    z = zipfile.ZipFile(io.BytesIO(dados))
    T = _strings(z)
    cel = _celulas(z.read(achar_aba(z)).decode("utf-8"), T)
    cs, cn, cc = _coluna(cel, COL_STATUS), _coluna(cel, COL_NOME), _coluna(cel, COL_CONTRATO)
    if not (cs and cn):
        raise RuntimeError("Colunas de nome/status nao encontradas pelo titulo.")
    ce, cb, ca, cr, cf, cp, ci = (_coluna(cel, t) for t in ("ESTADO", "BST", "ART", "RESUMO IGOR", "FUNCAO", "DATA DE VALIDADE", "INTERESSE"))
    out, vistos = [], set()
    for (c, r), v in sorted(cel.items(), key=lambda kv: kv[0][1]):
        if c != "A" or r <= 2:
            continue
        mat = str(v).strip()
        mat = mat[:-2] if mat.endswith(".0") else mat
        if not re.fullmatch(r"\d{1,5}", mat) or mat in vistos:
            continue
        nome = re.sub(r"\s+", " ", str(cel.get((cn, r), ""))).strip()
        status = norm(cel.get((cs, r), ""))
        ctt = norm(cel.get((cc, r), "")) if cc else ""
        marca = "D" if "DESQUALIFICADO" in status else "E" if "ADMINISTRATIVO" in status else ""
        if not nome or (ctt in CONTRATO_FORA and not marca):
            continue
        vistos.add(mat)
        g = lambda col: str(cel.get((col, r), "")).strip() if col else ""  # noqa: E731
        attrs = {"uf": g(ce)[:2].upper(), "bst": g(cb) not in ("", "0"), "art": g(ca) not in ("", "0"), "nivel": g(cr)[:40],
                 "funcao": g(cf)[:40], "pass": _data_iso(g(cp)), "interesse": g(ci)[:20]}
        out.append([mat, nome, ctt, marca, attrs])  # v43: marca D/E = carga unica no portal; v55: atributos para o algoritmo
    return out


def todas_matriculas(dados):
    """v63: todas as matriculas da coluna A do BANCO DE DADOS (sem filtro de contrato)."""
    z = zipfile.ZipFile(io.BytesIO(dados))
    cel = _celulas(z.read(achar_aba(z)).decode("utf-8"), _strings(z))
    out = set()
    for (c, r), v in cel.items():
        m = re.sub(r"\.0$", "", str(v).strip())
        if c == "A" and r > 2 and re.fullmatch(r"\d{1,5}", m):
            out.add(m)
    return sorted(out)


def _xml_esc(t):
    return t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _trava_coluna(x, col):
    """v43: garante a validacao de dados que RECUSA digitacao na coluna de status (so nela; o resto da aba fica livre).
    Se o RH apagar a validacao, ela volta na proxima rodada."""
    if 'errorTitle="%s"' % TRAVA_TITULO in x:
        return x, 0
    dv = ('<dataValidation type="custom" allowBlank="1" showErrorMessage="1" errorStyle="stop" errorTitle="%s" '
          'error="O status vem do portal (Vagas). Altere pelo portal." sqref="%s3:%s5000"><formula1>FALSE</formula1></dataValidation>'
          % (TRAVA_TITULO, col, col))
    m = re.search(r'<dataValidations\b[^>]*>', x)
    if m:
        c = re.search(r'count="(\d+)"', m.group(0))
        ini = m.group(0).replace(c.group(0), 'count="%d"' % (int(c.group(1)) + 1)) if c else m.group(0)
        return x[:m.start()] + ini + dv + x[m.end():], 1
    fim = x.find("</sheetData>")
    m2 = re.compile(r'<(hyperlinks|printOptions|pageMargins|pageSetup|headerFooter|rowBreaks|colBreaks|customProperties|cellWatches|'
                    r'ignoredErrors|smartTags|drawing|legacyDrawing|legacyDrawingHF|picture|oleObjects|controls|webPublishItems|tableParts|extLst)[\s/>]').search(x, fim)
    pos = m2.start() if m2 else x.rfind("</worksheet>")
    return x[:pos] + '<dataValidations count="1">' + dv + '</dataValidations>' + x[pos:], 1


def patch(dados, port, preservar_manual=False):
    """Coluna de status = espelho do portal. v43 (25/11/2026, Robson):
    - com matricula: texto do status do portal (Desqualificado e Administrativo/Eng tambem vem do portal);
    - nome sem matricula: EM CONTRATACAO;  - sem nome e sem matricula: coluna vazia (desfaz texto colado por cima da trava);
    - celula de formula / bloco de formula nunca e tocada;  - garante a trava (validacao) da coluna."""
    z = zipfile.ZipFile(io.BytesIO(dados))
    caminho = achar_aba(z)
    T = _strings(z)
    pos_T = {}
    for i, t in enumerate(T):
        pos_T.setdefault(t, i)
    x = z.read(caminho).decode("utf-8")
    cel = _celulas(x, T)
    col, cnome = _coluna(cel, COL_STATUS), _coluna(cel, COL_NOME)
    if not (col and cnome):
        raise RuntimeError("Coluna de status/nome nao encontrada pelo titulo.")
    mats, nomes = {}, set()
    for (c, r), v in cel.items():
        if r <= 2:
            continue
        if c == "A":
            mt = str(v).strip()
            mt = mt[:-2] if mt.endswith(".0") else mt
            if re.fullmatch(r"\d{1,5}", mt):
                mats[r] = mt
        elif c == cnome and str(v).strip():
            nomes.add(r)
    stats = {"trocadas": 0, "iguais": 0, "preservadas": 0, "sem_portal": 0, "puladas_formula": 0,
             "em_contratacao": 0, "limpas": 0, "inseridas": 0, "trava_coluna": 0, "formulas_desfeitas": 0}
    # blocos de formula (compartilhada/matriz) que cobrem a coluna de status NUNCA sao tocados (ex.: AL309:AM314).
    cn = col_num(col)
    # v43: bloco de formula que fica SO na coluna de status (ex.: AM323:AM386 =IF($A323="","","RESERVAS"), modelo do RH)
    # e desfeito INTEIRO (todas as celulas viram valor de uma vez, nunca pela metade). Bloco que pega outra coluna
    # (ex.: AL309:AM314) continua intocavel.
    # v43b (25/11/2026, Robson autorizou): bloco com a formula modelo do RH (=IF($A..="","","RESERVAS")) que pega outra coluna
    # junto (ex.: AL309:AM314) tambem e desfeito inteiro; nas outras colunas fica o VALOR que a formula mostrava.
    cobrem = [b for b in _blocos_formula(x) if b[0] <= cn <= b[2]]
    desfazer = [b for b in cobrem if _bloco_shared(x, b) and (b[0] == b[2] == cn or _bloco_shared(x, b, so_modelo=True))]
    blocos = [b for b in cobrem if b not in desfazer]
    outras = [b for b in desfazer if not (b[0] == b[2] == cn)]
    soltos = {"n": 0}

    def dentro_de_bloco(linha):
        return any(c1 <= cn <= c2 and r1 <= linha <= r2 for (c1, r1, c2, r2) in blocos)

    def alvo(r, atual):
        mat = mats.get(r)
        if mat:
            if mat not in port:
                stats["sem_portal"] += 1
                return None
            l = port[mat]
            if preservar_manual and l not in ("D", "E") and PRESERVAR.search(norm(atual)):
                stats["preservadas"] += 1
                return None
            if l == "E" and norm(atual).startswith("ADMINISTRATIVO"):
                return atual  # mantem a variacao ja usada pelo RH (ADMINISTRATIVO / ADMINISTRATIVO/ ENG)
            return TEXTO[l]
        if r in nomes:
            return EM_CONTRATACAO
        return ""

    def xml_cel(r, attrs, texto):
        attrs = re.sub(r'\s*t="[^"]*"', "", attrs)
        if texto == "":
            return '<c r="%s%d"%s/>' % (col, r, attrs)
        if texto in pos_T:
            return '<c r="%s%d"%s t="s"><v>%d</v></c>' % (col, r, attrs, pos_T[texto])
        return '<c r="%s%d"%s t="inlineStr"><is><t>%s</t></is></c>' % (col, r, attrs, _xml_esc(texto))

    vistas = set()

    def rep(m):
        r, a, b = int(m.group(1)), m.group(2), m.group(3) or ""
        vistas.add(r)
        if r <= 2:
            return m.group(0)
        if dentro_de_bloco(r) or 't="array"' in b:
            stats["puladas_formula"] += 1
            return m.group(0)
        formula = "<f" in b
        v = re.search(r"<v>(.*?)</v>", b, flags=re.S)
        if v:
            atual = T[int(v.group(1))] if 't="s"' in a else v.group(1)
        else:
            it = re.search(r"<t[^>]*>(.*?)</t>", b, flags=re.S)
            atual = it.group(1) if it else ""
        novo = alvo(r, atual)
        if formula:
            soltos["n"] += 1
            stats["formulas_desfeitas"] += 1
            return xml_cel(r, a, atual if novo is None else novo)
        if novo is None or novo == atual:
            if novo is not None:
                stats["iguais"] += 1
            return m.group(0)
        stats["limpas" if novo == "" else "em_contratacao" if novo == EM_CONTRATACAO else "trocadas"] += 1
        return xml_cel(r, a, novo)

    x2 = re.sub(r'<c r="%s(\d+)"([^>]*?)(?:/>|>(.*?)</c>)' % col, rep, x, flags=re.S)

    # linha de tecnico (ou de contratacao) sem a celula de status: cria a celula na posicao certa
    def rep_linha(m):
        r = int(m.group(1))
        if r <= 2 or r in vistas or dentro_de_bloco(r):
            return m.group(0)
        novo = alvo(r, "")
        if not novo:
            return m.group(0)
        corpo = m.group(3)
        depois = [mm for mm in re.finditer(r'<c r="([A-Z]+)\d+"', corpo) if col_num(mm.group(1)) > cn]
        p = depois[0].start() if depois else len(corpo)
        stats["inseridas"] += 1
        stats["em_contratacao" if novo == EM_CONTRATACAO else "trocadas"] += 1
        return '<row r="%d"%s>%s%s%s</row>' % (r, m.group(2), corpo[:p], xml_cel(r, "", novo), corpo[p:])

    x2 = re.sub(r'<row r="(\d+)"([^>]*?)>(.*?)</row>', rep_linha, x2, flags=re.S)
    def em_outras(c, r):
        return c != col and any(c1 <= col_num(c) <= c2 and r1 <= r <= r2 for (c1, r1, c2, r2) in outras)

    def rep_outra(m):
        c, r, at, b = m.group(1), int(m.group(2)), m.group(3), m.group(4) or ""
        if not em_outras(c, r) or "<f" not in b:
            return m.group(0)
        v = re.search(r"<v>(.*?)</v>", b, flags=re.S)
        val = (T[int(v.group(1))] if 't="s"' in at else v.group(1)) if v else ""
        at2 = re.sub(r'\s*t="[^"]*"', "", at)
        soltos["n"] += 1
        stats["formulas_desfeitas"] += 1
        if val == "":
            return '<c r="%s%d"%s/>' % (c, r, at2)
        if val in pos_T:
            return '<c r="%s%d"%s t="s"><v>%d</v></c>' % (c, r, at2, pos_T[val])
        return '<c r="%s%d"%s t="inlineStr"><is><t>%s</t></is></c>' % (c, r, at2, _xml_esc(val))

    if outras:
        x2 = re.sub(r'<c r="([A-Z]+)(\d+)"([^>]*?)(?:/>|>(.*?)</c>)', rep_outra, x2, flags=re.S)

    # conferencia: fora da coluna de status (e das celulas dos blocos-modelo desfeitos) nada pode mudar
    def sem_cols(xx):
        xx = re.sub(r'<c r="%s\d+"[^>]*?(?:/>|>.*?</c>)' % col, "", xx, flags=re.S)
        if outras:
            xx = re.sub(r'<c r="([A-Z]+)(\d+)"[^>]*?(?:/>|>.*?</c>)', lambda m: "" if em_outras(m.group(1), int(m.group(2))) else m.group(0), xx, flags=re.S)
        return xx
    a, b = sem_cols(x), sem_cols(x2)
    if a != b:
        raise RuntimeError("TRAVA: o patch alterou algo fora da coluna de status.")
    x2, stats["trava_coluna"] = _trava_coluna(x2, col)
    if x2 == x:
        return None, stats
    _conferir_blocos(x2)
    # formula desfeita: a cadeia de calculo (calcChain.xml) apontaria para celula sem formula -> sai do arquivo;
    # o Excel recria sozinho ao abrir (mesmo comportamento de quando se apaga formula a mao).
    trocar, tirar = {caminho: x2.encode("utf-8")}, set()
    if soltos["n"] and "xl/calcChain.xml" in z.namelist():
        tirar.add("xl/calcChain.xml")
        ct = z.read("[Content_Types].xml").decode("utf-8")
        trocar["[Content_Types].xml"] = re.sub(r'<Override [^>]*PartName="/xl/calcChain.xml"[^>]*/>', "", ct).encode("utf-8")
        rl = z.read("xl/_rels/workbook.xml.rels").decode("utf-8")
        trocar["xl/_rels/workbook.xml.rels"] = re.sub(r'<Relationship [^>]*Target="(?:/xl/)?calcChain.xml"[^>]*/>', "", rl).encode("utf-8")
    saida = io.BytesIO()
    zo = zipfile.ZipFile(saida, "w", zipfile.ZIP_DEFLATED)
    for it in z.infolist():
        if it.filename in tirar:
            continue
        d = trocar.get(it.filename) or z.read(it.filename)
        ni = zipfile.ZipInfo(it.filename, it.date_time)
        ni.compress_type, ni.external_attr = zipfile.ZIP_DEFLATED, it.external_attr
        zo.writestr(ni, d)
    zo.close()
    z2 = zipfile.ZipFile(io.BytesIO(saida.getvalue()))
    if z2.testzip() is not None:
        raise RuntimeError("zip invalido apos o patch")
    for it in z.infolist():
        if it.filename in trocar or it.filename in tirar:
            continue
        if z.read(it.filename) != z2.read(it.filename):
            raise RuntimeError("TRAVA: outra parte do arquivo mudou.")
    if tirar and ("calcChain" in z2.read("[Content_Types].xml").decode() or "calcChain" in z2.read("xl/_rels/workbook.xml.rels").decode()):
        raise RuntimeError("TRAVA: referencia a calcChain ficou no arquivo.")
    return saida.getvalue(), stats


def remover_desligados(dados, mats):
    """v62 (28/11/2026, Robson): quem esta DESLIGADO no portal tem a linha APAGADA da aba BANCO DE DADOS.
    As linhas de baixo sobem (renumera linha e celulas). So roda se a aba nao tiver formula, comentario, link,
    formatacao condicional, tabela nem mesclagem abaixo da linha; confere que nenhuma outra celula mudou."""
    if not mats:
        return None, 0
    z = zipfile.ZipFile(io.BytesIO(dados))
    caminho = achar_aba(z)
    x = z.read(caminho).decode("utf-8")
    cel = _celulas(x, _strings(z))
    alvo = sorted({r for (c, r), v in cel.items() if c == "A" and r > 2 and re.sub(r"\.0$", "", str(v).strip()) in mats})
    if not alvo:
        return None, 0
    if len(alvo) > MAX_DESLIGAR:
        raise RuntimeError("TRAVA: %d linha(s) para apagar num ciclo (limite %d); nada apagado." % (len(alvo), MAX_DESLIGAR))
    if re.search(r"<f[ >]", x) or any(t in x for t in ("<conditionalFormatting", "<tableParts", "<drawing ")):
        raise RuntimeError("TRAVA: a aba tem formula/formatacao condicional/tabela/desenho; desligamento nao apagado.")
    for ref in re.findall(r'<mergeCell ref="([^"]+)"', x):
        if max(int(n) for n in re.findall(r"\d+", ref)) >= alvo[0]:
            raise RuntimeError("TRAVA: celula mesclada abaixo da linha a apagar; nada apagado.")
    S = set(alvo)
    RX = re.compile(r'<row\b[^>]*?\br="(\d+)"[^>]*?(?:/>|>.*?</row>)', re.S)

    def rep_row(m):
        n = int(m.group(1))
        if n in S:
            return ""
        d = n - sum(1 for a in alvo if a < n)
        if d == n:
            return m.group(0)
        b = re.sub(r'^(<row\b[^>]*?\br=")%d"' % n, lambda mm: mm.group(1) + '%d"' % d, m.group(0), count=1)
        return re.sub(r'(<c\b[^>]*?\br="[A-Z]+)%d"' % n, lambda mm: mm.group(1) + '%d"' % d, b)
    x2 = RX.sub(rep_row, x)
    # conferencia: tirando as linhas apagadas e ignorando o numero da linha, o resto e identico
    tira_r = lambda t: re.sub(r'\br="[A-Z]*\d+"', 'r=""', t)  # noqa: E731
    x_sem = RX.sub(lambda m: "" if int(m.group(1)) in S else m.group(0), x)
    if tira_r(x_sem) != tira_r(x2):
        raise RuntimeError("TRAVA: apagar a linha mudaria outra coisa na aba; nada apagado.")
    rows2 = [int(n) for n in re.findall(r'<row\b[^>]*?\br="(\d+)"', x2)]
    if rows2 != sorted(rows2) or len(rows2) != len(set(rows2)):
        raise RuntimeError("TRAVA: numeracao de linhas inconsistente; nada apagado.")
    cel2 = _celulas(x2, _strings(z))
    if any(c == "A" and re.sub(r"\.0$", "", str(v).strip()) in mats for (c, r), v in cel2.items() if r > 2):
        raise RuntimeError("TRAVA: matricula desligada continua na aba; nada apagado.")
    desl = lambda n: n - sum(1 for a in alvo if a < n)  # noqa: E731

    def rep_link(m):  # hyperlinks: o da linha apagada sai; os de baixo sobem
        n = int(m.group(2))
        return "" if n in S else m.group(0).replace('ref="%s%d"' % (m.group(1), n), 'ref="%s%d"' % (m.group(1), desl(n)), 1)
    x2 = re.sub(r'<hyperlink ref="([A-Z]+)(\d+)"[^>]*/>', rep_link, x2)
    if re.search(r'<hyperlink ref="[A-Z]+\d+:', x2):
        raise RuntimeError("TRAVA: link em intervalo de celulas; nada apagado.")
    extra = {}
    rels_p = caminho.replace("worksheets/", "worksheets/_rels/") + ".rels"
    if "<legacyDrawing" in x2 and rels_p in z.namelist():  # comentarios (notas) da aba: acompanham a linha
        rl = z.read(rels_p).decode("utf-8")
        base = caminho.rsplit("/", 1)[0]
        for tipo, alvo_p in re.findall(r'Type="[^"]*/(comments|vmlDrawing)"[^>]*Target="([^"]+)"', rl):
            fp = alvo_p.replace("../", "xl/") if alvo_p.startswith("../") else base + "/" + alvo_p
            t = z.read(fp).decode("utf-8")
            if tipo == "comments":
                def rep_cm(m):
                    n = int(m.group(2))
                    return "" if n in S else m.group(0).replace('ref="%s%d"' % (m.group(1), n), 'ref="%s%d"' % (m.group(1), desl(n)), 1)
                t = re.sub(r'<comment ref="([A-Z]+)(\d+)".*?</comment>', rep_cm, t, flags=re.S)
            else:
                def rep_sh(m):
                    r0 = re.search(r"<x:Row>(\d+)</x:Row>", m.group(0))
                    if not r0:
                        return m.group(0)
                    n = int(r0.group(1)) + 1
                    if n in S:
                        return ""
                    dd = n - desl(n)
                    if not dd:
                        return m.group(0)
                    sh = m.group(0).replace(r0.group(0), "<x:Row>%d</x:Row>" % (n - 1 - dd), 1)
                    return re.sub(r"(<x:Anchor>\s*)([^<]*)(</x:Anchor>)", lambda a: a.group(1) + ", ".join(str(max(int(v) - dd, 0)) if i in (2, 6) else v.strip() for i, v in enumerate(a.group(2).split(","))) + a.group(3), sh, count=1)
                t = re.sub(r"<v:shape\b.*?</v:shape>", rep_sh, t, flags=re.S)
            extra[fp] = t.encode("utf-8")
    x2 = re.sub(r'(<dimension ref="[A-Z]+\d+:[A-Z]+)(\d+)"', lambda m: m.group(1) + '%d"' % max(int(m.group(2)) - len(alvo), 2), x2, count=1)
    saida = io.BytesIO()
    zo = zipfile.ZipFile(saida, "w", zipfile.ZIP_DEFLATED)
    for it in z.infolist():
        d = x2.encode("utf-8") if it.filename == caminho else extra.get(it.filename) or z.read(it.filename)
        ni = zipfile.ZipInfo(it.filename, it.date_time)
        ni.compress_type, ni.external_attr = zipfile.ZIP_DEFLATED, it.external_attr
        zo.writestr(ni, d)
    zo.close()
    z2 = zipfile.ZipFile(io.BytesIO(saida.getvalue()))
    if z2.testzip() is not None:
        raise RuntimeError("zip invalido apos apagar linha")
    for it in z.infolist():
        if it.filename != caminho and it.filename not in extra and z.read(it.filename) != z2.read(it.filename):
            raise RuntimeError("TRAVA: outra parte do arquivo mudou.")
    return saida.getvalue(), len(alvo)


def main():
    dry = os.environ.get("DRY_RUN", "false").strip().lower() == "true"
    try:
        local = os.environ.get("ARQUIVO_LOCAL")
        if local:
            dados, rev, tok = open(local, "rb").read(), None, None
        else:
            tok = token()
            dados, rev, quando = baixar(tok)
        lista = lista_tecnicos(dados)
        log("VAGAS: %d tecnico(s) de campo na lista." % len(lista))
        lista_ok = False
        if not local:
            try:
                r = enviar_lista(lista, todas_matriculas(dados))
                lista_ok = True
                log("Lista enviada ao portal: %d novo(s), %d nome(s) e %d contrato(s) atualizados." % (r.get("novos", 0), r.get("nomes", 0), r.get("contratos", 0)))
            except Exception as e:  # noqa: BLE001  (a lista falhar nao impede a gravacao do status)
                log("[AVISO] lista nao enviada: %s" % str(e)[:200])
        port = ler_portal() if not os.environ.get("PORTAL_LOCAL") else json.load(open(os.environ["PORTAL_LOCAL"]))
        log("Portal: %d tecnico(s) com status." % len(port))
        novo, st = patch(dados, port, preservar_manual=not lista_ok)  # lista falhou: nao mexe em DESQUALIFICADO/ADMINISTRATIVO
        log("Resultado: %s" % json.dumps(st))
        n_del = 0
        desl = {m for m, l in port.items() if l == "X"}
        if desl:  # v62: desligado no portal -> linha apagada da VAGAS (com backup antes)
            try:
                sem, n_del = remover_desligados(novo if novo is not None else dados, desl)
                if sem is not None:
                    novo = sem
                log("Desligados no portal: %d; linha(s) a apagar na VAGAS: %d." % (len(desl), n_del))
            except Exception as e:  # noqa: BLE001  (falha no desligamento nao impede a gravacao do status)
                n_del = 0
                log("[AVISO] desligamento nao aplicado: %s" % str(e)[:200])
        if novo is None:
            log("Sem mudanca: o Mestre ja esta igual ao portal.")
            return 0
        if dry or local:
            log("[TESTE] haveria gravacao de %d celula(s) e %d linha(s) apagada(s); nada foi gravado." % (st["trocadas"], n_del))
            if local:
                open(os.environ.get("SAIDA_LOCAL", "/tmp/mestre_sync_out.xlsx"), "wb").write(novo)
            return 0
        if em_edicao(dados, quando):
            log("Arquivo salvo pelo Excel ha menos de 30 min (alguem editando): nao grava agora; tenta no proximo ciclo.")
            return 0
        if n_del:
            backup(tok, dados)  # se o backup falhar, cai no except e NADA e gravado
            log("Backup da VAGAS salvo antes de apagar %d linha(s)." % n_del)
        subir(tok, novo, rev)
        log("Gravado no Dropbox (%d celula(s), %d linha(s) de desligado apagada(s), revisao conferida)." % (st["trocadas"], n_del))
        return 0
    except Exception as e:  # noqa: BLE001
        log("[ERRO] %s" % str(e)[:300])
        return 1


if __name__ == "__main__":
    sys.exit(main())
