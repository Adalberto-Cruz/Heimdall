"""
Heimdall - GS 2026.2 - Statistical Computing with R & Python
Preparacao da base: transforma a serie horaria da estacao do CEMADEN em Petrolina
em uma base diaria (cemaden_petrolina_diario.csv), que e a base usada no relatorio.

Fonte: Zeri, M. et al. A soil moisture dataset over the Brazilian semiarid region.
Mendeley Data, v2, 2020. DOI 10.17632/xrk5rfcpvg.2 (licenca CC BY 4.0).
Arquivo usado: PCDs_/PCD_Acqua_PE_261110103C.xlsx (estacao Petrolina 03).

Uso: python preparar_base.py caminho/para/PCD_Acqua_PE_261110103C.xlsx
"""

import sys
import pandas as pd

ARQUIVO_SAIDA = "cemaden_petrolina_diario.csv"
MIN_HORAS = 20          # so aceita o dia se tiver pelo menos 20 das 24 leituras horarias
LIMIAR_ESTRESSE = 7.0   # umidade a 10 cm <= 7% (1o quartil da serie) = dia de estresse hidrico
# falha do sensor de 20 cm: a partir de 11/04/2019 12h ele sobe de 0,13 para 0,26 m3/m3 sem nenhuma chuva
# e fica parado em 0,26, enquanto o sensor de 10 cm continua secando. dai em diante o dado de 20 cm e descartado
INICIO_FALHA_US20 = "2019-04-11 12:00"


def main():
    if len(sys.argv) < 2:
        print("Informe o arquivo da estacao. Ex: python preparar_base.py PCD_Acqua_PE_261110103C.xlsx")
        sys.exit(1)

    caminho = sys.argv[1]
    try:
        bruto = pd.read_excel(caminho, sheet_name="Data")
    except FileNotFoundError:
        print(f"Arquivo nao encontrado: {caminho}")
        sys.exit(1)
    except ValueError:
        print("A planilha nao tem a aba 'Data'. Confira se e o arquivo do CEMADEN.")
        sys.exit(1)

    colunas = {"Time", "Precip", "US10cm", "US20cm"}
    if not colunas.issubset(bruto.columns):
        print(f"Faltam colunas na planilha. Esperado: {sorted(colunas)}")
        sys.exit(1)

    bruto = bruto.set_index("Time").sort_index()

    falha = bruto.index >= INICIO_FALHA_US20
    print(f"US20cm: {(falha & bruto['US20cm'].notna()).sum()} horas descartadas por falha do sensor")
    bruto.loc[falha, "US20cm"] = None

    # agrega por dia: chuva somada, umidade pela media, e conta quantas horas tem dado
    dia = bruto.resample("D").agg({
        "Precip": ["sum", "count"],
        "US10cm": ["mean", "count"],
        "US20cm": ["mean", "count"],
    })
    dia.columns = ["chuva_dia_mm", "n_chuva", "u10", "n_u10", "u20", "n_u20"]

    # dia com chuva incompleta vira vazio, para nao somar chuva pela metade
    chuva_ok = dia["chuva_dia_mm"].where(dia["n_chuva"] >= MIN_HORAS)
    dia["chuva_7d_mm"] = chuva_ok.rolling(7, min_periods=7).sum()
    dia["chuva_30d_mm"] = chuva_ok.rolling(30, min_periods=30).sum()

    completo = (dia["n_chuva"] >= MIN_HORAS) & (dia["n_u10"] >= MIN_HORAS) & (dia["n_u20"] >= MIN_HORAS)
    dia = dia[completo].dropna(subset=["chuva_7d_mm", "chuva_30d_mm"])

    base = pd.DataFrame({
        "data": dia.index.strftime("%Y-%m-%d"),
        "estacao": "261110103C",
        "municipio": "Petrolina/PE",
        # m3/m3 vira % (x100) para ficar mais facil de ler
        "umidade_10cm": (dia["u10"] * 100).round(2).values,
        "umidade_20cm": (dia["u20"] * 100).round(2).values,
        "chuva_dia_mm": dia["chuva_dia_mm"].round(1).values,
        "chuva_7d_mm": dia["chuva_7d_mm"].round(1).values,
        "chuva_30d_mm": dia["chuva_30d_mm"].round(1).values,
    })
    base["estresse_hidrico"] = (base["umidade_10cm"] <= LIMIAR_ESTRESSE).astype(int)

    base.to_csv(ARQUIVO_SAIDA, index=False)
    print(f"Base gerada: {ARQUIVO_SAIDA} com {len(base)} dias ({base['data'].iloc[0]} a {base['data'].iloc[-1]})")
    print(f"Dias de estresse hidrico: {base['estresse_hidrico'].sum()} ({base['estresse_hidrico'].mean():.1%})")


if __name__ == "__main__":
    main()
