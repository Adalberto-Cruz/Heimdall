# Estatística (Statistical Computing with R & Python)

Relatório: [`Heimdall_Statistical_Computing.pdf`](Heimdall_Statistical_Computing.pdf)

Base real: estação Petrolina 03 (código 261110103C) do CEMADEN, do conjunto *A soil moisture dataset over the Brazilian semiarid region* (Zeri et al., 2020), Mendeley Data, DOI 10.17632/xrk5rfcpvg.2, licença CC BY 4.0.

## Arquivos

- `cemaden_petrolina_diario.csv`: base diária usada no relatório (1.023 dias, 11/2015 a 04/2019)
- `preparar_base.py`: gera o CSV a partir da planilha original da estação (`PCD_Acqua_PE_261110103C.xlsx`)
- `analise_estatistica.py`: questões 2 a 6 (normal, testes Z, regressão simples e múltipla, logística) e gráficos

## Como rodar

```
pip install pandas numpy scipy statsmodels scikit-learn matplotlib openpyxl
python preparar_base.py PCD_Acqua_PE_261110103C.xlsx   # opcional, o CSV já está aqui
python analise_estatistica.py                          # resultados no terminal e gráficos em graficos/
```
