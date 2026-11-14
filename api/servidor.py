# servidor.py
# Sobe a API em um dos dois modos usados na validacao de seguranca:
#
#   python servidor.py --modo vulneravel   -> app.py (sem protecao), porta 8000, dados em dados_vulneravel/
#   python servidor.py --modo seguro       -> app_seguro.py (blindada), porta 8001, dados em dados_seguro/
#
# Cada modo grava numa pasta propria, entao os ataques nao sujam os dados oficiais em dados/.

import argparse
import os
import sys

PASTA = os.path.dirname(os.path.abspath(__file__))

MODOS = {
    "vulneravel": {"modulo": "app:app", "porta": 8000, "pasta": "dados_vulneravel"},
    "seguro": {"modulo": "app_seguro:app", "porta": 8001, "pasta": "dados_seguro"},
}


def main():
    parser = argparse.ArgumentParser(description="Sobe a API Heimdall no modo escolhido")
    parser.add_argument("--modo", required=True, choices=MODOS.keys(), help="vulneravel ou seguro")
    args = parser.parse_args()
    modo = MODOS[args.modo]

    # a pasta de dados tem que ser definida antes de importar a API
    os.environ["DATA_DIR"] = os.path.join(PASTA, modo["pasta"])

    if args.modo == "seguro":
        import seguranca
        try:
            seguranca.carregar_env()
        except seguranca.ConfigFaltando as erro:
            print("Nao da pra subir o modo seguro: " + str(erro))
            sys.exit(1)

    import uvicorn
    print("Modo " + args.modo + " em http://127.0.0.1:" + str(modo["porta"]) + " - dados em " + modo["pasta"] + "/")
    uvicorn.run(modo["modulo"], host="127.0.0.1", port=modo["porta"])


if __name__ == "__main__":
    main()
