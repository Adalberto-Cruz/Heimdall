"""
Servidor Python minimo da AICSS - recebe o JSON do ESP32, exibe no terminal e grava em CSV.
(A API completa com /indicadores, validacoes e seguranca fica nas entregas de Python e Cyber.)

Instalar:  pip install fastapi uvicorn
Rodar:     uvicorn servidor_aicss:app --host 0.0.0.0 --port 8000
Tunel:     ngrok http 8000   (copie a URL https para SERVER_URL no sketch)
"""
import csv
import json
import os
from datetime import datetime

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel

API_KEY = os.getenv("API_KEY", "CHAVE_SECRETA")
ARQ_CSV = "leituras_sensores.csv"
ARQ_JSONL = "leituras_sensores.jsonl"

CAMPOS = [
    "recebido_em", "id_sensor", "fazenda", "cultivo", "umidade", "temperatura",
    "umidade_ar", "nivel_reservatorio", "status_umidade", "status_temperatura",
    "status_reservatorio", "bomba", "risco_perda_lote", "motivo", "data_hora",
]

app = FastAPI(title="Heimdall - servidor AICSS")


class Leitura(BaseModel):
    id_sensor: str
    fazenda: str
    cultivo: str
    umidade: float
    temperatura: float
    umidade_ar: float
    nivel_reservatorio: float
    status_umidade: str
    status_temperatura: str
    status_reservatorio: str
    bomba: bool
    risco_perda_lote: str
    motivo: str
    data_hora: str


def limpar(texto: str) -> str:
    """Evita CSV injection: prefixa aspa simples se comecar com caractere de formula."""
    return "'" + texto if texto[:1] in ("=", "+", "-", "@") else texto


@app.post("/leituras")
def receber(leitura: Leitura, x_api_key: str = Header(default="")):
    if x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="API key invalida")

    dados = leitura.model_dump()
    dados["recebido_em"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # exibe no terminal
    print(
        f"[{dados['recebido_em']}] {dados['id_sensor']} | solo {dados['umidade']}% ({dados['status_umidade']}) | "
        f"temp {dados['temperatura']}C ({dados['status_temperatura']}) | "
        f"reserv {dados['nivel_reservatorio']}% ({dados['status_reservatorio']}) | "
        f"bomba={dados['bomba']} | risco={dados['risco_perda_lote']} | {dados['motivo']}"
    )

    # grava CSV
    novo = not os.path.exists(ARQ_CSV)
    with open(ARQ_CSV, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=CAMPOS)
        if novo:
            w.writeheader()
        w.writerow({c: (limpar(dados[c]) if isinstance(dados[c], str) else dados[c]) for c in CAMPOS})

    # grava JSON Lines (para Databricks/AWS depois)
    with open(ARQ_JSONL, "a", encoding="utf-8") as f:
        f.write(json.dumps(leitura.model_dump(), ensure_ascii=False) + "\n")

    return {"status": "ok", "motivo": dados["motivo"]}


@app.get("/leituras")
def listar():
    if not os.path.exists(ARQ_CSV):
        return []
    with open(ARQ_CSV, encoding="utf-8") as f:
        return list(csv.DictReader(f))
