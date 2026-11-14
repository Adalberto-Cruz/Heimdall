# simulacao_ia.py
# Mostra as 3 protecoes de IA funcionando (prints para o PDF de Cyber).
# Uso: python simulacao_ia.py

import json
import os
import shutil
import tempfile

from PIL import Image

import config
import ia_seguranca

PASTA = tempfile.mkdtemp(prefix="heimdall_ia_")


def titulo(texto):
    print("")
    print("=" * 70)
    print(texto)
    print("=" * 70)


def foto_com_gps(caminho):
    # simula a foto de celular: folha + modelo do aparelho + GPS da propriedade
    imagem = Image.new("RGB", (224, 224), (60, 140, 60))
    exif = Image.Exif()
    exif[0x010F] = "Celular do produtor"
    exif[0x0132] = "2026:11:12 07:40:00"
    exif[0x8825] = {1: "S", 2: (9.0, 23.0, 30.0), 3: "W", 4: (40.0, 30.0, 10.0)}  # perto de Petrolina-PE
    imagem.save(caminho, exif=exif)


def main():
    # 1) EXIF / GPS
    titulo("1. Foto da folha: remover EXIF e GPS antes da CNN")
    original = os.path.join(PASTA, "folha_original.jpg")
    limpa = os.path.join(PASTA, "folha_limpa.jpg")
    foto_com_gps(original)
    with Image.open(original) as aberta:
        gps = aberta.getexif().get_ifd(0x8825)
    print("Foto original - GPS gravado:", dict(gps))
    resultado = ia_seguranca.remover_metadados(original, limpa)
    print("Antes :", resultado["antes"])
    print("Depois:", resultado["depois"])

    try:
        falso = os.path.join(PASTA, "nao_e_imagem.jpg")
        with open(falso, "w") as arq:
            arq.write("isso nao e uma foto")
        ia_seguranca.remover_metadados(falso, os.path.join(PASTA, "x.jpg"))
    except ia_seguranca.ImagemInvalida as erro:
        print("Arquivo falso com extensao .jpg recusado:", erro)

    # 2) supervisao humana
    titulo("2. Diagnostico da CNN com supervisao humana (limiar 0,75)")
    exemplos = [("Tomato___Late_blight", 0.93), ("Tomato___healthy", 0.88), ("Tomato___Early_blight", 0.61)]
    for classe, confianca in exemplos:
        d = ia_seguranca.decidir_diagnostico(classe, confianca)
        print("{:<24} conf {:.2f} -> {:<16} {}".format(classe, confianca, d["acao"], d["mensagem"]))

    # 3) data poisoning
    titulo("3. Filtro do JSONL antes do treino do ML (contra dados envenenados)")
    entrada = os.path.join(PASTA, "leituras_para_treino.jsonl")
    saida = os.path.join(PASTA, "leituras_limpas.jsonl")
    # procura o arquivo oficial na pasta dados/ da API ou na dados/ da raiz do repositorio
    oficial = config.ARQUIVO_JSONL
    if not os.path.exists(oficial):
        oficial = os.path.join(config.PASTA_BASE, "..", "dados", "leituras_sensores.jsonl")
    linhas = []
    if os.path.exists(oficial):
        with open(oficial, "r", encoding="utf-8") as arq:
            linhas = [l.strip() for l in arq if l.strip()]
    else:
        print("(dados/leituras_sensores.jsonl nao encontrado, usando so as linhas de ataque)")

    base = json.loads(linhas[0]) if linhas else {
        "id_sensor": "S01", "fazenda": "Sitio Boa Esperanca", "cultivo": "Tomate", "umidade": 40.0,
        "temperatura": 25.0, "umidade_ar": 50.0, "nivel_reservatorio": 70.0, "status_umidade": "OK",
        "status_temperatura": "OK", "status_reservatorio": "OK", "bomba": False,
        "risco_perda_lote": "BAIXO", "motivo": "CONDICOES_ESTAVEIS", "data_hora": "2026-11-12 06:00:00"}
    envenenadas = [
        dict(base, umidade=250.0),                      # valor impossivel pra puxar o modelo
        dict(base, fazenda="=cmd|' /C calc'!A0"),       # formula escondida
        dict(base, motivo="LIGAR_BOMBA_SEMPRE"),        # rotulo inventado
        dict(base, extra="campo a mais"),               # fora do contrato
    ]
    with open(entrada, "w", encoding="utf-8") as arq:
        for linha in linhas:
            arq.write(linha + "\n")
        for registro in envenenadas:
            arq.write(json.dumps(registro) + "\n")
        arq.write("{quebrado\n")
    total = len(linhas) + len(envenenadas) + 1
    resumo = ia_seguranca.filtrar_jsonl_para_treino(entrada, saida)
    print("Linhas no arquivo:", total)
    print("Aceitas pro treino:", resumo["aceitas"])
    print("Descartadas:", resumo["descartadas"])
    for motivo, qtd in resumo["motivos"].items():
        print("   -", motivo + ":", qtd)

    shutil.rmtree(PASTA, ignore_errors=True)


if __name__ == "__main__":
    main()
