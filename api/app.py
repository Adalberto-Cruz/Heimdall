# app.py
# API REST do projeto Heimdall (Global Solution 2026.2 - CitizenTech)
# Adalberto Alves Cruz - RM 574115
#
# Recebe as leituras do ESP32, classifica, grava no CSV e no JSONL e calcula os indicadores.
# Rodar: uvicorn app:app --host 0.0.0.0 --port 8000
#
# Obs: essa e a versao "normal" (sem autenticacao, sem limite de requisicoes e sem limpar texto).
# Ela e de proposito o "antes" da disciplina de Cybersecurity. A versao blindada vai ser a app_seguro.py.

import unicodedata
from datetime import datetime
from typing import Literal, Optional

from fastapi import FastAPI, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator

import armazenamento
import config
import indicadores
import regras

app = FastAPI(
    title="Heimdall API",
    description="Heimdall - vigia do campo a mesa: leituras IoT contra perda de alimentos - GS 2026.2 CitizenTech",
    version="1.0",
)


def tirar_acentos(texto):
    # "Sítio" vira "Sitio" (o contrato pede texto sem acento por causa do Glue/Athena)
    normalizado = unicodedata.normalize("NFKD", texto)
    return "".join(letra for letra in normalizado if not unicodedata.combining(letra))


class Leitura(BaseModel):
    # medicoes (obrigatorias)
    id_sensor: str = Field(min_length=1, max_length=60)
    fazenda: str = Field(min_length=1, max_length=60)
    cultivo: str = Field(min_length=1, max_length=60)
    umidade: float = Field(ge=0, le=100, strict=True, allow_inf_nan=False)
    temperatura: float = Field(ge=-10, le=65, strict=True, allow_inf_nan=False)
    umidade_ar: float = Field(ge=0, le=100, strict=True, allow_inf_nan=False)
    nivel_reservatorio: float = Field(ge=0, le=100, strict=True, allow_inf_nan=False)
    data_hora: str

    # decisao do ESP32 (opcional, a API recalcula e so compara)
    status_umidade: Optional[Literal["OK", "ALERTA"]] = None
    status_temperatura: Optional[Literal["OK", "ALERTA"]] = None
    status_reservatorio: Optional[Literal["OK", "ALERTA"]] = None
    bomba: Optional[bool] = Field(default=None, strict=True)
    risco_perda_lote: Optional[Literal["BAIXO", "MEDIO", "ALTO"]] = None
    motivo: Optional[Literal[
        "BLOQUEIO_RESERVATORIO_BAIXO",
        "ALERTA_CALOR_EXTREMO",
        "IRRIGACAO_EMERGENCIAL_SOLO_CRITICO",
        "SOLO_SECO_JANELA_DESCONTO",
        "AGUARDANDO_JANELA_DESCONTO",
        "CONDICOES_ESTAVEIS",
    ]] = None

    @field_validator("id_sensor", "fazenda", "cultivo")
    @classmethod
    def limpar_texto(cls, valor):
        valor = tirar_acentos(valor).strip()
        if valor == "":
            raise ValueError("texto vazio")
        return valor

    @field_validator("data_hora")
    @classmethod
    def conferir_data(cls, valor):
        try:
            datetime.strptime(valor, config.FORMATO_DATA)
        except ValueError:
            raise ValueError("data_hora precisa estar no formato YYYY-MM-DD HH:MM:SS")
        return valor


def traduzir_erro(item):
    # o pydantic responde em ingles, aqui vira portugues pros prints
    tipo = item.get("type", "")
    ctx = item.get("ctx", {}) or {}
    if tipo == "missing":
        return "campo obrigatorio ausente"
    elif tipo in ("float_type", "float_parsing", "int_type", "int_parsing"):
        return "precisa ser um numero (sem aspas)"
    elif tipo == "finite_number":
        return "numero invalido (NaN ou infinito)"
    elif tipo == "greater_than_equal":
        return "abaixo do minimo permitido (" + str(ctx.get("ge")) + ")"
    elif tipo == "less_than_equal":
        return "acima do maximo permitido (" + str(ctx.get("le")) + ")"
    elif tipo == "string_too_long":
        return "texto maior que " + str(ctx.get("max_length")) + " caracteres"
    elif tipo in ("string_too_short", "string_type"):
        return "precisa ser um texto nao vazio"
    elif tipo == "bool_type":
        return "precisa ser true ou false"
    elif tipo == "literal_error":
        return "valor nao permitido, use: " + str(ctx.get("expected", "")).replace(" or ", " ou ")
    elif tipo == "json_invalid":
        return "JSON mal formatado"
    elif tipo == "model_attributes_type" or tipo == "dict_type":
        return "o corpo precisa ser um objeto JSON"
    elif tipo == "value_error":
        return str(ctx.get("error", item.get("msg", "valor invalido")))
    return item.get("msg", "valor invalido")


@app.exception_handler(RequestValidationError)
async def erro_de_validacao(request: Request, erro: RequestValidationError):
    # deixa a resposta do 422 mais facil de ler
    detalhes = []
    for item in erro.errors():
        caminho = [str(parte) for parte in item.get("loc", []) if parte != "body"]
        if item.get("type") == "json_invalid":
            caminho = []
        detalhes.append({
            "campo": ".".join(caminho) if caminho else "corpo da requisicao",
            "problema": traduzir_erro(item),
        })
    return JSONResponse(status_code=422, content={"erro": "leitura invalida", "detalhes": detalhes})


def resposta_arquivo_bloqueado():
    return JSONResponse(
        status_code=503,
        content={"erro": "nao foi possivel acessar o arquivo de dados",
                 "dica": "feche o leituras_sensores.csv se ele estiver aberto no Excel e tente de novo"},
    )


@app.get("/")
def raiz():
    # so pra conferir se a API ta no ar (util no ngrok)
    return {"status": "ok", "api": "Heimdall",
            "endpoints": ["POST /leituras", "GET /leituras", "GET /indicadores"]}


@app.post("/leituras", status_code=201)
def receber_leitura(leitura: Leitura):
    enviado = leitura.model_dump()
    registro, avisos = regras.classificar_leitura(enviado)
    divergencia = regras.houve_divergencia(enviado, registro)

    try:
        armazenamento.gravar_leitura(registro, divergencia)
    except armazenamento.ArquivoBloqueado:
        return resposta_arquivo_bloqueado()
    except OSError as erro:
        return JSONResponse(status_code=500, content={"erro": "falha ao gravar a leitura", "detalhe": str(erro)})

    resposta = {
        "mensagem": "leitura registrada",
        "leitura": registro,
        "alertas": regras.montar_alertas(registro),
        "divergencia_dispositivo": divergencia,
    }
    if avisos:
        resposta["avisos"] = avisos
    return resposta


@app.get("/leituras")
def listar_leituras(
    id_sensor: Optional[str] = None,
    fazenda: Optional[str] = None,
    limite: Optional[int] = Query(default=None, ge=1, le=1000),
):
    try:
        leituras, ignoradas = armazenamento.ler_leituras()
    except armazenamento.ArquivoBloqueado:
        return resposta_arquivo_bloqueado()

    # filtros opcionais
    filtradas = []
    for leitura in leituras:
        if id_sensor and leitura["id_sensor"] != id_sensor:
            continue
        if fazenda and leitura["fazenda"] != fazenda:
            continue
        filtradas.append(leitura)

    # limite pega as ultimas N leituras
    if limite:
        filtradas = filtradas[-limite:]

    return {"total": len(filtradas), "linhas_ignoradas": ignoradas, "leituras": filtradas}


@app.get("/indicadores")
def obter_indicadores():
    try:
        leituras, ignoradas = armazenamento.ler_leituras()
    except armazenamento.ArquivoBloqueado:
        return resposta_arquivo_bloqueado()

    resultado = indicadores.calcular_indicadores(leituras)
    resultado["linhas_ignoradas"] = ignoradas
    return resultado
