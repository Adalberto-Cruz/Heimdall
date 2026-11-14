# simulacao_ataques.py
# Dispara os mesmos ataques contra a versao sem protecao (ANTES, porta 8000)
# e contra a versao blindada (DEPOIS, porta 8001) e monta a tabela comparativa.
#
# Antes de rodar, em dois terminais:
#   python servidor.py --modo vulneravel
#   python servidor.py --modo seguro
# Depois: python simulacao_ataques.py
# (se rodar de novo, espere 1 minuto por causa do limite de requisicoes)
#
# Os ataques sao inspirados nos casos reais de 2026 em que hackers mexeram
# na temperatura de geladeiras de supermercados e falsificaram as leituras.

import json
import os
import sys
import time

import requests

import seguranca

# 127.0.0.1 e nao localhost: no Windows o localhost tenta IPv6 antes e cada pedido demora uns 2 s
ANTES = "http://127.0.0.1:8000"
DEPOIS = "http://127.0.0.1:8001"
PASTA = os.path.dirname(os.path.abspath(__file__))
CSV_ANTES = os.path.join(PASTA, "dados_vulneravel", "leituras_sensores.csv")
CSV_DEPOIS = os.path.join(PASTA, "dados_seguro", "leituras_sensores.csv")
LOG_DEPOIS = os.path.join(PASTA, "dados_seguro", "auditoria_seguranca.log")
RESULTADO_MD = os.path.join(PASTA, "resultado_validacao.md")

# o validador faz o papel do ESP32 legitimo, por isso le as mesmas chaves do .env
try:
    ENV = seguranca.carregar_env()
    API_KEY = ENV["API_KEY"]
    CHAVES = seguranca.ler_chaves_dispositivos(ENV["CHAVES_DISPOSITIVOS"])
except seguranca.ConfigFaltando as erro:
    print(str(erro))
    sys.exit(1)


def leitura(id_sensor, **mudancas):
    base = {"id_sensor": id_sensor, "fazenda": "Fazenda Boa Safra", "cultivo": "Soja",
            "umidade": 40.0, "temperatura": 25.0, "umidade_ar": 50.0,
            "nivel_reservatorio": 70.0, "data_hora": "2026-11-12 14:00:00"}
    base.update(mudancas)
    return base


def corpo_bytes(dados):
    return json.dumps(dados, separators=(",", ":")).encode("utf-8")


def cabecalhos_assinados(id_sensor, corpo, segredo=None, timestamp=None):
    # o que o ESP32 legitimo manda
    ts = int(time.time()) if timestamp is None else timestamp
    chave = CHAVES[id_sensor] if segredo is None else segredo
    return {
        "Content-Type": "application/json",
        "X-API-Key": API_KEY,
        "X-Device-Id": id_sensor,
        "X-Timestamp": str(ts),
        "X-Signature": seguranca.calcular_assinatura(chave, ts, corpo),
    }


def post(url, corpo, cabecalhos=None):
    h = {"Content-Type": "application/json"}
    if cabecalhos:
        h.update(cabecalhos)
    try:
        return requests.post(url + "/leituras", data=corpo, headers=h, timeout=5).status_code
    except requests.exceptions.ConnectionError:
        return None


def ultima_linha(caminho):
    if not os.path.exists(caminho):
        return "(sem arquivo)"
    with open(caminho, "r", encoding="utf-8-sig") as arq:
        linhas = arq.readlines()
    return linhas[-1].strip() if len(linhas) > 1 else "(so cabecalho)"


def conferir_apis():
    for nome, url in (("ANTES", ANTES), ("DEPOIS", DEPOIS)):
        try:
            requests.get(url + "/", timeout=3)
        except requests.exceptions.ConnectionError:
            print("A API " + nome + " nao esta no ar em " + url)
            print("Abra dois terminais e rode: python servidor.py --modo vulneravel  e  python servidor.py --modo seguro")
            sys.exit(1)


resultados = []


def registrar(ataque, antes, depois, esperado, caso_real):
    texto = lambda c: "sem resposta" if c is None else str(c)
    resultados.append({"ataque": ataque, "antes": texto(antes), "depois": texto(depois),
                       "esperado": esperado, "caso_real": caso_real})
    print("  ANTES:  " + texto(antes) + "   DEPOIS: " + texto(depois) + "   (esperado depois: " + esperado + ")")


def titulo(texto):
    print("")
    print("=" * 74)
    print(texto)
    print("=" * 74)


def main():
    conferir_apis()

    # 0) leitura legitima nas duas (prova que o ESP32 de verdade continua funcionando)
    titulo("0. Leitura legitima do ESP32 (S01) - deve passar nas duas")
    dados = leitura("S01", fazenda="Sitio Boa Esperanca", cultivo="Tomate")
    c = corpo_bytes(dados)
    registrar("Leitura legitima assinada", post(ANTES, c), post(DEPOIS, c, cabecalhos_assinados("S01", c)),
              "201", "-")

    # 1) spoofing: atacante sem credencial manda galpao "frio" pra esconder o calor
    titulo("1. Spoofing: leitura falsa sem credencial (galpao a 22 C pra esconder calor)")
    c = corpo_bytes(leitura("S05", temperatura=22.0))
    registrar("Spoofing sem credencial", post(ANTES, c), post(DEPOIS, c), "401",
              "leituras falsificadas escondendo o aquecimento (Claroty, DEF CON 2026)")

    # 2) assinatura forjada com chave errada
    titulo("2. Assinatura forjada (atacante chuta a chave do S05)")
    c = corpo_bytes(leitura("S05", temperatura=22.0))
    falso = cabecalhos_assinados("S05", c, segredo="chave-chutada")
    registrar("Assinatura HMAC forjada", post(ANTES, c, falso), post(DEPOIS, c, falso), "401",
              "bypass de autenticacao (alerta FBI/CISA, nov/2026)")

    # 3) replay: pacote legitimo capturado e reenviado
    titulo("3. Replay: reenviar um pacote legitimo capturado")
    c = corpo_bytes(leitura("S03", cultivo="Soja", fazenda="Cooperativa Vale Verde"))
    h = cabecalhos_assinados("S03", c)
    post(DEPOIS, c, h)  # primeira vez: legitima
    post(ANTES, c)
    registrar("Replay do mesmo pacote", post(ANTES, c), post(DEPOIS, c, h), "401",
              "reenvio de comando/leitura antiga")

    # 4) timestamp velho (pacote gravado ha 10 minutos)
    titulo("4. Pacote antigo (assinado ha 10 minutos)")
    c = corpo_bytes(leitura("S03", cultivo="Soja", fazenda="Cooperativa Vale Verde", umidade=41.0))
    h = cabecalhos_assinados("S03", c, timestamp=int(time.time()) - 600)
    registrar("Timestamp fora da janela", post(ANTES, c), post(DEPOIS, c, h), "401",
              "reenvio de pacote antigo")

    # 5) sensor tentando falar por outro
    titulo("5. S04 assinando uma leitura em nome do S05")
    c = corpo_bytes(leitura("S05", temperatura=22.0))
    h = cabecalhos_assinados("S04", c)
    registrar("Sensor se passando por outro", post(ANTES, c), post(DEPOIS, c, h), "401",
              "dispositivo comprometido usado como ponte")

    # 6) variacao impossivel: 25 C -> 50 C em segundos
    titulo("6. Variacao impossivel: S02 vai de 25 C a 50 C em segundos")
    c1 = corpo_bytes(leitura("S02", fazenda="Sitio Boa Esperanca", cultivo="Tomate", temperatura=25.0))
    post(ANTES, c1)
    post(DEPOIS, c1, cabecalhos_assinados("S02", c1))
    c2 = corpo_bytes(leitura("S02", fazenda="Sitio Boa Esperanca", cultivo="Tomate", temperatura=50.0))
    registrar("Salto de 25 C para 50 C", post(ANTES, c2), post(DEPOIS, c2, cabecalhos_assinados("S02", c2)), "422",
              "freezers levados a 50 C (Franca e Europa, out-nov/2026)")

    # 7) CSV injection
    titulo("7. CSV injection: formula no nome da fazenda")
    dados = leitura("S04", fazenda="=cmd|' /C calc'!A0", cultivo="Tomate")
    c = corpo_bytes(dados)
    antes = post(ANTES, c)
    depois = post(DEPOIS, c, cabecalhos_assinados("S04", c))
    registrar("Formula no CSV (=cmd...)", antes, depois, "201 neutralizado",
              "injecao de codigo (alerta FBI/CISA)")
    print("  Linha no CSV ANTES:  " + ultima_linha(CSV_ANTES))
    print("  Linha no CSV DEPOIS: " + ultima_linha(CSV_DEPOIS))

    # 8) payload gigante / campo extra
    titulo("8. Payload gigante com campo extra (100 KB)")
    dados = leitura("S04", cultivo="Tomate")
    dados["lixo"] = "A" * 100000
    c = corpo_bytes(dados)
    registrar("Payload de 100 KB", post(ANTES, c), post(DEPOIS, c, cabecalhos_assinados("S04", c)), "422",
              "esgotar recursos do servidor")

    # 9) valor impossivel (as duas ja protegem: validacao da disciplina de Python)
    titulo("9. Valor impossivel: umidade 150%")
    c = corpo_bytes(leitura("S04", cultivo="Tomate", umidade=150.0))
    registrar("Umidade 150%", post(ANTES, c), post(DEPOIS, c, cabecalhos_assinados("S04", c)), "422",
              "-")

    # 10) leitura sem autenticacao nos GETs
    titulo("10. Ler o historico sem chave (vazamento de dados)")
    try:
        a = requests.get(ANTES + "/leituras", timeout=5).status_code
        d = requests.get(DEPOIS + "/leituras", timeout=5).status_code
    except requests.exceptions.ConnectionError:
        a, d = None, None
    registrar("GET /leituras sem chave", a, d, "401", "-")

    # 11) flood sem credencial (por ultimo, porque gasta o limite do IP)
    titulo("11. Flood: 70 requisicoes seguidas sem credencial")
    contagem_antes, contagem_depois = {}, {}
    c = corpo_bytes(leitura("S05", temperatura=22.0))
    for _ in range(70):
        ra = post(ANTES, c)
        rd = post(DEPOIS, c)
        contagem_antes[ra] = contagem_antes.get(ra, 0) + 1
        contagem_depois[rd] = contagem_depois.get(rd, 0) + 1
    resumo = lambda d: ", ".join(str(k) + " x" + str(v) for k, v in sorted(d.items(), key=lambda i: str(i[0])))
    print("  ANTES:  " + resumo(contagem_antes))
    print("  DEPOIS: " + resumo(contagem_depois))
    resultados.append({"ataque": "Flood de 70 requisicoes", "antes": resumo(contagem_antes),
                       "depois": resumo(contagem_depois), "esperado": "429 apos o limite",
                       "caso_real": "derrubar o monitoramento (perda de visibilidade)"})

    # status dos sensores (perda de visibilidade)
    titulo("Status dos sensores na versao segura (sensor calado vira alerta)")
    time.sleep(61)  # espera o limite por IP zerar pra conseguir consultar
    try:
        r = requests.get(DEPOIS + "/sensores/status", headers={"X-API-Key": API_KEY}, timeout=5)
        print(json.dumps(r.json(), indent=2, ensure_ascii=False))
    except requests.exceptions.ConnectionError:
        print("  sem resposta")

    # tabela final
    titulo("TABELA ANTES vs DEPOIS")
    print("{:<32} {:<22} {:<26}".format("Ataque", "ANTES", "DEPOIS"))
    for r in resultados:
        print("{:<32} {:<22} {:<26}".format(r["ataque"][:32], r["antes"][:22], r["depois"][:26]))

    with open(RESULTADO_MD, "w", encoding="utf-8") as arq:
        arq.write("| Ataque | Antes (app.py) | Depois (app_seguro.py) | Esperado | Caso real relacionado |\n")
        arq.write("| --- | --- | --- | --- | --- |\n")
        for r in resultados:
            arq.write("| " + " | ".join([r["ataque"], r["antes"], r["depois"], r["esperado"], r["caso_real"]]) + " |\n")
    print("")
    print("Tabela salva em " + RESULTADO_MD)

    titulo("auditoria_seguranca.log - eventos por tipo")
    if not os.path.exists(LOG_DEPOIS):
        print("  log nao encontrado")
        return
    contagem = {}
    exemplos = {}
    with open(LOG_DEPOIS, "r", encoding="utf-8") as arq:
        for linha in arq:
            try:
                evento = json.loads(linha)
            except json.JSONDecodeError:
                continue
            nome = evento.get("evento", "?")
            contagem[nome] = contagem.get(nome, 0) + 1
            exemplos.setdefault(nome, linha.strip())
    for nome, total in sorted(contagem.items(), key=lambda i: -i[1]):
        print("  " + nome.ljust(28) + str(total))
    print("")
    print("Um exemplo de cada evento:")
    for nome in contagem:
        print("  " + exemplos[nome])


if __name__ == "__main__":
    try:
        main()
    except seguranca.ConfigFaltando as erro:
        print(str(erro))
        sys.exit(1)
