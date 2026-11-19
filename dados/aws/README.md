# AWS (Plataformas e Servicos Cognitivos)

Responsavel: Danilo Keithi Makiya Nakasone (RM574137)

Data Lake na AWS com a arquitetura medalhao sobre as leituras do Heimdall (`../leituras_sensores.jsonl`):
bucket S3 com raw, bronze, silver, gold e resultados-athena; database `dbheimdall` e crawler no Glue;
bronze por CTAS no Athena; silver e gold por jobs ETL visuais do Glue.

Video da demonstracao (YouTube, nao listado): https://youtu.be/giiDRl5nLe4

Detalhes do que o video mostra: [`Heimdall_Plataformas_Cognitivas.txt`](Heimdall_Plataformas_Cognitivas.txt)

## Recriar o Data Lake

Se o Learner Lab apagar os recursos, `criar_datalake_aws.py` refaz tudo com os mesmos nomes (bucket, database, crawler, bronze por CTAS, jobs do Glue e comprovacao no Athena).
Colocar o `credentials` do AWS Details na mesma pasta (nunca vai pro git) e rodar `python criar_datalake_aws.py`.
Resultado esperado: raw, bronze e silver com 50 linhas e gold com 14.
