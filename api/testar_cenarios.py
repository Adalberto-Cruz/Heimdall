# testar_cenarios.py
# Roda os 3 cenarios de teste pedidos na disciplina de Python.
# Pra cada um mostra: requisicao enviada, resposta da API e a linha gravada no CSV.
# Tirar print da saida de cada cenario pro PDF.
#
# Uso (com a API rodando em outro terminal):
#   python testar_cenarios.py

import argparse
import json
import os
import sys

import requests

import config

CENARIOS = [
    {
        "titulo": "CENARIO 1 - Solo seco na janela de desconto (bomba liga)",
        "leitura": {
            "id_sensor": "S01", "fazenda": "Sitio Boa Esperanca", "cultivo": "Tomate",
            "umidade": 28.4, "temperatura": 26.5, "umidade_ar": 55.0,
            "nivel_reservatorio": 75.0, "data_hora": "2026-11-12 22:15:00",
        },
    },
    {
        "titulo": "CENARIO 2 - Reservatorio baixo (bomba travada contra queima a seco)",
        "leitura": {
            "id_sensor": "S03", "fazenda": "Cooperativa Vale Verde", "cultivo": "Soja",
            "umidade": 22.0, "temperatura": 29.0, "umidade_ar": 48.0,
            "nivel_reservatorio": 12.0, "data_hora": "2026-11-12 22:30:00",
        },
    },
    {
        "titulo": "CENARIO 3 - Leitura invalida (umidade 150%) e recusada, nada e gravado",
        "leitura": {
            "id_sensor": "S05", "fazenda": "Fazenda Boa Safra", "cultivo": "Soja",
            "umidade": 150.0, "temperatura": 31.0, "umidade_ar": 40.0,
            "nivel_reservatorio": 60.0, "data_hora": "2026-11-12 22:45:00",
        },
    },
]


def contar_linhas_csv():
    if not os.path.exists(config.ARQUIVO_CSV):
        return 0
    with open(config.ARQUIVO_CSV, "r", encoding="utf-8-sig") as arq:
        return len(arq.readlines())


def ultima_linha_csv():
    with open(config.ARQUIVO_CSV, "r", encoding="utf-8-sig") as arq:
        linhas = arq.readlines()
    return linhas[0].strip(), linhas[-1].strip()


def mostrar(titulo, conteudo):
    print("-- " + titulo)
    print(conteudo)
    print("")


def main():
    parser = argparse.ArgumentParser(description="Roda os 3 cenarios de teste")
    parser.add_argument("--url", default="http://localhost:8000", help="endereco da API")
    args = parser.parse_args()
    url = args.url.rstrip("/")

    for cenario in CENARIOS:
        print("=" * 70)
        print(cenario["titulo"])
        print("=" * 70)

        linhas_antes = contar_linhas_csv()
        mostrar("Requisicao enviada: POST " + url + "/leituras",
                json.dumps(cenario["leitura"], indent=2, ensure_ascii=False))

        try:
            r = requests.post(url + "/leituras", json=cenario["leitura"], timeout=5)
        except requests.exceptions.ConnectionError:
            print("API fora do ar em " + url + ". Rode: uvicorn app:app --host 0.0.0.0 --port 8000")
            sys.exit(1)

        mostrar("Resposta da API: HTTP " + str(r.status_code),
                json.dumps(r.json(), indent=2, ensure_ascii=False))

        linhas_depois = contar_linhas_csv()
        if linhas_depois > linhas_antes:
            cabecalho, linha = ultima_linha_csv()
            mostrar("Linha gravada em " + os.path.basename(config.ARQUIVO_CSV),
                    cabecalho + "\n" + linha)
        else:
            mostrar("CSV", "nenhuma linha nova gravada (leitura recusada)")


if __name__ == "__main__":
    main()
