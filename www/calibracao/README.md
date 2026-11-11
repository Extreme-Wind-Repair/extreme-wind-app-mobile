# Painel de Controle de Calibração — Extreme Wind

Dashboard estático (HTML + JS puro, sem backend) para acompanhar prazos de
calibração dos instrumentos de medição. Feito para rodar direto no GitHub
Pages ou em qualquer hospedagem de arquivos estáticos.

## Como publicar

1. Suba os arquivos `index.html` e `data.json` para um repositório no GitHub.
2. Em **Settings → Pages**, ative o GitHub Pages apontando para a branch/pasta
   onde esses arquivos estão.
3. Pronto — a URL gerada pelo GitHub Pages já mostra o painel.

## Importante: isso é um snapshot, não um painel ao vivo

Este `index.html` **não se conecta ao Dropbox**. Ele só lê o arquivo
`data.json` que está no mesmo repositório. Ou seja, os dados ficam parados
na última vez que alguém gerou o `data.json` — não atualiza sozinho.

Se você precisa de um painel que busca a planilha do Dropbox automaticamente
toda vez que é aberto, esse é o painel ao vivo do Cowork (fora do escopo
deste repositório).

## Como atualizar os dados

1. Uma vez só: `pip install openpyxl`
2. Rode nesta pasta:
   ```
   python3 generate_data.py
   ```
   O script procura `Controle_Calibracao_Extreme_Wind_2026_FINAL.xlsx` na
   pasta acima (ou passe o caminho: `python3 generate_data.py caminho/planilha.xlsx`),
   recalcula Status e Dias para Vencer com a data de hoje e reescreve
   `data.json` e o bloco embutido do `index.html`.
3. Faça commit e push de `data.json` e `index.html`. O GitHub Pages atualiza
   em alguns minutos.

Sem a planilha à mão, o script usa `raw_text.txt` como alternativa (modo antigo).

## Arquivos

- `index.html` — o dashboard (KPIs, gráficos, tabela). Não precisa de build,
  é HTML puro com Chart.js e Grid.js carregados via CDN.
- `data.json` — os dados exibidos (gerado pelo script, não edite à mão).
- `generate_data.py` — gera `data.json` direto da planilha .xlsx.
- `raw_text.txt` — texto bruto da planilha, usado como entrada do script.

## Certificados para download (coluna "Certificado")

- O `generate_data.py` lê a pasta `../CERTIFICADOS`, identifica o código do
  instrumento pelo final do nome do PDF (padrão: `CERTIFICADO 2725-26 - ... - TRE-009.pdf`)
  e copia o arquivo para `certificados/CERT_2725-26_TRE-009.pdf`.
- No painel, a linha do instrumento ganha um botão "⬇ 2725/26" que baixa o PDF.
- Ao publicar no GitHub, suba também a pasta `certificados/` junto com
  `index.html` e `data.json`. Atenção: se o repositório/Pages for público,
  os PDFs ficam públicos.
- PDF com nome fora do padrão (sem " - CÓDIGO.pdf" no final) aparece como AVISO
  ao rodar o script e não é vinculado.
