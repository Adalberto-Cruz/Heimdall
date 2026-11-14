# armazenamento.py
# Grava e le as leituras no CSV e no JSONL.

import csv
import json
import os
import threading
from datetime import datetime

import config

# ordem das chaves igual ao contrato JSON (o JSONL sai exatamente assim)
CAMPOS_CONTRATO = [
    "id_sensor", "fazenda", "cultivo", "umidade", "temperatura", "umidade_ar",
    "nivel_reservatorio", "status_umidade", "status_temperatura", "status_reservatorio",
    "bomba", "risco_perda_lote", "motivo", "data_hora",
]
# o CSV leva duas colunas a mais, que nao vao pro JSONL pra nao quebrar o Databricks e a AWS
CAMPOS_CSV = CAMPOS_CONTRATO + ["data_recebimento", "divergencia_dispositivo"]

CAMPOS_NUMERICOS = ["umidade", "temperatura", "umidade_ar", "nivel_reservatorio"]
CAMPOS_BOOLEANOS = ["bomba", "divergencia_dispositivo"]

# evita duas requisicoes escrevendo ao mesmo tempo
trava_escrita = threading.Lock()


class ArquivoBloqueado(Exception):
    # quando o CSV ta aberto no Excel o Windows nao deixa gravar
    pass


def garantir_pasta():
    os.makedirs(config.DATA_DIR, exist_ok=True)


def preparar_csv():
    # cria o CSV com cabecalho, ou guarda um CSV antigo com cabecalho diferente como .bak
    if not os.path.exists(config.ARQUIVO_CSV) or os.path.getsize(config.ARQUIVO_CSV) == 0:
        with open(config.ARQUIVO_CSV, "w", newline="", encoding="utf-8-sig") as arq:
            csv.writer(arq).writerow(CAMPOS_CSV)
        return

    with open(config.ARQUIVO_CSV, "r", newline="", encoding="utf-8-sig") as arq:
        cabecalho = next(csv.reader(arq), [])
    if cabecalho != CAMPOS_CSV:
        carimbo = datetime.now().strftime("%Y%m%d_%H%M%S")
        os.replace(config.ARQUIVO_CSV, config.ARQUIVO_CSV + "." + carimbo + ".bak")
        with open(config.ARQUIVO_CSV, "w", newline="", encoding="utf-8-sig") as arq:
            csv.writer(arq).writerow(CAMPOS_CSV)


def texto_csv(valor):
    # booleano vai como true/false minusculo, igual no JSON
    if isinstance(valor, bool):
        return "true" if valor else "false"
    return valor


def gravar_leitura(registro, divergencia):
    linha_jsonl = {campo: registro[campo] for campo in CAMPOS_CONTRATO}
    linha_csv = dict(linha_jsonl)
    linha_csv["data_recebimento"] = datetime.now().strftime(config.FORMATO_DATA)
    linha_csv["divergencia_dispositivo"] = divergencia

    with trava_escrita:
        try:
            garantir_pasta()
            preparar_csv()
            # primeiro o JSONL, depois o CSV
            with open(config.ARQUIVO_JSONL, "a", encoding="utf-8") as arq:
                arq.write(json.dumps(linha_jsonl, ensure_ascii=True) + "\n")
            with open(config.ARQUIVO_CSV, "a", newline="", encoding="utf-8-sig") as arq:
                escritor = csv.writer(arq)
                escritor.writerow([texto_csv(linha_csv[campo]) for campo in CAMPOS_CSV])
        except PermissionError as erro:
            raise ArquivoBloqueado(str(erro))
    return linha_csv


def converter_linha(linha):
    # o CSV guarda tudo como texto, aqui volta pros tipos certos
    registro = {}
    for campo in CAMPOS_CSV:
        valor = linha.get(campo)
        if valor is None or valor == "":
            raise ValueError("campo vazio: " + campo)
        if campo in CAMPOS_NUMERICOS:
            registro[campo] = float(valor)
        elif campo in CAMPOS_BOOLEANOS:
            if valor not in ("true", "false"):
                raise ValueError("booleano invalido em " + campo)
            registro[campo] = valor == "true"
        else:
            registro[campo] = valor
    return registro


def ler_leituras():
    # devolve (lista de leituras, quantidade de linhas estragadas que foram puladas)
    if not os.path.exists(config.ARQUIVO_CSV):
        return [], 0

    leituras = []
    ignoradas = 0
    try:
        with open(config.ARQUIVO_CSV, "r", newline="", encoding="utf-8-sig") as arq:
            leitor = csv.DictReader(arq)
            if leitor.fieldnames != CAMPOS_CSV:
                # cabecalho errado: nao da pra confiar em nada do arquivo
                return [], 0
            for linha in leitor:
                # linha com coluna a mais ou a menos
                if None in linha or len(linha) != len(CAMPOS_CSV):
                    ignoradas += 1
                    continue
                try:
                    leituras.append(converter_linha(linha))
                except ValueError:
                    ignoradas += 1
    except PermissionError as erro:
        raise ArquivoBloqueado(str(erro))
    return leituras, ignoradas
