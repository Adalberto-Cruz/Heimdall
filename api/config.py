# config.py
# Aqui ficam todos os limites e premissas do projeto num lugar so.
# Se precisar mudar algum valor, muda aqui e o resto do codigo acompanha.

import os

# pasta onde ficam o CSV e o JSONL (da pra trocar pela variavel de ambiente DATA_DIR, os testes usam isso)
PASTA_BASE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.environ.get("DATA_DIR", os.path.join(PASTA_BASE, "dados"))
ARQUIVO_CSV = os.path.join(DATA_DIR, "leituras_sensores.csv")
ARQUIVO_JSONL = os.path.join(DATA_DIR, "leituras_sensores.jsonl")

# limite de umidade do solo por cultivo (%)
# o enunciado de CDS fala em irrigar quando a umidade cai abaixo do limite DO CULTIVO
# Tomate: valores da ficha do projeto
# Soja: premissa didatica, trocar pelo percentil 20 da base CEMADEN quando a analise sair
LIMIARES_POR_CULTIVO = {
    "Tomate": {"alerta": 35.0, "critica": 20.0},
    "Soja": {"alerta": 30.0, "critica": 18.0},
}
LIMIAR_PADRAO = {"alerta": 35.0, "critica": 20.0}

# temperatura (C)
TEMP_ALERTA = 35.0   # acima disso: estresse termico e risco alto de perder o lote
TEMP_ATENCAO = 30.0  # acima disso: risco medio

# reservatorio (%) - abaixo disso a bomba nao pode ligar (queima a seco)
RESERVATORIO_MIN = 20.0

# horarios (Portaria Normativa MME 137/2026)
# ponta: 17:00 ate 21:30, nunca tem desconto
# janela contratada: o produtor escolhe ate 8h30 por dia fora da ponta, aqui usamos 21:30 ate 06:00
PONTA_INICIO = "17:00"
PONTA_FIM = "21:30"
JANELA_INICIO = "21:30"
JANELA_FIM = "06:00"

# premissas da economia de energia
# Economia = E x T x [1 - (1 - r) x (1 - f x d)]
ENERGIA_MES_KWH = 264.0     # E: bomba de 3 cv (~2,2 kW) rodando 4h por dia
TARIFA_KWH = 0.85           # T: tarifa media estimada em R$/kWh
REDUCAO_SENSORES = 0.25     # r: reducao de bombeamento com sensores (faixa Embrapa 20% a 30%)
DESCONTO_TARIFA = 0.73      # d: Grupo B na area da Sudene (fazenda no semiarido, Petrolina-PE)
# f (quanto do bombeamento cai na janela) nao fica aqui: e calculado com os dados reais

# indice de risco de perda por fazenda
PESO_RISCO = {"ALTO": 1.0, "MEDIO": 0.5, "BAIXO": 0.0}
INDICE_VENDA_RAPIDA = 0.30  # a partir disso o lote vai pra venda rapida ou PAA
INDICE_MONITORAR = 0.10

# motivos que contam como alerta critico
MOTIVOS_CRITICOS = [
    "BLOQUEIO_RESERVATORIO_BAIXO",
    "ALERTA_CALOR_EXTREMO",
    "IRRIGACAO_EMERGENCIAL_SOLO_CRITICO",
]

# valores aceitos nos campos de decisao
STATUS_VALIDOS = ["OK", "ALERTA"]
RISCOS_VALIDOS = ["BAIXO", "MEDIO", "ALTO"]
MOTIVOS_VALIDOS = [
    "BLOQUEIO_RESERVATORIO_BAIXO",
    "ALERTA_CALOR_EXTREMO",
    "IRRIGACAO_EMERGENCIAL_SOLO_CRITICO",
    "SOLO_SECO_JANELA_DESCONTO",
    "AGUARDANDO_JANELA_DESCONTO",
    "CONDICOES_ESTAVEIS",
]

FORMATO_DATA = "%Y-%m-%d %H:%M:%S"
