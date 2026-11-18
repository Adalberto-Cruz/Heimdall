# Contexto do projeto Heimdall

Documento de referência do grupo. Qualquer pessoa ou IA que for escrever código, relatório, slide ou roteiro do Heimdall deve ler este arquivo antes. Ele vale para todas as disciplinas da Global Solution 2026.2 e para versões futuras do projeto.

## 1. Visão

**Heimdall: o vigia que protege o alimento do campo à mesa.**

Plataforma de IoT e IA contra a perda de alimentos em toda a cadeia: na lavoura, no armazenamento, no transporte e na prateleira. Funciona para o pequeno e para o grande, no campo e na cidade.

O alimento se perde em duas fases:

- **Antes da colheita:** seca, irrigação na hora errada e doença na lavoura.
- **Depois da colheita:** calor e falta de controle no galpão, no caminhão, na banca e na gôndola.

Entre 2013 e 2022 a estiagem causou R$ 186,2 bilhões de perdas agrícolas no Brasil (CNM). Frutas, legumes e verduras são a seção com mais perdas nos supermercados: 5,93% (Abrappe, 2024).

## 2. Públicos (mesma plataforma, escalas diferentes)

| Escala | Exemplos | Como usa o Heimdall |
|---|---|---|
| Pequeno | agricultor familiar, horta, feirante, vendedor de manga, sacolão de bairro | Kit com ESP32 e alertas simples (LED, buzzer, celular) |
| Médio | cooperativas, redes regionais de hortifruti | Dezenas de sensores na mesma API, painel por fazenda e por lote |
| Grande | redes de supermercado (ex.: Carrefour), distribuidores, programas públicos (PAA) | Dados na nuvem, análises e modelos de IA sobre milhares de leituras |

Rural e urbano: no campo protege a lavoura e a irrigação; na cidade protege o estoque, a câmara fria e a banca.

## 3. Os elos da cadeia

| Elo | O que o Heimdall faz |
|---|---|
| **1. Campo: irrigação** | Mede a umidade do solo, irriga na hora certa e na tarifa mais barata (Portaria MME 137/2026) e trava a bomba quando o reservatório está baixo |
| **2. Campo: saúde da lavoura** | Triagem de doença por foto da folha, para agir antes de perder a produção |
| **3. Armazenamento e transporte** | Monitora temperatura e umidade do lote, calcula o risco de perda e alerta calor extremo |
| **4. Varejo e destino** | Aponta os lotes em risco para venda rápida ou doação (PAA) antes de estragar |
| **Transversal: segurança** | Protege os dados e os comandos contra ataques (leituras falsas, freezers desligados remotamente, injeção no CSV) |

## 4. Cada disciplina é uma peça do mesmo sistema

| Disciplina | Responsável | Peça do Heimdall | Elo | Entrada | Saída que alimenta outra peça |
|---|---|---|---|---|---|
| AI Computer Systems & Sensors | Gustavo | ESP32 com sensores e alerta local | 1 e 3 | solo, ar, reservatório | JSON do contrato para a API |
| Computational Thinking with Python | Adalberto | API REST (FastAPI) | 1, 3 e 4 | JSON do ESP32 | CSV e JSONL para Databricks, AWS, Estatística e ML |
| Cognitive Cybersecurity | Adalberto | Blindagem da API e dos modelos | transversal | ataques simulados | API segura (HMAC, anti-replay, limites) |
| Cognitive Data Science | Danilo | Pipeline Databricks (Bronze, Silver, Gold) | todos | JSONL da API | visão por fazenda, cultivo e lote |
| Plataformas Cognitivas | Danilo | Nuvem AWS | todos | JSONL da API | armazenamento e consulta para os grandes clientes |
| Statistical Computing | Danilo | Análise estatística da umidade do solo | 1 | dados reais CEMADEN | limiar de estresse, sazonalidade, base para os alertas |
| Machine Learning | Gustavo | Previsão da umidade do solo em 24 h | 1 | histórico de umidade e chuva (CEMADEN) | previsão para antecipar a irrigação |
| Redes Neurais | Gustavo | CNN de doenças em folha de tomate | 2 | foto da folha (PlantVillage) | classe, confiança e alerta ao produtor |
| AI Challenge | Adalberto | Vídeo integrador | todos | todas as peças | apresentação do sistema inteiro |

Fluxo dos dados:

```
ESP32 (AICSS) --JSON--> API Python (Python + Cyber) --CSV/JSONL--> Databricks e AWS (CDS + PlatCog)
                                                     \--> Estatística e ML (umidade, previsão 24 h)
Foto da folha --> Rede Neural (CNN) --> alerta ao produtor
Todas as peças --> vídeo integrador (AI Challenge)
```

## 5. Contrato JSON único

```json
{"id_sensor":"S01","fazenda":"Sitio Boa Esperanca","cultivo":"Tomate","umidade":28.4,"temperatura":33.1,"umidade_ar":41.0,"nivel_reservatorio":62.0,"status_umidade":"ALERTA","status_temperatura":"OK","status_reservatorio":"OK","bomba":true,"risco_perda_lote":"BAIXO","motivo":"SOLO_SECO_JANELA_DESCONTO","data_hora":"2026-11-12 22:15:00"}
```

Textos sem acento. Motivos, em ordem de prioridade: `BLOQUEIO_RESERVATORIO_BAIXO`, `ALERTA_CALOR_EXTREMO`, `IRRIGACAO_EMERGENCIAL_SOLO_CRITICO`, `SOLO_SECO_JANELA_DESCONTO`, `AGUARDANDO_JANELA_DESCONTO`, `CONDICOES_ESTAVEIS`.

Premissas comuns: cultivo de exemplo é o tomate; local de exemplo é Petrolina/PE (semiárido, irrigação decisiva); horário de ponta 17h00 às 21h30; janela de irrigação contratada 21h30 às 06h00.

## 6. Regras para qualquer entrega (pessoa ou IA)

1. **Toda entrega tem uma seção "O Heimdall e esta disciplina"**, logo depois do problema, com quatro pontos:
   - a visão do Heimdall em um parágrafo (do campo à mesa, do pequeno ao grande, rural e urbano);
   - qual elo da cadeia esta disciplina cobre;
   - de onde vêm os dados e para qual peça vai o resultado;
   - o que foi implementado agora e o que fica como evolução.
2. **O recorte técnico pode ser estreito, o contexto não.** Uma análise de umidade do solo de uma estação é válida, mas o texto precisa dizer onde ela entra no sistema inteiro.
3. **Mesmos nomes, mesmos números, mesmo contrato.** Usar sempre "Heimdall" (nunca os nomes antigos Rega Certa ou GiroFresco), o contrato JSON acima e as premissas comuns. Se uma disciplina mudar uma regra, atualizar este arquivo.
4. **Dados reais e verificáveis.** Nada de base gerada ou fictícia apresentada como real. Toda base cita fonte, DOI ou link, e o tratamento é documentado.
5. **Honestidade nos resultados.** Mostrar baseline, limitações e erros do modelo. Não exagerar o que foi feito.
6. **Padrão visual e de escrita.** Capa com projeto, turma, nomes, RMs e repositório, sem local e data. Texto com acentos, sem emojis, sem frases de assistente ("Olá, professor"), em tom de relatório para cliente.
7. **Código e arquivos com nomes de mercado** (`servidor.py`, `preparar_base.py`), comentários simples, como de aluno.
8. **Commits só no nome do integrante**, sem coautoria de IA. Segredos (`.env`) nunca entram no repositório nem nos ZIPs.

## 7. Checklist antes de entregar

- [ ] A seção "O Heimdall e esta disciplina" está presente e cita pelo menos uma peça vizinha (de onde vem o dado, para onde vai).
- [ ] Os públicos pequeno, médio e grande aparecem.
- [ ] O nome é Heimdall em tudo e o contrato JSON bate com a seção 5.
- [ ] A base de dados é real e a fonte está citada.
- [ ] O formato de entrega segue o enunciado da disciplina (PDF único, arquivos soltos ou ZIP).
