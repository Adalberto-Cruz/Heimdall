# seguranca.py
# Pecas de seguranca usadas pela app_seguro.py:
# leitura do .env, assinatura HMAC, anti-replay, limite de requisicoes,
# limpeza contra CSV injection, checagem de variacao impossivel e log de auditoria.

import hashlib
import hmac
import json
import os
import threading
import time
from collections import deque
from datetime import datetime

import config

ARQUIVO_ENV = os.path.join(config.PASTA_BASE, ".env")
ARQUIVO_AUDITORIA = os.path.join(config.DATA_DIR, "auditoria_seguranca.log")


# ---------------- configuracao (.env) ----------------

class ConfigFaltando(Exception):
    pass


def carregar_env(caminho=ARQUIVO_ENV):
    # le o .env na mao (CHAVE=valor por linha), sem segredo no codigo
    if not os.path.exists(caminho):
        raise ConfigFaltando("arquivo .env nao encontrado. Rode: python gerar_env.py")
    valores = {}
    with open(caminho, "r", encoding="utf-8") as arq:
        for linha in arq:
            linha = linha.strip()
            if linha == "" or linha.startswith("#") or "=" not in linha:
                continue
            chave, valor = linha.split("=", 1)
            valores[chave.strip()] = valor.strip().strip('"')
    # variavel de ambiente de verdade ganha do arquivo
    for chave in list(valores.keys()):
        if chave in os.environ:
            valores[chave] = os.environ[chave]

    obrigatorias = ["API_KEY", "CHAVES_DISPOSITIVOS"]
    for chave in obrigatorias:
        if not valores.get(chave):
            raise ConfigFaltando("faltou " + chave + " no .env. Rode: python gerar_env.py")
    return valores


def ler_chaves_dispositivos(texto):
    # "S01:abc,S02:def" -> {"S01": "abc", "S02": "def"}
    chaves = {}
    for par in texto.split(","):
        if ":" in par:
            dispositivo, segredo = par.split(":", 1)
            if dispositivo.strip() and segredo.strip():
                chaves[dispositivo.strip()] = segredo.strip()
    if len(chaves) == 0:
        raise ConfigFaltando("CHAVES_DISPOSITIVOS vazio ou mal formatado")
    return chaves


# ---------------- assinatura HMAC + anti-replay ----------------

def calcular_assinatura(segredo, timestamp, corpo_bytes):
    # mensagem assinada = "timestamp." + corpo cru da requisicao
    mensagem = (str(timestamp) + ".").encode("utf-8") + corpo_bytes
    return hmac.new(segredo.encode("utf-8"), mensagem, hashlib.sha256).hexdigest()


class AntiReplay:
    # guarda as assinaturas ja usadas dentro da janela de tempo
    def __init__(self, janela_s):
        self.janela_s = janela_s
        self.vistas = {}
        self.trava = threading.Lock()

    def ja_usada(self, assinatura):
        agora = time.time()
        with self.trava:
            # limpa as velhas pra memoria nao crescer pra sempre
            for velha in [a for a, venc in self.vistas.items() if venc < agora]:
                del self.vistas[velha]
            if assinatura in self.vistas:
                return True
            self.vistas[assinatura] = agora + 2 * self.janela_s
            return False


def verificar_assinatura(cabecalhos, corpo_bytes, chaves, tolerancia_s, anti_replay):
    # devolve (ok, dispositivo, motivo) - o motivo vai so pro log, nunca pra resposta
    dispositivo = cabecalhos.get("x-device-id", "")
    timestamp = cabecalhos.get("x-timestamp", "")
    assinatura = cabecalhos.get("x-signature", "")

    if not dispositivo or not timestamp or not assinatura:
        return False, dispositivo, "cabecalho de assinatura ausente"
    if dispositivo not in chaves:
        return False, dispositivo, "dispositivo desconhecido"
    try:
        ts = int(timestamp)
    except ValueError:
        return False, dispositivo, "timestamp invalido"
    if abs(time.time() - ts) > tolerancia_s:
        return False, dispositivo, "timestamp fora da janela (possivel replay)"

    esperada = calcular_assinatura(chaves[dispositivo], ts, corpo_bytes)
    # compare_digest evita ataque de tempo na comparacao
    if not hmac.compare_digest(esperada, assinatura.lower()):
        return False, dispositivo, "assinatura nao confere"
    if anti_replay.ja_usada(assinatura.lower()):
        return False, dispositivo, "assinatura repetida (replay)"
    return True, dispositivo, "ok"


def chave_api_valida(recebida, esperada):
    if not recebida:
        return False
    return hmac.compare_digest(recebida, esperada)


# ---------------- limite de requisicoes ----------------

class LimitadorRequisicoes:
    # janela deslizante: no maximo N pedidos por chave em 60 segundos
    def __init__(self, limite_por_minuto):
        self.limite = limite_por_minuto
        self.historico = {}
        self.trava = threading.Lock()

    def permitir(self, chave):
        agora = time.time()
        with self.trava:
            fila = self.historico.setdefault(chave, deque())
            while fila and fila[0] < agora - 60:
                fila.popleft()
            if len(fila) >= self.limite:
                espera = int(60 - (agora - fila[0])) + 1
                return False, espera
            fila.append(agora)
            return True, 0


# ---------------- CSV injection ----------------

CARACTERES_PERIGOSOS = ("=", "+", "-", "@", "\t", "\r")


def neutralizar_csv(texto):
    # celula que comeca com = + - @ vira formula no Excel; o apostrofo faz ela virar texto
    if texto.startswith(CARACTERES_PERIGOSOS):
        return "'" + texto, True
    return texto, False


# ---------------- plausibilidade fisica ----------------

class ChecagemPlausibilidade:
    # temperatura e umidade nao pulam muito em poucos minutos;
    # um salto assim e sensor quebrado ou leitura forjada
    def __init__(self, delta_temp, delta_umid, janela_s):
        self.delta_temp = delta_temp
        self.delta_umid = delta_umid
        self.janela_s = janela_s
        self.ultimas = {}
        self.trava = threading.Lock()

    def avaliar(self, dispositivo, temperatura, umidade):
        agora = time.time()
        with self.trava:
            anterior = self.ultimas.get(dispositivo)
            problema = None
            if anterior and agora - anterior["quando"] <= self.janela_s:
                salto_temp = abs(temperatura - anterior["temperatura"])
                salto_umid = abs(umidade - anterior["umidade"])
                if salto_temp > self.delta_temp:
                    problema = "temperatura variou " + str(round(salto_temp, 1)) + " C em menos de " + str(self.janela_s // 60) + " min"
                elif salto_umid > self.delta_umid:
                    problema = "umidade variou " + str(round(salto_umid, 1)) + " pontos em menos de " + str(self.janela_s // 60) + " min"
            if problema is None:
                # so guarda como referencia o que foi aceito
                self.ultimas[dispositivo] = {"temperatura": temperatura, "umidade": umidade, "quando": agora}
            return problema


# ---------------- auditoria ----------------

trava_log = threading.Lock()


def auditar(evento, ip, dispositivo="", detalhe=""):
    # uma linha JSON por evento; nunca grava segredo nem assinatura
    registro = {
        "quando": datetime.now().strftime(config.FORMATO_DATA),
        "evento": evento,
        "ip": ip,
        "dispositivo": dispositivo,
        "detalhe": detalhe,
    }
    try:
        os.makedirs(config.DATA_DIR, exist_ok=True)
        with trava_log:
            with open(ARQUIVO_AUDITORIA, "a", encoding="utf-8") as arq:
                arq.write(json.dumps(registro, ensure_ascii=True) + "\n")
    except OSError:
        # se o log falhar a API continua, mas avisa no terminal
        print("AVISO: nao consegui gravar o log de auditoria")
