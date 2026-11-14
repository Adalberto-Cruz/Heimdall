# indicadores.py
# Percorre o historico e calcula os indicadores do GET /indicadores.

import config
import regras


def calcular_economia(fracao_na_janela):
    # Economia = E x T x [1 - (1 - r) x (1 - f x d)]
    e = config.ENERGIA_MES_KWH
    t = config.TARIFA_KWH
    r = config.REDUCAO_SENSORES
    d = config.DESCONTO_TARIFA
    f = fracao_na_janela
    conta_sem_sistema = e * t
    conta_com_sistema = e * t * (1 - r) * (1 - f * d)
    return {
        "conta_mensal_sem_sistema_reais": round(conta_sem_sistema, 2),
        "conta_mensal_com_sistema_reais": round(conta_com_sistema, 2),
        "economia_estimada_reais": round(conta_sem_sistema - conta_com_sistema, 2),
        "parametros": {
            "E_kwh_mes": e,
            "T_reais_kwh": t,
            "r_reducao_sensores": r,
            "f_bombeamento_na_janela": round(f, 3),
            "d_desconto_tarifa": d,
        },
    }


def decidir_acao(indice):
    if indice >= config.INDICE_VENDA_RAPIDA:
        return "VENDA_RAPIDA_PAA"
    elif indice >= config.INDICE_MONITORAR:
        return "MONITORAR"
    else:
        return "NORMAL"


def risco_por_fazenda(leituras):
    # junta as leituras de cada fazenda num dicionario
    grupos = {}
    for leitura in leituras:
        fazenda = leitura["fazenda"]
        if fazenda not in grupos:
            grupos[fazenda] = {"total": 0, "pontos": 0.0, "ALTO": 0, "MEDIO": 0, "BAIXO": 0}
        grupo = grupos[fazenda]
        risco = leitura["risco_perda_lote"]
        grupo["total"] += 1
        grupo["pontos"] += config.PESO_RISCO.get(risco, 0.0)
        if risco in grupo:
            grupo[risco] += 1

    resultado = []
    for fazenda, grupo in grupos.items():
        indice = grupo["pontos"] / grupo["total"]
        resultado.append({
            "fazenda": fazenda,
            "leituras": grupo["total"],
            "risco_alto": grupo["ALTO"],
            "risco_medio": grupo["MEDIO"],
            "indice_risco_perda_safra": round(indice, 3),
            "acao_recomendada": decidir_acao(indice),
        })
    # quem tem mais risco aparece primeiro (prioridade pra venda rapida/PAA)
    resultado.sort(key=lambda item: item["indice_risco_perda_safra"], reverse=True)
    return resultado


def calcular_indicadores(leituras):
    if len(leituras) == 0:
        return {
            "mensagem": "sem leituras registradas",
            "total_leituras": 0,
            "media_umidade_solo": 0.0,
            "temperatura_maxima": None,
            "total_alertas_criticos": 0,
            "taxa_acionamento_bomba_pct": 0.0,
            "pct_bombeamento_na_janela": 0.0,
            "economia": calcular_economia(0.0),
            "risco_por_fazenda": [],
        }

    soma_umidade = 0.0
    maior = None
    alertas_criticos = 0
    bomba_ligada = 0
    bomba_na_janela = 0
    contagem_motivos = {}

    for leitura in leituras:
        soma_umidade += leitura["umidade"]
        if maior is None or leitura["temperatura"] > maior["temperatura"]:
            maior = leitura
        if leitura["motivo"] in config.MOTIVOS_CRITICOS:
            alertas_criticos += 1
        if leitura["bomba"]:
            bomba_ligada += 1
            if regras.esta_na_janela(leitura["data_hora"]):
                bomba_na_janela += 1
        contagem_motivos[leitura["motivo"]] = contagem_motivos.get(leitura["motivo"], 0) + 1

    total = len(leituras)
    if bomba_ligada > 0:
        fracao_janela = bomba_na_janela / bomba_ligada
    else:
        fracao_janela = 0.0

    return {
        "total_leituras": total,
        "media_umidade_solo": round(soma_umidade / total, 2),
        "temperatura_maxima": {
            "valor": maior["temperatura"],
            "id_sensor": maior["id_sensor"],
            "fazenda": maior["fazenda"],
            "data_hora": maior["data_hora"],
        },
        "total_alertas_criticos": alertas_criticos,
        "taxa_acionamento_bomba_pct": round(bomba_ligada / total * 100, 2),
        "pct_bombeamento_na_janela": round(fracao_janela * 100, 2),
        "leituras_por_motivo": contagem_motivos,
        "economia": calcular_economia(fracao_janela),
        "risco_por_fazenda": risco_por_fazenda(leituras),
    }
