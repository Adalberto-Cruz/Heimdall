# gerar_dados.py
# Manda 50 leituras variadas pra API. O leituras_sensores.jsonl que sai daqui
# e o arquivo oficial que vai pro Databricks e pra AWS.
#
# Uso (com a API rodando em outro terminal):
#   python gerar_dados.py
#   python gerar_dados.py --url http://localhost:8000 --forcar

import argparse
import random
import sys
from datetime import datetime, timedelta

import requests

import config
import regras

TOTAL_LEITURAS = 50

# cada sensor fica numa fazenda e num cultivo fixos
SENSORES = {
    "S01": {"fazenda": "Sitio Boa Esperanca", "cultivo": "Tomate"},
    "S02": {"fazenda": "Sitio Boa Esperanca", "cultivo": "Tomate"},
    "S03": {"fazenda": "Cooperativa Vale Verde", "cultivo": "Soja"},
    "S04": {"fazenda": "Cooperativa Vale Verde", "cultivo": "Tomate"},
    "S05": {"fazenda": "Fazenda Boa Safra", "cultivo": "Soja"},
}

# que tipo de situacao gerar em cada faixa do dia (gira em ciclo)
CICLO_JANELA = ["SOLO_SECO_JANELA_DESCONTO", "CONDICOES_ESTAVEIS", "SOLO_SECO_JANELA_DESCONTO",
                "BLOQUEIO_RESERVATORIO_BAIXO", "CONDICOES_ESTAVEIS"]
CICLO_TARDE = ["ALERTA_CALOR_EXTREMO", "AGUARDANDO_JANELA_DESCONTO", "ALERTA_CALOR_EXTREMO",
               "IRRIGACAO_EMERGENCIAL_SOLO_CRITICO"]

# o calor forte fica concentrado no galpao da Fazenda Boa Safra,
# pra mostrar um lote que precisa ir pra venda rapida/PAA
SENSOR_DO_CALOR = "S05"
CICLO_RESTO = ["AGUARDANDO_JANELA_DESCONTO", "CONDICOES_ESTAVEIS", "IRRIGACAO_EMERGENCIAL_SOLO_CRITICO",
               "BLOQUEIO_RESERVATORIO_BAIXO", "CONDICOES_ESTAVEIS"]


def sortear(minimo, maximo):
    return round(random.uniform(minimo, maximo), 1)


def montar_medicoes(cenario, cultivo):
    # escolhe valores que caem no cenario pedido, respeitando o limite do cultivo
    limiar = config.LIMIARES_POR_CULTIVO.get(cultivo, config.LIMIAR_PADRAO)
    alerta = limiar["alerta"]
    critica = limiar["critica"]

    umidade = sortear(alerta + 5, alerta + 30)
    temperatura = sortear(20, 29)
    nivel = sortear(30, 95)

    if cenario in ("SOLO_SECO_JANELA_DESCONTO", "AGUARDANDO_JANELA_DESCONTO"):
        umidade = sortear(critica + 1, alerta - 1)
        temperatura = sortear(22, 33)
    elif cenario == "IRRIGACAO_EMERGENCIAL_SOLO_CRITICO":
        umidade = sortear(8, critica - 1)
        temperatura = sortear(24, 34)
    elif cenario == "BLOQUEIO_RESERVATORIO_BAIXO":
        nivel = sortear(3, 19)
        umidade = sortear(15, 50)
    elif cenario == "ALERTA_CALOR_EXTREMO":
        temperatura = sortear(35.5, 41)
        umidade = sortear(critica, alerta + 20)

    return {
        "umidade": umidade,
        "temperatura": temperatura,
        "umidade_ar": sortear(25, 80),
        "nivel_reservatorio": nivel,
    }


def montar_massa():
    random.seed(42)  # sempre a mesma massa
    inicio = datetime(2026, 11, 12, 6, 0, 0)
    leituras = []
    posicoes = {"janela": 0, "tarde": 0, "resto": 0}

    for i in range(TOTAL_LEITURAS):
        momento = inicio + timedelta(minutes=30 * i)
        data_hora = momento.strftime(config.FORMATO_DATA)

        # escolhe o cenario conforme a hora
        if regras.esta_na_janela(data_hora):
            faixa, ciclo = "janela", CICLO_JANELA
        elif 11 <= momento.hour < 17:
            faixa, ciclo = "tarde", CICLO_TARDE
        else:
            faixa, ciclo = "resto", CICLO_RESTO
        cenario = ciclo[posicoes[faixa] % len(ciclo)]
        posicoes[faixa] += 1

        if cenario == "ALERTA_CALOR_EXTREMO":
            id_sensor = SENSOR_DO_CALOR
        else:
            id_sensor = random.choice(list(SENSORES.keys()))
        leitura = {
            "id_sensor": id_sensor,
            "fazenda": SENSORES[id_sensor]["fazenda"],
            "cultivo": SENSORES[id_sensor]["cultivo"],
        }
        leitura.update(montar_medicoes(cenario, leitura["cultivo"]))
        leitura["data_hora"] = data_hora
        leituras.append((cenario, leitura))
    return leituras


def main():
    parser = argparse.ArgumentParser(description="Envia 50 leituras de teste para a API")
    parser.add_argument("--url", default="http://localhost:8000", help="endereco da API")
    parser.add_argument("--forcar", action="store_true", help="envia mesmo se ja tiver leituras gravadas")
    args = parser.parse_args()
    url = args.url.rstrip("/")

    # confere se a API ta no ar antes de comecar
    try:
        resposta = requests.get(url + "/leituras", timeout=5)
        resposta.raise_for_status()
    except requests.exceptions.ConnectionError:
        print("API fora do ar em " + url)
        print("Abra outro terminal e rode: uvicorn app:app --host 0.0.0.0 --port 8000")
        sys.exit(1)
    except requests.exceptions.RequestException as erro:
        print("A API respondeu com erro: " + str(erro))
        sys.exit(1)

    ja_gravadas = resposta.json().get("total", 0)
    if ja_gravadas > 0 and not args.forcar:
        print("Ja existem " + str(ja_gravadas) + " leituras gravadas.")
        print("Pra gerar a massa oficial limpa: pare a API, apague a pasta dados/ e rode de novo.")
        print("Se quiser somar mesmo assim, use --forcar.")
        sys.exit(1)

    contagem = {}
    erros = 0
    for cenario, leitura in montar_massa():
        try:
            r = requests.post(url + "/leituras", json=leitura, timeout=5)
        except requests.exceptions.RequestException as erro:
            print("Falha ao enviar: " + str(erro))
            erros += 1
            continue
        if r.status_code != 201:
            print("Recusada (" + str(r.status_code) + "): " + r.text)
            erros += 1
            continue
        motivo = r.json()["leitura"]["motivo"]
        contagem[motivo] = contagem.get(motivo, 0) + 1
        # avisa se a API classificou diferente do que o gerador queria
        if motivo != cenario:
            print("Atencao: esperado " + cenario + ", API deu " + motivo + " em " + leitura["data_hora"])

    print("")
    print("Enviadas com sucesso: " + str(TOTAL_LEITURAS - erros) + " de " + str(TOTAL_LEITURAS))
    print("Leituras por motivo:")
    for motivo in config.MOTIVOS_VALIDOS:
        print("  " + motivo.ljust(36) + str(contagem.get(motivo, 0)))
    print("")
    print("Arquivo para o Databricks/AWS: " + config.ARQUIVO_JSONL)


if __name__ == "__main__":
    main()
