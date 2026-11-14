# ia_seguranca.py
# Protecoes para os componentes de IA do Heimdall (disciplina Cognitive Cybersecurity, etapa 5).
#
# 1. remover_metadados: tira EXIF/GPS da foto da folha antes de mandar pra CNN
#    (a foto pode entregar a localizacao exata da propriedade - LGPD, minimizacao de dados)
# 2. decidir_diagnostico: a CNN nao decide sozinha quando a confianca e baixa (supervisao humana)
# 3. filtrar_jsonl_para_treino: so leitura limpa entra no treino do ML (contra data poisoning)

import json
import math
import os

from PIL import Image, UnidentifiedImageError

import config

# ---------------- 1. metadados da foto ----------------

FORMATOS_ACEITOS = ("JPEG", "PNG")
TAMANHO_MAX_BYTES = 10 * 1024 * 1024   # 10 MB
LADO_MAX_PIXELS = 6000                  # evita imagem gigante feita pra travar o servidor
TAG_GPS = 0x8825


class ImagemInvalida(Exception):
    pass


def ler_imagem(caminho):
    # confere tudo antes de abrir de verdade
    if not os.path.exists(caminho):
        raise ImagemInvalida("arquivo nao encontrado: " + caminho)
    tamanho = os.path.getsize(caminho)
    if tamanho == 0:
        raise ImagemInvalida("arquivo vazio")
    if tamanho > TAMANHO_MAX_BYTES:
        raise ImagemInvalida("arquivo maior que 10 MB")
    try:
        with Image.open(caminho) as teste:
            teste.verify()  # detecta arquivo corrompido
        # depois do verify precisa abrir de novo; o "with" fecha o arquivo (no Windows isso importa)
        with Image.open(caminho) as aberta:
            formato = aberta.format
            if formato not in FORMATOS_ACEITOS:
                raise ImagemInvalida("formato nao aceito: " + str(formato))
            if aberta.width > LADO_MAX_PIXELS or aberta.height > LADO_MAX_PIXELS:
                raise ImagemInvalida("imagem grande demais")
            metadados = resumo_metadados(aberta)
            aberta.load()
            imagem = aberta.copy()
    except ImagemInvalida:
        raise
    except (UnidentifiedImageError, OSError, SyntaxError):
        raise ImagemInvalida("arquivo nao e uma imagem valida ou esta corrompido")
    return imagem, formato, metadados


def resumo_metadados(imagem):
    exif = imagem.getexif()
    gps = exif.get_ifd(TAG_GPS) if TAG_GPS in exif else {}
    return {"campos_exif": len(exif), "tem_gps": len(gps) > 0}


def remover_metadados(caminho_entrada, caminho_saida):
    # copia so os pixels pra uma imagem nova: EXIF, GPS, modelo do celular e data ficam pra tras
    imagem, formato, antes = ler_imagem(caminho_entrada)

    modo = "RGB" if imagem.mode not in ("RGB", "L") else imagem.mode
    pixels = imagem.convert(modo)
    limpa = Image.new(modo, pixels.size)
    limpa.paste(pixels)

    pasta = os.path.dirname(caminho_saida)
    if pasta:
        os.makedirs(pasta, exist_ok=True)
    limpa.save(caminho_saida, format=formato)

    with Image.open(caminho_saida) as conferida:
        depois = resumo_metadados(conferida)
    if depois["tem_gps"] or depois["campos_exif"] > 0:
        # nao deveria acontecer, mas se acontecer a foto nao pode seguir
        os.remove(caminho_saida)
        raise ImagemInvalida("nao foi possivel limpar os metadados")
    return {"antes": antes, "depois": depois, "arquivo_limpo": caminho_saida}


# ---------------- 2. supervisao humana do diagnostico ----------------

LIMIAR_CONFIANCA = 0.75


def decidir_diagnostico(classe, confianca, limiar=LIMIAR_CONFIANCA):
    # a CNN sugere, mas abaixo do limiar quem decide e uma pessoa
    if not isinstance(classe, str) or classe.strip() == "":
        raise ValueError("classe precisa ser um texto nao vazio")
    if isinstance(confianca, bool) or not isinstance(confianca, (int, float)):
        raise ValueError("confianca precisa ser um numero")
    if math.isnan(confianca) or confianca < 0 or confianca > 1:
        raise ValueError("confianca precisa estar entre 0 e 1")

    if confianca < limiar:
        acao = "ACIONAR_TECNICO"
        mensagem = "Diagnostico inconclusivo - acionar tecnico agricola da cooperativa"
    elif "healthy" in classe.lower() or "saudavel" in classe.lower():
        acao = "PLANTA_SAUDAVEL"
        mensagem = "Folha saudavel, seguir monitorando"
    else:
        acao = "ALERTA_DOENCA"
        mensagem = "Possivel doenca detectada - separar o lote e confirmar com o tecnico"
    return {"classe": classe, "confianca": round(float(confianca), 3),
            "acao": acao, "decisao_automatica": acao != "ACIONAR_TECNICO", "mensagem": mensagem}


# ---------------- 3. dados limpos para o treino do ML ----------------

CHAVES_CONTRATO = [
    "id_sensor", "fazenda", "cultivo", "umidade", "temperatura", "umidade_ar",
    "nivel_reservatorio", "status_umidade", "status_temperatura", "status_reservatorio",
    "bomba", "risco_perda_lote", "motivo", "data_hora",
]
FAIXAS = {"umidade": (0, 100), "umidade_ar": (0, 100), "nivel_reservatorio": (0, 100), "temperatura": (-10, 65)}


def motivo_para_descartar(registro):
    # devolve None se a leitura pode ir pro treino, ou o motivo do descarte
    if not isinstance(registro, dict):
        return "linha nao e um objeto JSON"
    if sorted(registro.keys()) != sorted(CHAVES_CONTRATO):
        return "chaves diferentes do contrato"
    for campo, (minimo, maximo) in FAIXAS.items():
        valor = registro[campo]
        if isinstance(valor, bool) or not isinstance(valor, (int, float)):
            return campo + " nao e numero"
        if math.isnan(valor) or valor < minimo or valor > maximo:
            return campo + " fora da faixa fisica"
    if registro["motivo"] not in config.MOTIVOS_VALIDOS:
        return "motivo desconhecido"
    if not isinstance(registro["bomba"], bool):
        return "bomba nao e booleano"
    for campo in ("id_sensor", "fazenda", "cultivo"):
        texto = registro[campo]
        if not isinstance(texto, str) or texto == "" or texto.startswith(("=", "+", "-", "@", "'")):
            return campo + " suspeito"
    return None


def filtrar_jsonl_para_treino(caminho_entrada, caminho_saida):
    # gera um JSONL so com leituras confiaveis + conta o que foi descartado e por que
    if not os.path.exists(caminho_entrada):
        raise FileNotFoundError("arquivo nao encontrado: " + caminho_entrada)

    aceitas = []
    descartes = {}
    with open(caminho_entrada, "r", encoding="utf-8") as arq:
        for numero, linha in enumerate(arq, start=1):
            linha = linha.strip()
            if linha == "":
                continue
            try:
                registro = json.loads(linha)
            except json.JSONDecodeError:
                motivo = "JSON quebrado"
            else:
                motivo = motivo_para_descartar(registro)
            if motivo is None:
                aceitas.append(registro)
            else:
                descartes[motivo] = descartes.get(motivo, 0) + 1

    with open(caminho_saida, "w", encoding="utf-8") as arq:
        for registro in aceitas:
            arq.write(json.dumps(registro, ensure_ascii=True) + "\n")

    return {"aceitas": len(aceitas), "descartadas": sum(descartes.values()), "motivos": descartes}
