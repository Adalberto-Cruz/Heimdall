# AWS (Plataformas e Servicos Cognitivos)

Responsavel: Danilo Keithi Makiya Nakasone (RM574137)

Data Lake na AWS com a arquitetura medalhao sobre as leituras do Heimdall (`../leituras_sensores.jsonl`):
bucket S3 com raw, bronze, silver, gold e resultados-athena; database `dbheimdall` e crawler no Glue;
bronze por CTAS no Athena; silver e gold por jobs ETL visuais do Glue.

Video da demonstracao (YouTube, nao listado): https://youtu.be/giiDRl5nLe4

Detalhes do que o video mostra: [`Heimdall_Plataformas_Cognitivas.txt`](Heimdall_Plataformas_Cognitivas.txt)
