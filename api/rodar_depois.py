# rodar_depois.py
# Sobe a versao BLINDADA (app_seguro.py) na porta 8001, gravando em dados_depois/
import os
import sys

os.environ["DATA_DIR"] = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dados_depois")

import uvicorn  # noqa: E402

import seguranca  # noqa: E402

if __name__ == "__main__":
    try:
        seguranca.carregar_env()
    except seguranca.ConfigFaltando as erro:
        print("Nao da pra subir a versao segura: " + str(erro))
        sys.exit(1)
    print("DEPOIS (blindada) em http://localhost:8001 - dados em dados_depois/")
    uvicorn.run("app_seguro:app", host="127.0.0.1", port=8001)
