# criar_datalake_aws.py
# Monta o Data Lake do Heimdall na AWS (arquitetura medalhao) com os mesmos nomes do video
# de Plataformas Cognitivas: bucket, database, crawler, bronze por CTAS, jobs do Glue e Athena.
#
# Como usar (Windows, no PC):
#   1. pip install boto3
#   2. No Learner Lab: Start Lab, depois AWS Details > AWS CLI > Show.
#      Colar o bloco inteiro num credenciais.txt na mesma pasta deste script
#      (ou passar o caminho com --credenciais). Esse txt nunca vai pro git.
#   3. python criar_datalake_aws.py
#
# Tambem roda no CloudShell do console (la o boto3 ja vem instalado).
# As credenciais do Learner Lab vencem em umas 4 horas: se der erro de token, copiar de novo.
# Pode rodar mais de uma vez: o que ja existe e reaproveitado ou recriado.

import argparse
import json
import sys
import time
from pathlib import Path

try:
    import boto3
    from botocore.exceptions import ClientError, NoCredentialsError, BotoCoreError
except ImportError:
    print("Falta o boto3. Rode: pip install boto3")
    sys.exit(1)

REGIAO = "us-east-1"
BUCKET_PADRAO = "heimdall-datalake-sensores"
DATABASE = "dbheimdall"
CRAWLER = "crawler_dados_brutos"
JOB_SILVER = "job_bronze_para_silver"
JOB_GOLD = "job_silver_para_gold"
PASTAS = ["raw/", "bronze/", "silver/", "gold/", "resultados-athena/"]
ARQUIVO_PADRAO = Path(__file__).resolve().parent.parent / "leituras_sensores.jsonl"

# script PySpark dos jobs (o job visual mostra o desenho, este e o codigo que roda)
SCRIPT_SILVER = '''import sys
from awsglue.utils import getResolvedOptions
from awsglue.context import GlueContext
from awsglue.job import Job
from pyspark.context import SparkContext

args = getResolvedOptions(sys.argv, ["JOB_NAME", "BUCKET"])
glue = GlueContext(SparkContext.getOrCreate())
spark = glue.spark_session
job = Job(glue)
job.init(args["JOB_NAME"], args)

b = args["BUCKET"]
bronze = spark.read.parquet("s3://" + b + "/bronze/")
# silver: so id_sensor, fazenda e umidade
bronze.select("id_sensor", "fazenda", "umidade").write.mode("overwrite").parquet("s3://" + b + "/silver/")
job.commit()
'''

SCRIPT_GOLD = '''import sys
from awsglue.utils import getResolvedOptions
from awsglue.context import GlueContext
from awsglue.job import Job
from pyspark.context import SparkContext
from pyspark.sql import functions as F

args = getResolvedOptions(sys.argv, ["JOB_NAME", "BUCKET"])
glue = GlueContext(SparkContext.getOrCreate())
spark = glue.spark_session
job = Job(glue)
job.init(args["JOB_NAME"], args)

b = args["BUCKET"]
silver = spark.read.parquet("s3://" + b + "/silver/")
# gold: media de umidade por sensor e fazenda
gold = silver.groupBy("id_sensor", "fazenda").agg(F.round(F.avg("umidade"), 2).alias("media_umidade"))
gold.write.mode("overwrite").parquet("s3://" + b + "/gold/")
job.commit()
'''


def passo(msg):
    print("\n== " + msg)


def erro_aws(e):
    if isinstance(e, ClientError):
        return e.response.get("Error", {}).get("Code", "") + ": " + e.response.get("Error", {}).get("Message", "")
    return str(e)


def ler_credenciais_txt(caminho):
    # aceita o bloco do AWS Details (aws_access_key_id=...) ou as linhas $env:AWS_ACCESS_KEY_ID="..."
    nomes = {
        "aws_access_key_id": "aws_access_key_id",
        "aws_secret_access_key": "aws_secret_access_key",
        "aws_session_token": "aws_session_token",
    }
    achou = {}
    for linha in Path(caminho).read_text(encoding="utf-8-sig").splitlines():
        linha = linha.strip()
        if "=" not in linha or linha.startswith("#") or linha.startswith("["):
            continue
        chave, valor = linha.split("=", 1)
        chave = chave.strip().replace("$env:", "").lower()
        valor = valor.strip().strip('"').strip("'")
        if chave in nomes and valor:
            achou[nomes[chave]] = valor
    faltando = [n for n in ("aws_access_key_id", "aws_secret_access_key", "aws_session_token") if n not in achou]
    if faltando:
        print("No " + str(caminho) + " faltou: " + ", ".join(faltando))
        print("Cole o bloco inteiro do AWS Details > AWS CLI no arquivo.")
        sys.exit(1)
    print("Credenciais lidas de " + str(caminho))
    return achou


def conferir_credenciais(sessao):
    passo("Conferindo as credenciais do Learner Lab")
    try:
        ident = sessao.client("sts").get_caller_identity()
    except NoCredentialsError:
        print("Nao achei credenciais. Copie o bloco do AWS Details para o arquivo .aws/credentials.")
        sys.exit(1)
    except (ClientError, BotoCoreError) as e:
        print("Credencial recusada (" + erro_aws(e) + ").")
        print("Se o lab foi reiniciado ou passou de 4 horas, copie as credenciais de novo.")
        sys.exit(1)
    print("Conta " + ident["Account"] + " | " + ident["Arn"])
    return ident["Account"]


def preparar_bucket(s3, nome, conta):
    passo("Bucket e pastas")
    try:
        if REGIAO == "us-east-1":
            s3.create_bucket(Bucket=nome)
        else:
            s3.create_bucket(Bucket=nome, CreateBucketConfiguration={"LocationConstraint": REGIAO})
        print("Bucket criado: " + nome)
    except ClientError as e:
        cod = e.response["Error"]["Code"]
        if cod == "BucketAlreadyOwnedByYou":
            print("Bucket ja existe nesta conta, vou reaproveitar: " + nome)
        elif cod == "BucketAlreadyExists":
            # nome de bucket e global, se outra conta pegou usa o numero da conta no final
            novo = nome + "-" + conta
            print("O nome " + nome + " ja e de outra conta. Usando " + novo)
            return preparar_bucket(s3, novo, conta)
        else:
            raise
    for p in PASTAS:
        s3.put_object(Bucket=nome, Key=p)
    print("Pastas: " + ", ".join(PASTAS))
    return nome


def subir_dados(s3, bucket, arquivo):
    passo("Subindo as leituras para raw/")
    if not arquivo.exists():
        print("Arquivo nao encontrado: " + str(arquivo))
        print("Passe o caminho com --arquivo (o arquivo fica em dados/leituras_sensores.jsonl no repositorio).")
        sys.exit(1)
    linhas = []
    for i, l in enumerate(arquivo.read_text(encoding="utf-8").splitlines(), 1):
        if not l.strip():
            continue
        try:
            json.loads(l)
        except json.JSONDecodeError:
            print("Linha " + str(i) + " do arquivo nao e um JSON valido, parei aqui.")
            sys.exit(1)
        linhas.append(l)
    if not linhas:
        print("Arquivo vazio.")
        sys.exit(1)
    s3.put_object(Bucket=bucket, Key="raw/leituras_sensores.jsonl", Body=("\n".join(linhas) + "\n").encode("utf-8"))
    print(str(len(linhas)) + " leituras enviadas")


def criar_database(glue):
    passo("Database no Glue")
    try:
        glue.create_database(DatabaseInput={"Name": DATABASE, "Description": "Data Lake do Heimdall - leituras dos sensores"})
        print("Database criada: " + DATABASE)
    except ClientError as e:
        if e.response["Error"]["Code"] == "AlreadyExistsException":
            print("Database ja existe: " + DATABASE)
        else:
            raise


def rodar_crawler(glue, bucket, role):
    passo("Crawler lendo raw/")
    alvo = {"S3Targets": [{"Path": "s3://" + bucket + "/raw/"}]}
    try:
        glue.create_crawler(Name=CRAWLER, Role=role, DatabaseName=DATABASE, Targets=alvo)
        print("Crawler criado: " + CRAWLER)
    except ClientError as e:
        if e.response["Error"]["Code"] != "AlreadyExistsException":
            raise
        glue.update_crawler(Name=CRAWLER, Role=role, DatabaseName=DATABASE, Targets=alvo)
        print("Crawler ja existia, atualizei: " + CRAWLER)

    try:
        glue.start_crawler(Name=CRAWLER)
    except ClientError as e:
        if e.response["Error"]["Code"] != "CrawlerRunningException":
            raise
    print("Rodando", end="", flush=True)
    inicio = time.time()
    while True:
        time.sleep(10)
        c = glue.get_crawler(Name=CRAWLER)["Crawler"]
        print(".", end="", flush=True)
        if c["State"] == "READY":
            break
        if time.time() - inicio > 600:
            print("\nCrawler passou de 10 minutos. Veja no console do Glue.")
            sys.exit(1)
    status = c.get("LastCrawl", {}).get("Status")
    print(" " + str(status))
    if status != "SUCCEEDED":
        print("Crawler falhou: " + str(c.get("LastCrawl", {}).get("ErrorMessage")))
        sys.exit(1)
    try:
        glue.get_table(DatabaseName=DATABASE, Name="raw")
        print("Tabela raw criada pelo crawler")
    except ClientError:
        print("O crawler rodou mas nao criou a tabela raw. Confira no console se o nome saiu diferente.")
        sys.exit(1)


class Athena:
    def __init__(self, cliente, bucket):
        self.c = cliente
        self.saida = "s3://" + bucket + "/resultados-athena/"

    def configurar(self):
        passo("Athena salvando em resultados-athena/")
        try:
            self.c.update_work_group(
                WorkGroup="primary",
                ConfigurationUpdates={"ResultConfigurationUpdates": {"OutputLocation": self.saida}},
            )
            print("Workgroup primary configurado: " + self.saida)
        except ClientError as e:
            # se o lab nao deixar mexer no workgroup, cada consulta ja manda o local de saida
            print("Nao deu para alterar o workgroup (" + erro_aws(e) + "). As consultas usam o local direto.")

    def sql(self, consulta, mostrar=False):
        print("  " + " ".join(consulta.split())[:110])
        qid = self.c.start_query_execution(
            QueryString=consulta,
            QueryExecutionContext={"Database": DATABASE},
            ResultConfiguration={"OutputLocation": self.saida},
            WorkGroup="primary",
        )["QueryExecutionId"]
        inicio = time.time()
        while True:
            st = self.c.get_query_execution(QueryExecutionId=qid)["QueryExecution"]["Status"]
            if st["State"] in ("SUCCEEDED", "FAILED", "CANCELLED"):
                break
            if time.time() - inicio > 300:
                print("Consulta passou de 5 minutos.")
                sys.exit(1)
            time.sleep(2)
        if st["State"] != "SUCCEEDED":
            print("Consulta falhou: " + st.get("StateChangeReason", ""))
            sys.exit(1)
        if not mostrar:
            return None
        linhas = self.c.get_query_results(QueryExecutionId=qid, MaxResults=100)["ResultSet"]["Rows"]
        return [[d.get("VarCharValue", "") for d in r["Data"]] for r in linhas]


def limpar_prefixo(s3, bucket, prefixo):
    # o CTAS so grava em pasta vazia
    pag = s3.get_paginator("list_objects_v2")
    for pagina in pag.paginate(Bucket=bucket, Prefix=prefixo):
        objs = [{"Key": o["Key"]} for o in pagina.get("Contents", [])]
        if objs:
            s3.delete_objects(Bucket=bucket, Delete={"Objects": objs})


def apagar_tabela(glue, nome):
    # apaga direto no catalogo do Glue (o DROP do Athena as vezes nao remove tabela antiga do Glue)
    try:
        glue.delete_table(DatabaseName=DATABASE, Name=nome)
        print("  tabela antiga " + nome + " removida do catalogo")
    except ClientError as e:
        if e.response["Error"]["Code"] != "EntityNotFoundException":
            raise


def criar_bronze(athena, glue, s3, bucket):
    passo("Bronze por CTAS (Parquet em bronze/, com data_ingestao)")
    apagar_tabela(glue, "bronze")
    limpar_prefixo(s3, bucket, "bronze/")
    athena.sql(
        "CREATE TABLE bronze WITH (format = 'PARQUET', external_location = 's3://" + bucket + "/bronze/') AS "
        "SELECT *, CAST(current_timestamp AS timestamp) AS data_ingestao FROM raw"
    )
    print("Bronze criada")


def criar_tabelas_destino(athena, glue, bucket):
    passo("Tabelas silver e gold no catalogo (Parquet, sem particao)")
    apagar_tabela(glue, "silver")
    athena.sql(
        "CREATE EXTERNAL TABLE silver (id_sensor string, fazenda string, umidade double) "
        "STORED AS PARQUET LOCATION 's3://" + bucket + "/silver/'"
    )
    apagar_tabela(glue, "gold")
    athena.sql(
        "CREATE EXTERNAL TABLE gold (id_sensor string, fazenda string, media_umidade double) "
        "STORED AS PARQUET LOCATION 's3://" + bucket + "/gold/'"
    )


def nos_visuais(bucket, qual):
    # desenho que aparece no Glue Studio (ETL visual)
    if qual == "silver":
        return {
            "node_bronze": {"S3CatalogSource": {"Name": "Bronze (Data Catalog)", "Database": DATABASE, "Table": "bronze"}},
            "node_campos": {"SelectFields": {"Name": "Mantem id_sensor, fazenda e umidade", "Inputs": ["node_bronze"],
                                             "Paths": [["id_sensor"], ["fazenda"], ["umidade"]]}},
            "node_silver": {"S3GlueParquetTarget": {"Name": "Silver (S3 Parquet)", "Inputs": ["node_campos"],
                                                    "Path": "s3://" + bucket + "/silver/", "Compression": "snappy"}},
        }
    return {
        "node_silver": {"S3CatalogSource": {"Name": "Silver (Data Catalog)", "Database": DATABASE, "Table": "silver"}},
        "node_media": {"Aggregate": {"Name": "Media de umidade por id_sensor e fazenda", "Inputs": ["node_silver"],
                                     "Groups": [["id_sensor"], ["fazenda"]],
                                     "Aggs": [{"Column": ["umidade"], "AggFunc": "avg"}]}},
        "node_nome": {"RenameField": {"Name": "Renomeia para media_umidade", "Inputs": ["node_media"],
                                      "SourcePath": ["avg(umidade)"], "TargetPath": ["media_umidade"]}},
        "node_gold": {"S3GlueParquetTarget": {"Name": "Gold (S3 Parquet)", "Inputs": ["node_nome"],
                                              "Path": "s3://" + bucket + "/gold/", "Compression": "snappy"}},
    }


def criar_job(glue, s3, bucket, role, nome, script, qual):
    chave = "scripts/" + nome + ".py"
    s3.put_object(Bucket=bucket, Key=chave, Body=script.encode("utf-8"))
    config = {
        "Role": role,
        "Command": {"Name": "glueetl", "ScriptLocation": "s3://" + bucket + "/" + chave, "PythonVersion": "3"},
        "DefaultArguments": {"--BUCKET": bucket, "--job-language": "python"},
        "GlueVersion": "4.0",
        "WorkerType": "G.1X",
        "NumberOfWorkers": 2,
        "Timeout": 15,
    }
    for com_visual in (True, False):
        cfg = dict(config)
        if com_visual:
            cfg["CodeGenConfigurationNodes"] = nos_visuais(bucket, qual)
        try:
            try:
                glue.create_job(Name=nome, **cfg)
                print("Job criado: " + nome + (" (visual)" if com_visual else ""))
            except ClientError as e:
                if e.response["Error"]["Code"] not in ("AlreadyExistsException", "IdempotentParameterMismatchException"):
                    raise
                glue.update_job(JobName=nome, JobUpdate=cfg)
                print("Job ja existia, atualizei: " + nome + (" (visual)" if com_visual else ""))
            return
        except ClientError as e:
            if com_visual and e.response["Error"]["Code"] in ("InvalidInputException", "ValidationException"):
                print("A AWS recusou o desenho visual (" + erro_aws(e) + "). Criando o job so com o script.")
                continue
            raise


def rodar_job(glue, nome):
    run = glue.start_job_run(JobName=nome)["JobRunId"]
    print("Rodando " + nome, end="", flush=True)
    inicio = time.time()
    while True:
        time.sleep(15)
        jr = glue.get_job_run(JobName=nome, RunId=run)["JobRun"]
        print(".", end="", flush=True)
        if jr["JobRunState"] in ("SUCCEEDED", "FAILED", "STOPPED", "TIMEOUT", "ERROR"):
            break
        if time.time() - inicio > 1200:
            print("\nJob passou de 20 minutos. Veja no console do Glue.")
            sys.exit(1)
    print(" " + jr["JobRunState"])
    if jr["JobRunState"] != "SUCCEEDED":
        print("Erro do job: " + str(jr.get("ErrorMessage")))
        sys.exit(1)


def esperado_do_arquivo(arquivo):
    # conta direto no arquivo quantas linhas e quantos grupos (sensor + fazenda) a gold deve ter
    leituras = [json.loads(l) for l in Path(arquivo).read_text(encoding="utf-8").splitlines() if l.strip()]
    grupos = {(r.get("id_sensor"), r.get("fazenda")) for r in leituras}
    return len(leituras), len(grupos)


def comprovar(athena, arquivo):
    passo("Comprovacao no Athena")
    n_linhas, n_grupos = esperado_do_arquivo(arquivo)
    for tabela, esperado in (("raw", n_linhas), ("bronze", n_linhas), ("silver", n_linhas), ("gold", n_grupos)):
        total = athena.sql("SELECT COUNT(*) FROM " + tabela, mostrar=True)[1][0]
        ok = "ok" if str(total) == str(esperado) else "DIFERENTE do esperado (" + str(esperado) + ")"
        print("  " + tabela + ": " + str(total) + " linhas - " + ok)
    linhas = athena.sql("SELECT * FROM gold ORDER BY fazenda, id_sensor", mostrar=True)
    print("\n  " + " | ".join(linhas[0]))
    for l in linhas[1:]:
        print("  " + " | ".join(l))


def main():
    ap = argparse.ArgumentParser(description="Monta o Data Lake do Heimdall na AWS")
    ap.add_argument("--bucket", default=BUCKET_PADRAO)
    ap.add_argument("--arquivo", default=None, help="leituras_sensores.jsonl")
    ap.add_argument("--credenciais", default=None, help="txt com o bloco do AWS Details")
    args = ap.parse_args()

    pasta = Path(__file__).resolve().parent
    # procura o jsonl do lado do script e depois na pasta dados/ do repositorio
    if args.arquivo is None:
        args.arquivo = str(pasta / "leituras_sensores.jsonl") if (pasta / "leituras_sensores.jsonl").exists() else str(ARQUIVO_PADRAO)

    # credenciais: primeiro o credenciais.txt (ou o --credenciais), senao o .aws/credentials ou as variaveis do PowerShell
    if args.credenciais:
        txt = Path(args.credenciais)
    else:
        # aceita credenciais.txt ou credentials do lado do script
        txt = next((pasta / n for n in ("credenciais.txt", "credentials") if (pasta / n).exists()), pasta / "credenciais.txt")
    if args.credenciais and not txt.exists():
        print("Arquivo de credenciais nao encontrado: " + str(txt))
        sys.exit(1)
    if txt.exists():
        sessao = boto3.Session(region_name=REGIAO, **ler_credenciais_txt(txt))
    else:
        sessao = boto3.Session(region_name=REGIAO)
    conta = conferir_credenciais(sessao)
    role = "arn:aws:iam::" + conta + ":role/LabRole"  # no Learner Lab os servicos usam a LabRole
    s3 = sessao.client("s3")
    glue = sessao.client("glue")

    try:
        bucket = preparar_bucket(s3, args.bucket, conta)
        subir_dados(s3, bucket, Path(args.arquivo))
        criar_database(glue)
        rodar_crawler(glue, bucket, role)
        athena = Athena(sessao.client("athena"), bucket)
        athena.configurar()
        criar_bronze(athena, glue, s3, bucket)
        criar_tabelas_destino(athena, glue, bucket)
        passo("Jobs ETL do Glue (bronze > silver > gold)")
        criar_job(glue, s3, bucket, role, JOB_SILVER, SCRIPT_SILVER, "silver")
        criar_job(glue, s3, bucket, role, JOB_GOLD, SCRIPT_GOLD, "gold")
        # o job visual so acrescenta arquivos, entao limpa a pasta antes pra nao duplicar nem sobrar lixo
        for pasta_destino, job in (("silver/", JOB_SILVER), ("gold/", JOB_GOLD)):
            limpar_prefixo(s3, bucket, pasta_destino)
            s3.put_object(Bucket=bucket, Key=pasta_destino)
            rodar_job(glue, job)
        comprovar(athena, args.arquivo)
    except (ClientError, BotoCoreError) as e:
        print("\nA AWS recusou um passo: " + erro_aws(e))
        print("Se for AccessDenied, o Learner Lab bloqueou esse servico. Se for token, copie as credenciais de novo.")
        sys.exit(1)

    print("\nPronto. Bucket: " + bucket)


if __name__ == "__main__":
    main()
