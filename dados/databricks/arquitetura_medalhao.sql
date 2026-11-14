-- Arquitetura Medalhao no Databricks (Cognitive Data Science)
-- Catalogo db_ADG (iniciais dos integrantes: Adalberto, Danilo e Gustavo)

-- Catalogo e volume
CREATE CATALOG IF NOT EXISTS db_ADG;
USE CATALOG db_ADG;
USE SCHEMA default;
CREATE VOLUME IF NOT EXISTS db_ADG.default.arquivos;
SHOW VOLUMES;

-- Arquivos do volume e consulta direta no JSON
LIST '/Volumes/db_ADG/default/arquivos/';
SELECT * FROM json.`/Volumes/db_ADG/default/arquivos/leituras_sensores.jsonl`;

-- Camada Bronze (CTAS)
CREATE OR REPLACE TABLE db_ADG.default.bronze AS
SELECT *
FROM json.`/Volumes/db_ADG/default/arquivos/leituras_sensores.jsonl`;

SELECT * FROM db_ADG.default.bronze;

-- Camada Silver
CREATE OR REPLACE TABLE db_ADG.default.silver AS
SELECT
    umidade,
    fazenda,
    cultivo
FROM db_ADG.default.bronze;

SELECT * FROM db_ADG.default.silver;

-- Camada Gold
CREATE OR REPLACE VIEW db_ADG.default.gold AS
SELECT
    fazenda,
    ROUND(AVG(umidade), 2) AS media_umidade
FROM db_ADG.default.silver
GROUP BY fazenda;

SELECT * FROM db_ADG.default.gold;
