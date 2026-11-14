# regras.py
# Funcoes que decidem o que cada leitura significa: status, risco, bomba e motivo.
# A API recalcula tudo aqui e nao confia na decisao que vem do ESP32.

from datetime import datetime

import config


def hora_em_minutos(texto_hora):
    # "21:30" -> 1290 (minutos desde a meia-noite)
    horas, minutos = texto_hora.split(":")
    return int(horas) * 60 + int(minutos)


def minutos_da_leitura(data_hora):
    # pega so a hora da data_hora da leitura
    momento = datetime.strptime(data_hora, config.FORMATO_DATA)
    return momento.hour * 60 + momento.minute


def dentro_do_intervalo(minuto, inicio, fim):
    # inicio entra, fim nao entra: [inicio, fim)
    ini = hora_em_minutos(inicio)
    fi = hora_em_minutos(fim)
    if ini <= fi:
        return ini <= minuto < fi
    # intervalo que passa da meia-noite (ex: 21:30 ate 06:00)
    return minuto >= ini or minuto < fi


def esta_na_ponta(data_hora):
    return dentro_do_intervalo(minutos_da_leitura(data_hora), config.PONTA_INICIO, config.PONTA_FIM)


def esta_na_janela(data_hora):
    return dentro_do_intervalo(minutos_da_leitura(data_hora), config.JANELA_INICIO, config.JANELA_FIM)


def obter_limiar(cultivo):
    # devolve o limite do cultivo e um aviso se o cultivo nao estiver cadastrado
    if cultivo in config.LIMIARES_POR_CULTIVO:
        return config.LIMIARES_POR_CULTIVO[cultivo], None
    return config.LIMIAR_PADRAO, "cultivo sem limiar proprio, usando o padrao"


def classificar_status(leitura, limiar):
    status = {}
    if leitura["umidade"] < limiar["alerta"]:
        status["status_umidade"] = "ALERTA"
    else:
        status["status_umidade"] = "OK"

    if leitura["temperatura"] > config.TEMP_ALERTA:
        status["status_temperatura"] = "ALERTA"
    else:
        status["status_temperatura"] = "OK"

    if leitura["nivel_reservatorio"] < config.RESERVATORIO_MIN:
        status["status_reservatorio"] = "ALERTA"
    else:
        status["status_reservatorio"] = "OK"
    return status


def classificar_risco(leitura, limiar):
    # risco de perder o lote (planta no campo ou alimento ja colhido)
    if leitura["temperatura"] > config.TEMP_ALERTA:
        return "ALTO"
    elif leitura["temperatura"] > config.TEMP_ATENCAO or leitura["umidade"] < limiar["critica"]:
        return "MEDIO"
    else:
        return "BAIXO"


def decidir_bomba(leitura, limiar, na_janela):
    precisa_irrigar = leitura["umidade"] < limiar["alerta"]
    reservatorio_ok = leitura["nivel_reservatorio"] >= config.RESERVATORIO_MIN
    emergencia = leitura["umidade"] < limiar["critica"]
    # a trava do reservatorio sempre ganha, a emergencia deixa irrigar fora da janela
    return precisa_irrigar and reservatorio_ok and (na_janela or emergencia)


def decidir_motivo(leitura, limiar, na_janela):
    # so um motivo por leitura, na ordem de prioridade
    if leitura["nivel_reservatorio"] < config.RESERVATORIO_MIN:
        return "BLOQUEIO_RESERVATORIO_BAIXO"
    elif leitura["temperatura"] > config.TEMP_ALERTA:
        return "ALERTA_CALOR_EXTREMO"
    elif leitura["umidade"] < limiar["critica"] and not na_janela:
        return "IRRIGACAO_EMERGENCIAL_SOLO_CRITICO"
    elif leitura["umidade"] < limiar["alerta"] and na_janela:
        return "SOLO_SECO_JANELA_DESCONTO"
    elif leitura["umidade"] < limiar["alerta"]:
        return "AGUARDANDO_JANELA_DESCONTO"
    else:
        return "CONDICOES_ESTAVEIS"


def montar_alertas(registro):
    # frases simples pra quem ler a resposta da API
    alertas = []
    textos = {
        "status_umidade": "solo seco",
        "status_temperatura": "temperatura acima de 35 C, risco de perder o lote",
        "status_reservatorio": "reservatorio abaixo de 20%, bomba travada",
    }
    for campo, texto in textos.items():
        if registro[campo] == "ALERTA":
            alertas.append(texto)
    if registro["motivo"] == "AGUARDANDO_JANELA_DESCONTO":
        alertas.append("irrigacao adiada para a janela de desconto")
    if registro["motivo"] == "IRRIGACAO_EMERGENCIAL_SOLO_CRITICO":
        alertas.append("solo critico, irrigando fora da janela para salvar a planta")
    return alertas


def classificar_leitura(leitura):
    # recebe as medicoes e devolve o registro completo no formato do contrato
    limiar, aviso = obter_limiar(leitura["cultivo"])
    na_janela = esta_na_janela(leitura["data_hora"])

    registro = {
        "id_sensor": leitura["id_sensor"],
        "fazenda": leitura["fazenda"],
        "cultivo": leitura["cultivo"],
        "umidade": leitura["umidade"],
        "temperatura": leitura["temperatura"],
        "umidade_ar": leitura["umidade_ar"],
        "nivel_reservatorio": leitura["nivel_reservatorio"],
    }
    registro.update(classificar_status(leitura, limiar))
    registro["bomba"] = decidir_bomba(leitura, limiar, na_janela)
    registro["risco_perda_lote"] = classificar_risco(leitura, limiar)
    registro["motivo"] = decidir_motivo(leitura, limiar, na_janela)
    registro["data_hora"] = leitura["data_hora"]

    avisos = []
    if aviso:
        avisos.append(aviso)
    return registro, avisos


def houve_divergencia(enviado, calculado):
    # compara so os campos de decisao que o ESP32 mandou (se mandou)
    campos = ["status_umidade", "status_temperatura", "status_reservatorio",
              "bomba", "risco_perda_lote", "motivo"]
    for campo in campos:
        valor = enviado.get(campo)
        if valor is not None and valor != calculado[campo]:
            return True
    return False
