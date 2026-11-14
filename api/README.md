# Heimdall API

Global Solution 2026.2 (CitizenTech) - FIAP
Adalberto Alves Cruz - RM 574115 | Danilo Keithi Makiya Nakasone - RM 574137 | Gustavo da Silva Nascimento - RM 570821

API REST em Python (FastAPI) que recebe as leituras do ESP32, classifica cada uma (solo seco, horario de ponta, reservatorio baixo, calor), grava em CSV e JSONL e calcula indicadores contra a perda de alimentos.

## Arquivos

| Arquivo | O que faz |
|---|---|
| `app.py` | API com os endpoints |
| `regras.py` | regras de classificacao (status, risco, bomba, motivo) |
| `armazenamento.py` | grava e le o CSV e o JSONL |
| `indicadores.py` | calculos do GET /indicadores |
| `config.py` | limites e premissas (limiar por cultivo, horarios da Portaria MME 137/2026, tarifa) |
| `gerar_dados.py` | manda 50 leituras pra API e gera o .jsonl oficial |
| `testar_cenarios.py` | roda os 3 cenarios de teste pros prints |
| `test_api.py` | testes automaticos (unittest) |

## Como rodar (Windows)

```
cd api
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

**Terminal 1 - subir a API:**
```
uvicorn app:app --host 0.0.0.0 --port 8000
```
Documentacao automatica: http://localhost:8000/docs

**Terminal 2 - nessa ordem:**
```
python -m unittest test_api -v     # 24 testes, nao mexe nos dados reais
python gerar_dados.py              # gera as 50 leituras oficiais (pasta dados/)
python testar_cenarios.py          # 3 cenarios pros prints do PDF
```

Rodar o `gerar_dados.py` **antes** do `testar_cenarios.py`, porque o gerador recusa rodar se ja tiver leituras gravadas (pra massa oficial sair limpa). Se precisar gerar de novo: pare a API, apague a pasta `dados/` e repita.

## Endpoints

| Metodo | Rota | Retorno |
|---|---|---|
| GET | `/` | confere se a API ta no ar |
| POST | `/leituras` | 201 com a leitura classificada / 422 se invalida |
| GET | `/leituras` | historico do CSV (filtros: `?id_sensor=`, `?fazenda=`, `?limite=`) |
| GET | `/indicadores` | media de umidade, temperatura maxima, alertas criticos, taxa da bomba, economia em R$, risco por fazenda e acao (VENDA_RAPIDA_PAA / MONITORAR / NORMAL) |

## Expor pro Wokwi (ngrok)

```
ngrok http 8000
```
Passar a URL `https://....ngrok-free.app` pro Gustavo usar no ESP32, com o header `ngrok-skip-browser-warning: true`.

## Observacao

A `app.py` e a versao sem autenticacao e sem limite de requisicoes, de proposito: ela e o "antes" da disciplina de Cybersecurity. A versao blindada e a `app_seguro.py`; instrucoes e a especificacao da assinatura do ESP32 estao em `SEGURANCA.md`.
