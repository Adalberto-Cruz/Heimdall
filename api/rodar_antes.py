# rodar_antes.py
# Sobe a versao SEM protecao (app.py) na porta 8000, gravando em dados_antes/
# (pasta separada pra os ataques nao sujarem os dados oficiais em dados/)
import os

os.environ["DATA_DIR"] = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dados_antes")

import uvicorn  # noqa: E402

if __name__ == "__main__":
    print("ANTES (sem protecao) em http://localhost:8000 - dados em dados_antes/")
    uvicorn.run("app:app", host="127.0.0.1", port=8000)
