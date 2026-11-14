# app_seguro.py
# Versao BLINDADA da API (disciplina Cognitive Cybersecurity) - o "depois".
# Adalberto Alves Cruz - RM 574115
#
# O que muda em relacao a app.py:
#   1. POST so aceita leitura assinada pelo ESP32 (HMAC-SHA256 com chave por dispositivo)  -> 401
#   2. timestamp com prazo + assinatura de uso unico (anti-replay)                         -> 401
#   3. GET exige X-API-Key                                                                -> 401
#   4. schema estrito: campo extra e payload grande sao recusados                          -> 422
#   5. variacao fisicamente impossivel (ex: 25 C -> 50 C em segundos) e recusada            -> 422
#   6. limite de requisicoes por IP e por dispositivo                                      -> 429
#   7. texto que viraria formula no Excel e neutralizado (CSV injection)
#   8. alerta de sensor que parou de mandar leitura (perda de visibilidade)
#   9. segredos no .env e todos os eventos no auditoria_seguranca.log
#  10. /docs desligado (menos superficie exposta)
#
# Rodar: python servidor.py --modo seguro   (porta 8001, dados em dados_seguro/)

import json
from datetime import datetime
from typing import Optional

from fastapi import FastAPI, Query, Request
from fastapi.responses import JSONResponse
from pydantic import ConfigDict, ValidationError

import armazenamento
import config
import indicadores
import regras
import seguranca
from app import Leitura, traduzir_erro

# ---------- configuracao vinda do .env (sem segredo no codigo) ----------
ENV = seguranca.carregar_env()
API_KEY = ENV["API_KEY"]
CHAVES = seguranca.ler_chaves_dispositivos(ENV["CHAVES_DISPOSITIVOS"])
TOLERANCIA_S = int(ENV.get("TOLERANCIA_TIMESTAMP_S", "60"))
TAMANHO_MAX = int(ENV.get("TAMANHO_MAX_PAYLOAD", "2048"))
SENSOR_TIMEOUT_MIN = int(ENV.get("SENSOR_TIMEOUT_MIN", "10"))

limite_ip = seguranca.LimitadorRequisicoes(int(ENV.get("LIMITE_REQ_IP_MIN", "60")))
limite_dispositivo = seguranca.LimitadorRequisicoes(int(ENV.get("LIMITE_REQ_DISPOSITIVO_MIN", "30")))
anti_replay = seguranca.AntiReplay(TOLERANCIA_S)
plausibilidade = seguranca.ChecagemPlausibilidade(
    delta_temp=float(ENV.get("MAX_SALTO_TEMPERATURA", "8")),
    delta_umid=float(ENV.get("MAX_SALTO_UMIDADE", "30")),
    janela_s=int(ENV.get("JANELA_PLAUSIBILIDADE_S", "300")),
)

app = FastAPI(
    title="Heimdall API - versao segura",
    version="1.0-seguro",
    docs_url=None, redoc_url=None, openapi_url=None,
)


class LeituraSegura(Leitura):
    # mesmo contrato, mas campo desconhecido agora e erro
    model_config = ConfigDict(extra="forbid")


# ---------- respostas padrao (nunca dizem o motivo exato da recusa) ----------

def nao_autorizado():
    return JSONResponse(status_code=401, content={"erro": "nao autorizado"})


def muitas_requisicoes(espera):
    return JSONResponse(status_code=429, content={"erro": "muitas requisicoes, tente mais tarde"},
                        headers={"Retry-After": str(espera)})


def invalida(detalhes):
    return JSONResponse(status_code=422, content={"erro": "leitura invalida", "detalhes": detalhes})


def ip_do_cliente(request):
    return request.client.host if request.client else "desconhecido"


def checar_limite_ip(request):
    ok, espera = limite_ip.permitir(ip_do_cliente(request))
    if not ok:
        seguranca.auditar("RATE_LIMIT_IP", ip_do_cliente(request), detalhe="espera " + str(espera) + "s")
        return muitas_requisicoes(espera)
    return None


def checar_chave_api(request):
    if not seguranca.chave_api_valida(request.headers.get("x-api-key", ""), API_KEY):
        seguranca.auditar("AUTH_FALHOU_API_KEY", ip_do_cliente(request), detalhe=request.url.path)
        return nao_autorizado()
    return None


# ---------- endpoints ----------

@app.get("/")
def raiz():
    return {"status": "ok", "api": "Heimdall - versao segura"}


@app.post("/leituras", status_code=201)
async def receber_leitura(request: Request):
    ip = ip_do_cliente(request)

    # 1) limite por IP antes de tudo (corta forca bruta e flood sem credencial)
    bloqueio = checar_limite_ip(request)
    if bloqueio:
        return bloqueio

    # 2) tamanho do payload (pelo cabecalho e pelo corpo de verdade)
    tamanho_declarado = request.headers.get("content-length", "0")
    if tamanho_declarado.isdigit() and int(tamanho_declarado) > TAMANHO_MAX:
        seguranca.auditar("PAYLOAD_GRANDE", ip, detalhe=tamanho_declarado + " bytes")
        return invalida([{"campo": "corpo da requisicao", "problema": "maior que " + str(TAMANHO_MAX) + " bytes"}])
    corpo = await request.body()
    if len(corpo) > TAMANHO_MAX:
        seguranca.auditar("PAYLOAD_GRANDE", ip, detalhe=str(len(corpo)) + " bytes")
        return invalida([{"campo": "corpo da requisicao", "problema": "maior que " + str(TAMANHO_MAX) + " bytes"}])

    # 3) X-API-Key + assinatura HMAC do dispositivo + anti-replay
    if not seguranca.chave_api_valida(request.headers.get("x-api-key", ""), API_KEY):
        seguranca.auditar("AUTH_FALHOU", ip, request.headers.get("x-device-id", ""), "X-API-Key ausente ou errada")
        return nao_autorizado()
    ok, dispositivo, motivo = seguranca.verificar_assinatura(request.headers, corpo, CHAVES, TOLERANCIA_S, anti_replay)
    if not ok:
        evento = "REPLAY_BLOQUEADO" if "replay" in motivo else "AUTH_FALHOU"
        seguranca.auditar(evento, ip, dispositivo, motivo)
        return nao_autorizado()

    # 4) limite por dispositivo (um ESP32 com defeito nao derruba a API)
    permitido, espera = limite_dispositivo.permitir(dispositivo)
    if not permitido:
        seguranca.auditar("RATE_LIMIT_DISPOSITIVO", ip, dispositivo, "espera " + str(espera) + "s")
        return muitas_requisicoes(espera)

    # 5) schema estrito
    try:
        leitura = LeituraSegura.model_validate_json(corpo)
    except ValidationError as erro:
        detalhes = []
        for item in erro.errors():
            caminho = [str(parte) for parte in item.get("loc", [])]
            detalhes.append({"campo": ".".join(caminho) if caminho else "corpo da requisicao",
                             "problema": "campo nao permitido" if item.get("type") == "extra_forbidden" else traduzir_erro(item)})
        seguranca.auditar("SCHEMA_INVALIDO", ip, dispositivo, json.dumps(detalhes, ensure_ascii=True)[:300])
        return invalida(detalhes)

    enviado = leitura.model_dump()

    # o sensor so pode falar por ele mesmo
    if enviado["id_sensor"] != dispositivo:
        seguranca.auditar("SENSOR_TROCADO", ip, dispositivo, "corpo dizia " + enviado["id_sensor"])
        return nao_autorizado()

    # 6) variacao fisicamente impossivel
    problema = plausibilidade.avaliar(dispositivo, enviado["temperatura"], enviado["umidade"])
    if problema:
        seguranca.auditar("LEITURA_IMPLAUSIVEL", ip, dispositivo, problema)
        return invalida([{"campo": "temperatura/umidade", "problema": "variacao fisicamente implausivel: " + problema}])

    # 7) CSV injection: neutraliza texto que viraria formula
    for campo in ("fazenda", "cultivo"):
        limpo, mudou = seguranca.neutralizar_csv(enviado[campo])
        if mudou:
            seguranca.auditar("CSV_INJECTION_NEUTRALIZADA", ip, dispositivo, campo)
            enviado[campo] = limpo

    registro, avisos = regras.classificar_leitura(enviado)
    divergencia = regras.houve_divergencia(enviado, registro)
    try:
        armazenamento.gravar_leitura(registro, divergencia)
    except armazenamento.ArquivoBloqueado:
        return JSONResponse(status_code=503, content={"erro": "arquivo de dados indisponivel"})
    except OSError:
        seguranca.auditar("ERRO_GRAVACAO", ip, dispositivo)
        return JSONResponse(status_code=500, content={"erro": "falha ao gravar a leitura"})

    seguranca.auditar("LEITURA_ACEITA", ip, dispositivo, registro["motivo"])
    resposta = {"mensagem": "leitura registrada", "leitura": registro,
                "alertas": regras.montar_alertas(registro), "divergencia_dispositivo": divergencia}
    if avisos:
        resposta["avisos"] = avisos
    return resposta


@app.get("/leituras")
def listar_leituras(request: Request, id_sensor: Optional[str] = None,
                    limite: Optional[int] = Query(default=None, ge=1, le=1000)):
    bloqueio = checar_limite_ip(request) or checar_chave_api(request)
    if bloqueio:
        return bloqueio
    try:
        leituras, ignoradas = armazenamento.ler_leituras()
    except armazenamento.ArquivoBloqueado:
        return JSONResponse(status_code=503, content={"erro": "arquivo de dados indisponivel"})
    if id_sensor:
        leituras = [l for l in leituras if l["id_sensor"] == id_sensor]
    if limite:
        leituras = leituras[-limite:]
    return {"total": len(leituras), "linhas_ignoradas": ignoradas, "leituras": leituras}


@app.get("/indicadores")
def obter_indicadores(request: Request):
    bloqueio = checar_limite_ip(request) or checar_chave_api(request)
    if bloqueio:
        return bloqueio
    try:
        leituras, ignoradas = armazenamento.ler_leituras()
    except armazenamento.ArquivoBloqueado:
        return JSONResponse(status_code=503, content={"erro": "arquivo de dados indisponivel"})
    resultado = indicadores.calcular_indicadores(leituras)
    resultado["linhas_ignoradas"] = ignoradas
    return resultado


@app.get("/sensores/status")
def status_sensores(request: Request):
    # perda de visibilidade: sensor cadastrado que parou de mandar leitura
    bloqueio = checar_limite_ip(request) or checar_chave_api(request)
    if bloqueio:
        return bloqueio
    try:
        leituras, _ = armazenamento.ler_leituras()
    except armazenamento.ArquivoBloqueado:
        return JSONResponse(status_code=503, content={"erro": "arquivo de dados indisponivel"})

    ultima = {}
    for leitura in leituras:
        ultima[leitura["id_sensor"]] = leitura["data_recebimento"]

    agora = datetime.now()
    sensores = []
    sem_leitura = 0
    for dispositivo in sorted(CHAVES.keys()):
        if dispositivo not in ultima:
            sensores.append({"id_sensor": dispositivo, "status": "SEM_LEITURA", "ultima_leitura": None})
            sem_leitura += 1
            continue
        quando = datetime.strptime(ultima[dispositivo], config.FORMATO_DATA)
        minutos = round((agora - quando).total_seconds() / 60, 1)
        if minutos > SENSOR_TIMEOUT_MIN:
            status = "SEM_LEITURA"
            sem_leitura += 1
        else:
            status = "ONLINE"
        sensores.append({"id_sensor": dispositivo, "status": status,
                         "ultima_leitura": ultima[dispositivo], "minutos_sem_dados": minutos})

    return {"limite_minutos": SENSOR_TIMEOUT_MIN, "sensores_sem_leitura": sem_leitura, "sensores": sensores}
