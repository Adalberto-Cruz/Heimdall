/*
  Heimdall - AICSS (CitizenTech)
  Fluxo: fenomeno -> ESP32 + sensores -> alerta local -> JSON -> servidor Python
*/
#include <Arduino.h>
#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <HTTPClient.h>
#include <DHT.h>

// ================= CONECTIVIDADE =================
const char* WIFI_SSID  = "Wokwi-GUEST";
const char* WIFI_PASS  = "";
const char* SERVER_URL = "https://statistical-means-televisions-foods.trycloudflare.com/leituras";
const char* API_KEY    = "CHAVE_SECRETA";   // Será gerado na parte de Cybersecurity

const char* ID_SENSOR = "S01";
const char* FAZENDA   = "Sitio Boa Esperanca";
const char* CULTIVO   = "Tomate";

// ================= PINOS =================
#define PIN_SOLO     34   // potenciometro (simula umidade do solo)
#define PIN_DHT      15   // DHT22 (umidade e temperatura)
#define PIN_TRIG      5   // trigger do HC-SR04 (sensor de nivel do reservatorio)
#define PIN_ECHO     18   // echo do HC-SR04 (sensor de nivel do reservatorio)
#define PIN_CHAVE     4   // LOW = janela de desconto (22h15) | HIGH = horario de ponta (19h00)
#define PIN_RELE     26   // aciona bomba de irrigacao
#define PIN_LED_VERDE    25   // indica que tudo OK
#define PIN_LED_AMARELO  27   // indica alerta
#define PIN_LED_VERMELHO 14   // indica critico
#define PIN_BUZZER       12   // indica critico

// ================= LIMIARES (contrato do projeto) =================
const float LIM_UMIDADE_ALERTA   = 35.0;   // < 35  -> ALERTA
const float LIM_UMIDADE_CRITICA  = 20.0;   // < 20  -> critico (irriga mesmo fora da janela)
const float LIM_TEMP_ALERTA      = 35.0;   // > 35  -> ALERTA + risco ALTO
const float LIM_RESERVATORIO     = 20.0;   // < 20  -> ALERTA + bloqueia bomba
const float ALTURA_TANQUE_CM     = 40.0;   // distancia sensor -> fundo do tanque
const unsigned long TEMPO_MAX_BOMBA_MS = 10UL * 60UL * 1000UL;  // trava: max 10 min continuos

const unsigned long INTERVALO_LEITURA_MS = 1000;    // decisao local a cada 1 s
const unsigned long INTERVALO_ENVIO_MS   = 10000;   // envio periodico a cada 10 s

DHT dht(PIN_DHT, DHT22);

struct Leitura {
  float umidade, temperatura, umidadeAr, nivel;
  const char *stUmidade, *stTemp, *stReserv;
  bool bomba;
  const char *risco, *motivo;
  bool janela;
};

// ---------- offline (se a rede cair, guarda e reenvia) ----------
const int BUF_MAX = 20;
String bufferOffline[BUF_MAX];
int bufferQtd = 0;

float ultimaTemp = 25.0, ultimaUmAr = 50.0, ultimoNivel = 100.0;
unsigned long tLeitura = 0, tEnvio = 0, bombaDesde = 0;
bool bombaLigada = false;
String ultimoMotivo = "";

// ================= LEITURAS =================
float lerUmidadeSolo() {
  int bruto = analogRead(PIN_SOLO);            // 0..4095
  return bruto * 100.0 / 4095.0;
}

float lerNivelReservatorio() {
  digitalWrite(PIN_TRIG, LOW);  delayMicroseconds(2);
  digitalWrite(PIN_TRIG, HIGH); delayMicroseconds(10);
  digitalWrite(PIN_TRIG, LOW);
  long dur = pulseIn(PIN_ECHO, HIGH, 30000);
  if (dur == 0) return ultimoNivel;            // falha de leitura: mantem o ultimo valor
  float distCm = dur * 0.0343 / 2.0;
  float nivel = (ALTURA_TANQUE_CM - distCm) / ALTURA_TANQUE_CM * 100.0;
  nivel = constrain(nivel, 0.0, 100.0);
  ultimoNivel = nivel;
  return nivel;
}

void horaSimulada(char* buf, size_t n, bool janela) {
  int h = janela ? 22 : 19;
  int m = janela ? 15 : 0;
  unsigned long s = millis() / 1000;
  snprintf(buf, n, "2026-11-12 %02d:%02d:%02d", h, (int)(m + (s / 60) % 45), (int)(s % 60));
}

// ================= DECISAO =================
Leitura avaliar() {
  Leitura L;
  L.umidade = lerUmidadeSolo();
  float t = dht.readTemperature();
  float u = dht.readHumidity();
  if (!isnan(t)) ultimaTemp = t;
  if (!isnan(u)) ultimaUmAr = u;
  L.temperatura = ultimaTemp;
  L.umidadeAr = ultimaUmAr;
  L.nivel = lerNivelReservatorio();
  L.janela = (digitalRead(PIN_CHAVE) == LOW);

  // status por sensor
  L.stUmidade = (L.umidade < LIM_UMIDADE_ALERTA) ? "ALERTA" : "OK";
  L.stTemp    = (L.temperatura > LIM_TEMP_ALERTA) ? "ALERTA" : "OK";
  L.stReserv  = (L.nivel < LIM_RESERVATORIO) ? "ALERTA" : "OK";

  bool soloSeco    = (L.umidade < LIM_UMIDADE_ALERTA);
  bool soloCritico = (L.umidade < LIM_UMIDADE_CRITICA);
  bool reservBaixo = (L.nivel < LIM_RESERVATORIO);
  bool calor       = (L.temperatura > LIM_TEMP_ALERTA);

  // bomba: trava de seguranca do reservatorio vem primeiro
  bool bomba = false;
  if (!reservBaixo && soloSeco && (L.janela || soloCritico)) bomba = true;

  // trava de tempo maximo continuo (defesa em profundidade, independe da rede)
  if (bomba && bombaLigada && (millis() - bombaDesde > TEMPO_MAX_BOMBA_MS)) bomba = false;
  L.bomba = bomba;

  // risco de perda do lote
  if (calor) L.risco = "ALTO";
  else if (soloCritico || (soloSeco && !bomba)) L.risco = "MEDIO";
  else L.risco = "BAIXO";

  // prioridade: reservatorio > calor > solo
  if (reservBaixo)                        L.motivo = "BLOQUEIO_RESERVATORIO_BAIXO";
  else if (calor)                         L.motivo = "ALERTA_CALOR_EXTREMO";
  else if (soloSeco && bomba && L.janela) L.motivo = "SOLO_SECO_JANELA_DESCONTO";
  else if (soloSeco && bomba)             L.motivo = "SOLO_CRITICO_FORA_JANELA";
  else if (soloSeco)                      L.motivo = "AGUARDANDO_JANELA_DESCONTO";
  else                                    L.motivo = "TUDO_OK";
  return L;
}

// ================= ATUADORES =================
void acionar(const Leitura& L) {
  // rele
  if (L.bomba && !bombaLigada) bombaDesde = millis();
  bombaLigada = L.bomba;
  digitalWrite(PIN_RELE, L.bomba ? HIGH : LOW);

  bool alarme = (strcmp(L.motivo, "BLOQUEIO_RESERVATORIO_BAIXO") == 0) ||
                (strcmp(L.motivo, "ALERTA_CALOR_EXTREMO") == 0);
  bool espera = (strcmp(L.motivo, "AGUARDANDO_JANELA_DESCONTO") == 0);

  digitalWrite(PIN_LED_VERMELHO, alarme ? HIGH : LOW);
  digitalWrite(PIN_BUZZER,       alarme ? HIGH : LOW);
  digitalWrite(PIN_LED_AMARELO,  (!alarme && espera) ? HIGH : LOW);
  digitalWrite(PIN_LED_VERDE,    (!alarme && !espera) ? HIGH : LOW);
}

// ================= JSON =================
String montarJson(const Leitura& L) {
  char hora[24];
  horaSimulada(hora, sizeof(hora), L.janela);
  char json[480];
  snprintf(json, sizeof(json),
    "{\"id_sensor\":\"%s\",\"fazenda\":\"%s\",\"cultivo\":\"%s\","
    "\"umidade\":%.1f,\"temperatura\":%.1f,\"umidade_ar\":%.1f,\"nivel_reservatorio\":%.1f,"
    "\"status_umidade\":\"%s\",\"status_temperatura\":\"%s\",\"status_reservatorio\":\"%s\","
    "\"bomba\":%s,\"risco_perda_lote\":\"%s\",\"motivo\":\"%s\",\"data_hora\":\"%s\"}",
    ID_SENSOR, FAZENDA, CULTIVO,
    L.umidade, L.temperatura, L.umidadeAr, L.nivel,
    L.stUmidade, L.stTemp, L.stReserv,
    L.bomba ? "true" : "false", L.risco, L.motivo, hora);
  return String(json);
}

// ================= REDE =================
bool postJson(const String& body) {
  if (WiFi.status() != WL_CONNECTED) return false;
  HTTPClient http;
  WiFiClientSecure secure;
  WiFiClient plain;
  bool https = String(SERVER_URL).startsWith("https");
  if (https) { secure.setInsecure(); http.begin(secure, SERVER_URL); }
  else       { http.begin(plain, SERVER_URL); }
  http.addHeader("Content-Type", "application/json");
  http.addHeader("X-API-Key", API_KEY);
  http.addHeader("ngrok-skip-browser-warning", "true");
  int code = http.POST(body);
  http.end();
  Serial.printf("[HTTP] POST -> %d\n", code);
  return (code >= 200 && code < 300);
}

void enviar(const String& body) {
  // primeiro tenta esvaziar o buffer offline (ate 5 por ciclo)
  int tentativas = 0;
  while (bufferQtd > 0 && tentativas < 5) {
    if (postJson(bufferOffline[0])) {
      for (int i = 1; i < bufferQtd; i++) bufferOffline[i - 1] = bufferOffline[i];
      bufferQtd--;
      Serial.println("[BUFFER] leitura antiga reenviada");
    } else break;
    tentativas++;
  }
  if (!postJson(body)) {
    if (bufferQtd < BUF_MAX) { bufferOffline[bufferQtd++] = body; }
    Serial.printf("[BUFFER] sem rede, guardado (%d/%d)\n", bufferQtd, BUF_MAX);
  }
}

void conectarWiFi() {
  WiFi.begin(WIFI_SSID, WIFI_PASS, 6);
  Serial.print("Conectando WiFi");
  unsigned long t0 = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - t0 < 10000) { delay(250); Serial.print("."); }
  Serial.println(WiFi.status() == WL_CONNECTED ? " OK" : " FALHOU (modo offline)");
}

void setup() {
  Serial.begin(115200);
  pinMode(PIN_TRIG, OUTPUT);
  pinMode(PIN_ECHO, INPUT);
  pinMode(PIN_CHAVE, INPUT_PULLUP);
  pinMode(PIN_RELE, OUTPUT);
  pinMode(PIN_LED_VERDE, OUTPUT);
  pinMode(PIN_LED_AMARELO, OUTPUT);
  pinMode(PIN_LED_VERMELHO, OUTPUT);
  pinMode(PIN_BUZZER, OUTPUT);
  dht.begin();
  conectarWiFi();
}

void loop() {
  unsigned long agora = millis();
  if (agora - tLeitura >= INTERVALO_LEITURA_MS) {
    tLeitura = agora;
    Leitura L = avaliar();
    acionar(L);                                   // alerta local sempre, mesmo sem internet

    bool mudou = (ultimoMotivo != String(L.motivo));
    if (mudou || (agora - tEnvio >= INTERVALO_ENVIO_MS)) {
      tEnvio = agora;
      ultimoMotivo = String(L.motivo);
      String json = montarJson(L);
      Serial.println(json);                       // evidencia: JSON transmitido
      enviar(json);
    }
  }
  if (WiFi.status() != WL_CONNECTED && (agora % 30000) < 50) WiFi.reconnect();
}
