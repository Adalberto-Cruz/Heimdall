# Versao segura (Cognitive Cybersecurity)

## Arquivos

| Arquivo | O que faz |
|---|---|
| `app_seguro.py` | API blindada (o "depois") |
| `seguranca.py` | HMAC, anti-replay, limite de requisicoes, CSV injection, plausibilidade, auditoria |
| `gerar_env.py` | cria o `.env` com chaves aleatorias |
| `rodar_antes.py` | sobe a `app.py` (sem protecao) na porta 8000, dados em `dados_antes/` |
| `rodar_depois.py` | sobe a `app_seguro.py` na porta 8001, dados em `dados_depois/` |
| `validador_ataques_cyber.py` | ataca as duas e gera a tabela Antes vs Depois (`resultado_validacao.md`) |
| `ia_seguranca.py` | protecoes dos componentes de IA: remove EXIF/GPS das fotos, supervisao humana do diagnostico, filtro contra dados envenenados |
| `demo_ia_seguranca.py` | mostra as 3 protecoes de IA funcionando |
| `test_ia_seguranca.py` | 13 testes das protecoes de IA |

Os ataques usam pastas proprias (`dados_antes/`, `dados_depois/`), entao nao sujam os dados oficiais em `dados/`.

## Como rodar a demonstracao

```
python gerar_env.py                  # uma vez so
python rodar_antes.py                # terminal 1
python rodar_depois.py               # terminal 2
python validador_ataques_cyber.py    # terminal 3 (leva ~1 min no final)
```

Pra rodar o validador de novo, espere 1 minuto (limite de requisicoes) e apague as pastas `dados_antes/` e `dados_depois/` se quiser comecar limpo.

## Defesas e o que cada uma bloqueia

| Defesa | Bloqueia | Codigo |
|---|---|---|
| X-API-Key + assinatura HMAC-SHA256 por dispositivo | leitura falsa, assinatura forjada, sensor falando por outro | 401 |
| Timestamp com prazo de 60 s + assinatura de uso unico | replay e pacote antigo | 401 |
| X-API-Key nos GETs | leitura do historico por estranhos | 401 |
| Schema estrito + limite de 2 KB | campo extra, payload gigante | 422 |
| Plausibilidade fisica (max 8 C ou 30 pontos de umidade em 5 min) | salto tipo 25 C -> 50 C (caso dos supermercados europeus) | 422 |
| Limite de 60 req/min por IP e 30 por dispositivo | flood / DoS | 429 |
| Apostrofo antes de = + - @ | CSV injection no Excel | 201 neutralizado |
| GET /sensores/status | sensor que parou de mandar dados (perda de visibilidade) | alerta |
| `.env` + `auditoria_seguranca.log` | segredo no codigo, ataque sem rastro | - |
| `/docs` desligado | mapa da API exposto | - |

## Componentes de IA

| Risco | Protecao | Onde |
|---|---|---|
| Foto da folha entrega a localizacao da propriedade (GPS no EXIF) | `remover_metadados` copia so os pixels; recusa arquivo falso, vazio, gigante ou de formato estranho | `ia_seguranca.py` |
| CNN erra com confianca baixa e o produtor joga fora um lote bom (ou guarda um doente) | `decidir_diagnostico`: abaixo de 0,75 a decisao vai pro tecnico agricola | `ia_seguranca.py` |
| Dados envenenados no treino do ML (valor impossivel, rotulo inventado, formula, campo extra) | so leitura assinada e validada entra no JSONL; `filtrar_jsonl_para_treino` confere de novo antes do treino | `app_seguro.py` + `ia_seguranca.py` |

```
python demo_ia_seguranca.py
python -m unittest test_ia_seguranca -v
```

## Para o Gustavo: como o ESP32 assina cada envio

Headers obrigatorios no POST:

```
Content-Type: application/json
X-API-Key: <API_KEY do .env>
X-Device-Id: S01
X-Timestamp: <segundos desde 1970, UTC>
X-Signature: <HMAC-SHA256 em hex de "timestamp.corpo">
```

O corpo assinado tem que ser exatamente a mesma string enviada no POST.
O relogio do ESP32 precisa vir do NTP (`configTime(0, 0, "pool.ntp.org")`), senao o timestamp sai da janela e a API responde 401.

```cpp
#include <mbedtls/md.h>
#include <time.h>

String hmacSha256(const String& chave, const String& mensagem) {
  byte saida[32];
  mbedtls_md_context_t ctx;
  mbedtls_md_init(&ctx);
  mbedtls_md_setup(&ctx, mbedtls_md_info_from_type(MBEDTLS_MD_SHA256), 1);
  mbedtls_md_hmac_starts(&ctx, (const unsigned char*)chave.c_str(), chave.length());
  mbedtls_md_hmac_update(&ctx, (const unsigned char*)mensagem.c_str(), mensagem.length());
  mbedtls_md_hmac_finish(&ctx, saida);
  mbedtls_md_free(&ctx);
  char hex[65];
  for (int i = 0; i < 32; i++) sprintf(hex + 2 * i, "%02x", saida[i]);
  hex[64] = 0;
  return String(hex);
}

// no envio:
// String corpo = ...;                       // o JSON da leitura
// String ts = String((long)time(nullptr));
// http.addHeader("X-Device-Id", "S01");
// http.addHeader("X-Timestamp", ts);
// http.addHeader("X-Signature", hmacSha256(CHAVE_DO_S01, ts + "." + corpo));
// http.POST(corpo);
```

Regra que vale para o firmware: o ESP32 nunca liga a bomba por ordem vinda da rede. A trava do reservatorio e o tempo maximo de bomba ficam no proprio chip.

## Limitacoes conhecidas

- Atras do ngrok, todos os clientes aparecem com o mesmo IP local, entao o limite por IP fica compartilhado.
- No Wokwi a chave do dispositivo fica visivel no codigo do projeto; num ESP32 real ela iria para a memoria protegida (NVS criptografada / flash encryption).
- A checagem de plausibilidade guarda a ultima leitura em memoria: ao reiniciar a API, a primeira leitura de cada sensor passa sem comparacao.
- Quem tiver a chave de um ESP32 (acesso fisico ao aparelho) consegue assinar leituras falsas daquele sensor; a plausibilidade e a divergencia ajudam a perceber, mas nao impedem.
