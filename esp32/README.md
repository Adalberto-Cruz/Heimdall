# ESP32 (AI Computer Systems & Sensors)

Responsavel: Gustavo da Silva Nascimento (RM570821)

Relatorio da entrega: [`Heimdall_AICSS.pdf`](Heimdall_AICSS.pdf).

## Arquivos

- `src/main.cpp`: firmware do ESP32 (sensores, limiares, decisao e envio do JSON)
- `platformio.ini`: configuracao do PlatformIO (placa esp32dev e bibliotecas do DHT)
- `diagram.json` e `wokwi.toml`: circuito e configuracao do simulador Wokwi
- `servidor_aicss.py`: servidor Python que recebe o JSON, mostra no terminal e grava em CSV e JSONL
- `leituras_sensores.csv` e `leituras_sensores.jsonl`: leituras gravadas nos testes do relatorio

## Como rodar

1. Servidor: `pip install fastapi uvicorn` e depois `uvicorn servidor_aicss:app --host 0.0.0.0 --port 8000`
2. Tunel: `ngrok http 8000` (ou cloudflared) e copiar a URL https para `SERVER_URL` no `src/main.cpp`
3. Firmware: abrir a pasta no VS Code com PlatformIO, compilar (`pio run`) e iniciar a simulacao com a extensao do Wokwi

Para enviar para a versao segura da API, o ESP32 assina cada leitura: ver [`api/SEGURANCA.md`](../api/SEGURANCA.md).

A chave do dispositivo nunca entra no repositorio.
