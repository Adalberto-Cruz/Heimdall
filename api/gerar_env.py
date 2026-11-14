# gerar_env.py
# Cria o arquivo .env com chaves aleatorias (nunca colocar segredo no codigo).
# Uso: python gerar_env.py            (nao sobrescreve se ja existir)
#      python gerar_env.py --forcar   (gera chaves novas)

import os
import secrets
import sys

import config

CAMINHO = os.path.join(config.PASTA_BASE, ".env")
SENSORES = ["S01", "S02", "S03", "S04", "S05"]


def main():
    if os.path.exists(CAMINHO) and "--forcar" not in sys.argv:
        print(".env ja existe. Use --forcar se quiser gerar chaves novas.")
        print("Atencao: com chaves novas o ESP32 precisa receber a chave nova tambem.")
        return

    chaves = ",".join(s + ":" + secrets.token_hex(16) for s in SENSORES)
    conteudo = [
        "# segredos da app_seguro.py - NAO subir pro GitHub (ja esta no .gitignore)",
        "API_KEY=" + secrets.token_hex(16),
        "CHAVES_DISPOSITIVOS=" + chaves,
        "TOLERANCIA_TIMESTAMP_S=60",
        "TAMANHO_MAX_PAYLOAD=2048",
        "LIMITE_REQ_IP_MIN=60",
        "LIMITE_REQ_DISPOSITIVO_MIN=30",
        "MAX_SALTO_TEMPERATURA=8",
        "MAX_SALTO_UMIDADE=30",
        "JANELA_PLAUSIBILIDADE_S=300",
        "SENSOR_TIMEOUT_MIN=10",
    ]
    with open(CAMINHO, "w", encoding="utf-8") as arq:
        arq.write("\n".join(conteudo) + "\n")
    print(".env criado em " + CAMINHO)
    print("Chave de cada ESP32 esta em CHAVES_DISPOSITIVOS (passar so a do sensor dele pro Gustavo).")


if __name__ == "__main__":
    main()
