"""
Heimdall - GS 2026.2 - Statistical Computing with R & Python
Analise estatistica da umidade do solo em Petrolina/PE (base real do CEMADEN).

Integrantes:
  Adalberto Alves Cruz - RM574115
  Danilo Keithi Makiya Nakasone - RM574137
  Gustavo da Silva Nascimento - RM570821

Entrada: cemaden_petrolina_diario.csv (gerado pelo preparar_base.py)
Saida:   resultados no terminal e graficos na pasta graficos/

Uso: python analise_estatistica.py
"""

import os
import sys

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")  # salva os graficos em arquivo, sem abrir janela
import matplotlib.pyplot as plt
from scipy.stats import norm
import statsmodels.api as sm
from sklearn.metrics import confusion_matrix, accuracy_score

ARQUIVO = "cemaden_petrolina_diario.csv"
PASTA_GRAFICOS = "graficos"
SEMENTE = 42  # para as amostras sairem sempre iguais
ROSA = "#e3125d"
AZUL = "#1f4e79"

# ----------------------------------------------------------------------------
# carregando a base
# ----------------------------------------------------------------------------
if not os.path.exists(ARQUIVO):
    print(f"Arquivo {ARQUIVO} nao encontrado. Rode antes: python preparar_base.py <planilha da estacao>")
    sys.exit(1)

df = pd.read_csv(ARQUIVO, parse_dates=["data"])
colunas = ["umidade_10cm", "umidade_20cm", "chuva_dia_mm", "chuva_7d_mm", "chuva_30d_mm", "estresse_hidrico"]
faltando = [c for c in colunas if c not in df.columns]
if faltando:
    print(f"A base nao tem as colunas: {faltando}")
    sys.exit(1)

df = df.dropna(subset=colunas)
df["mes"] = df["data"].dt.month
os.makedirs(PASTA_GRAFICOS, exist_ok=True)


def salvar(nome):
    plt.tight_layout()
    plt.savefig(os.path.join(PASTA_GRAFICOS, nome), dpi=150)
    plt.close()


def titulo(texto):
    print("\n" + "=" * 78)
    print(texto)
    print("=" * 78)


titulo("BASE DE DADOS")
print(f"{len(df)} dias de {df['data'].min():%d/%m/%Y} a {df['data'].max():%d/%m/%Y} - estacao 261110103C (Petrolina/PE)")
print(df[colunas].describe().round(2).to_string())

# serie no tempo, so para contextualizar o relatorio
serie = df.set_index("data").asfreq("D")  # dias sem dado ficam vazios e a linha nao liga os buracos
fig, ax = plt.subplots(figsize=(10, 4))
ax.plot(serie.index, serie["umidade_10cm"], color=AZUL, lw=0.8, label="Umidade a 10 cm (%)")
ax.axhline(7, color=ROSA, ls="--", lw=1, label="Limiar de estresse (7%)")
ax2 = ax.twinx()
ax2.bar(df["data"], df["chuva_dia_mm"], color="#9bbbd4", width=1, alpha=0.6, label="Chuva do dia (mm)")
ax2.set_ylabel("Chuva do dia (mm)")
ax.set_zorder(ax2.get_zorder() + 1)
ax.patch.set_visible(False)
ax.set_title("Umidade do solo a 10 cm e chuva diária - Petrolina/PE (CEMADEN)")
ax.set_xlabel("Data")
ax.set_ylabel("Umidade volumétrica (%)")
l1, n1 = ax.get_legend_handles_labels()
l2, n2 = ax2.get_legend_handles_labels()
ax.legend(l1 + l2, n1 + n2, loc="upper right", fontsize=8)
salvar("00_serie_temporal.png")

# ----------------------------------------------------------------------------
# QUESTAO 2 - distribuicao normal (variavel: umidade a 10 cm)
# ----------------------------------------------------------------------------
titulo("QUESTAO 2 - DISTRIBUICAO NORMAL (umidade_10cm)")
x = df["umidade_10cm"]
mu = x.mean()
sigma = x.std(ddof=0)  # desvio padrao populacional
mediana = x.median()
print(f"media = {mu:.4f} | desvio padrao = {sigma:.4f} | mediana = {mediana:.4f}")


def classificar(p):
    if p == 0:
        return "evento impossivel"
    if p < 0.5:
        return "evento improvavel (pouco provavel)"
    if np.isclose(p, 0.5):
        return "evento equiprovavel (50%)"
    if p < 1:
        return "evento provavel"
    return "evento certo"


p_a = norm.cdf(mu, mu, sigma)
p_b = norm.sf(mediana, mu, sigma)
z_med = (mediana - mu) / sigma
print(f"a) P(X < {mu:.2f}) = {p_a:.4f} -> {classificar(p_a)}")
print(f"b) Z = ({mediana:.2f} - {mu:.2f}) / {sigma:.2f} = {z_med:.4f}")
print(f"   P(X > {mediana:.2f}) = {p_b:.4f} -> {classificar(p_b)}")

xs = np.linspace(mu - 4 * sigma, mu + 4 * sigma, 400)
plt.figure(figsize=(8, 4))
plt.plot(xs, norm.pdf(xs, mu, sigma), color="black")
plt.fill_between(xs, norm.pdf(xs, mu, sigma), where=xs <= mu, color=AZUL, alpha=0.25, label=f"P(X < média) = {p_a:.2%}")
plt.fill_between(xs, norm.pdf(xs, mu, sigma), where=xs >= mediana, color=ROSA, alpha=0.2, label=f"P(X > mediana) = {p_b:.2%}")
plt.axvline(mu, color=AZUL, ls="--", label=f"Média = {mu:.2f}%")
plt.axvline(mediana, color=ROSA, ls=":", label=f"Mediana = {mediana:.2f}%")
plt.title("Distribuição Normal - umidade do solo a 10 cm")
plt.xlabel("Umidade a 10 cm (%)")
plt.ylabel("Densidade")
plt.legend(fontsize=8)
salvar("01_normal.png")

# ----------------------------------------------------------------------------
# QUESTAO 3 - testes de hipotese Z para a media
# mu0 e sigma = media e desvio populacional da serie inteira
# a) amostra de 20 dias da estacao seca (ago-set): a umidade e menor que a media?
# b) amostra de 25 dias da estacao chuvosa (fev-abr): a umidade e maior que a media?
# ----------------------------------------------------------------------------
titulo("QUESTAO 3 - TESTES DE HIPOTESE Z")
mu0 = mu
seca = df[df["mes"].isin([8, 9])]["umidade_10cm"]
chuvosa = df[df["mes"].isin([2, 3, 4])]["umidade_10cm"]
am_a = seca.sample(n=20, random_state=SEMENTE)
am_b = chuvosa.sample(n=25, random_state=SEMENTE)


def teste_z(amostra, alfa, lado):
    n = len(amostra)
    xbarra = amostra.mean()
    erro = sigma / np.sqrt(n)
    zc = (xbarra - mu0) / erro
    if lado == "esquerda":
        zcrit = norm.ppf(alfa)
        rejeita = zc < zcrit
        p = norm.cdf(zc)
    else:
        zcrit = norm.ppf(1 - alfa)
        rejeita = zc > zcrit
        p = norm.sf(zc)
    return n, xbarra, erro, zc, zcrit, p, rejeita


res_a = teste_z(am_a, 0.06, "esquerda")
res_b = teste_z(am_b, 0.09, "direita")
for nome, (n, xb, erro, zc, zcrit, p, rej), h1 in [("a", res_a, "<"), ("b", res_b, ">")]:
    print(f"\n{nome}) H0: mu = {mu0:.4f} | H1: mu {h1} {mu0:.4f} | n = {n}")
    print(f"   media amostral = {xb:.4f} | erro padrao = {erro:.4f}")
    print(f"   Zc = {zc:.4f} | Z critico = {zcrit:.4f} | p-valor = {p:.6f}")
    print(f"   decisao: {'rejeita H0' if rej else 'nao rejeita H0'}")


def grafico_teste(res, alfa, lado, nome, rotulo):
    n, xb, erro, zc, zcrit, p, rej = res
    zs = np.linspace(-4, max(4, abs(zc) + 0.5), 500) if lado == "direita" else np.linspace(min(-4, -abs(zc) - 0.5), 4, 500)
    plt.figure(figsize=(8, 4))
    plt.plot(zs, norm.pdf(zs), color="black")
    if lado == "esquerda":
        plt.fill_between(zs, norm.pdf(zs), where=zs <= zcrit, color=ROSA, alpha=0.35, label=f"Região crítica (α = {alfa:.0%})")
    else:
        plt.fill_between(zs, norm.pdf(zs), where=zs >= zcrit, color=ROSA, alpha=0.35, label=f"Região crítica (α = {alfa:.0%})")
    plt.axvline(zcrit, color=ROSA, ls="--", label=f"Z crítico = {zcrit:.4f}")
    plt.axvline(zc, color=AZUL, lw=2, label=f"Z calculado = {zc:.4f}")
    plt.title(f"Teste Z unilateral à {lado} - {rotulo} (n = {n})")
    plt.xlabel("Z")
    plt.ylabel("Densidade")
    plt.legend(fontsize=8)
    salvar(nome)


grafico_teste(res_a, 0.06, "esquerda", "02_teste_z_a.png", "estação seca")
grafico_teste(res_b, 0.09, "direita", "03_teste_z_b.png", "estação chuvosa")

# ----------------------------------------------------------------------------
# QUESTAO 4 - analise bivariada: umidade a 20 cm (X) x umidade a 10 cm (Y)
# ----------------------------------------------------------------------------
titulo("QUESTAO 4 - ANALISE BIVARIADA (X = umidade_20cm, Y = umidade_10cm)")
X = df["umidade_20cm"]
Y = df["umidade_10cm"]
cov_xy = np.cov(X, Y, ddof=1)[0, 1]
r_xy = np.corrcoef(X, Y)[0, 1]
print(f"covariancia = {cov_xy:.4f} | correlacao de Pearson r = {r_xy:.4f}")

mod_s = sm.OLS(Y, sm.add_constant(X)).fit()
b0, b1 = mod_s.params["const"], mod_s.params["umidade_20cm"]
print(f"Y = {b0:.4f} + {b1:.4f} X")
print(f"R2 = {mod_s.rsquared:.4f} | F = {mod_s.fvalue:.2f} | p-valor F = {mod_s.f_pvalue:.3e}")
x_prev = 12.0
y_prev = b0 + b1 * x_prev
print(f"previsao: umidade a 20 cm = {x_prev}% -> umidade a 10 cm = {y_prev:.2f}%")

plt.figure(figsize=(8, 5))
plt.scatter(X, Y, s=10, color=AZUL, alpha=0.5, label="Dias observados")
xl = np.linspace(X.min(), X.max(), 100)
plt.plot(xl, b0 + b1 * xl, color=ROSA, lw=2, label=f"Ŷ = {b0:.2f} + {b1:.2f}X (R² = {mod_s.rsquared:.2f})")
plt.title("Dispersão: umidade a 20 cm x umidade a 10 cm")
plt.xlabel("Umidade a 20 cm (%)")
plt.ylabel("Umidade a 10 cm (%)")
plt.legend()
salvar("04_dispersao_bivariada.png")


def heatmap(matriz, nome, tit, tam):
    plt.figure(figsize=tam)
    im = plt.imshow(matriz.values, cmap="RdBu_r", vmin=-1, vmax=1)
    plt.colorbar(im, fraction=0.046)
    rot = list(matriz.columns)
    plt.xticks(range(len(rot)), rot, rotation=30, ha="right")
    plt.yticks(range(len(rot)), rot)
    for i in range(len(rot)):
        for j in range(len(rot)):
            v = matriz.values[i, j]
            plt.text(j, i, f"{v:.3f}", ha="center", va="center", color="white" if abs(v) > 0.6 else "black")
    plt.title(tit)
    salvar(nome)


heatmap(df[["umidade_20cm", "umidade_10cm"]].corr(), "05_correlacao_bivariada.png",
        "Correlação de Pearson - análise bivariada", (5, 4))

# ----------------------------------------------------------------------------
# QUESTAO 5 - regressao linear multipla
# Y = umidade_10cm | X1 = umidade_20cm, X2 = chuva_7d_mm, X3 = chuva_30d_mm
# ----------------------------------------------------------------------------
titulo("QUESTAO 5 - REGRESSAO LINEAR MULTIPLA")
vars_m = ["umidade_10cm", "umidade_20cm", "chuva_7d_mm", "chuva_30d_mm"]
print("Matriz de covariancia:")
print(df[vars_m].cov().round(4).to_string())
print("\nMatriz de correlacao de Pearson:")
print(df[vars_m].corr().round(4).to_string())

Xm = sm.add_constant(df[["umidade_20cm", "chuva_7d_mm", "chuva_30d_mm"]])
mod_m = sm.OLS(df["umidade_10cm"], Xm).fit()
c = mod_m.params
print(f"\nY = {c['const']:.4f} + {c['umidade_20cm']:.4f} X1 + {c['chuva_7d_mm']:.4f} X2 + {c['chuva_30d_mm']:.4f} X3")
print(mod_m.summary().tables[1])
print(f"R2 = {mod_m.rsquared:.4f} | R2 ajustado = {mod_m.rsquared_adj:.4f} | F = {mod_m.fvalue:.2f} | p-valor F = {mod_m.f_pvalue:.3e}")
novo = pd.DataFrame({"const": [1.0], "umidade_20cm": [8.0], "chuva_7d_mm": [20.0], "chuva_30d_mm": [40.0]})
prev_m = mod_m.predict(novo)[0]
print(f"previsao (X1 = 8%, X2 = 20 mm, X3 = 40 mm) -> umidade a 10 cm = {prev_m:.2f}%")

# matriz de dispersao (feita na mao para nao depender do seaborn)
rotulos = ["Umid. 10 cm", "Umid. 20 cm", "Chuva 7 d", "Chuva 30 d"]
k = len(vars_m)
fig, eixos = plt.subplots(k, k, figsize=(9, 9))
for i in range(k):
    for j in range(k):
        a = eixos[i, j]
        if i == j:
            a.hist(df[vars_m[i]], bins=25, color=ROSA, alpha=0.7)
        else:
            a.scatter(df[vars_m[j]], df[vars_m[i]], s=3, color=AZUL, alpha=0.4)
        if i == k - 1:
            a.set_xlabel(rotulos[j], fontsize=8)
        else:
            a.set_xticklabels([])
        if j == 0:
            a.set_ylabel(rotulos[i], fontsize=8)
        else:
            a.set_yticklabels([])
        a.tick_params(labelsize=7)
fig.suptitle("Matriz de dispersão - variáveis da regressão múltipla")
salvar("06_dispersao_multivariada.png")

heatmap(df[vars_m].corr(), "07_correlacao_multivariada.png",
        "Correlação de Pearson - análise multivariada", (7, 5.5))

# ----------------------------------------------------------------------------
# QUESTAO 6 - regressao logistica binaria
# Y = estresse_hidrico (1 se umidade a 10 cm <= 7%)
# X1 = umidade_20cm, X2 = chuva_7d_mm, X3 = chuva_30d_mm
# ----------------------------------------------------------------------------
titulo("QUESTAO 6 - REGRESSAO LOGISTICA BINARIA")
mod_l = sm.Logit(df["estresse_hidrico"], Xm).fit(disp=False)
cl = mod_l.params
print(f"logit(p) = {cl['const']:.4f} + ({cl['umidade_20cm']:.4f}) X1 + ({cl['chuva_7d_mm']:.4f}) X2 + ({cl['chuva_30d_mm']:.4f}) X3")
print(mod_l.summary().tables[1])
prob = mod_l.predict(Xm)
pred = (prob >= 0.5).astype(int)
mc = confusion_matrix(df["estresse_hidrico"], pred)
acc = accuracy_score(df["estresse_hidrico"], pred)
vn, fp, fn, vp = mc.ravel()
print(f"matriz de confusao: VN = {vn} | FP = {fp} | FN = {fn} | VP = {vp}")
print(f"acuracia = {acc:.4f} | sensibilidade = {vp / (vp + fn):.4f} | especificidade = {vn / (vn + fp):.4f}")
base_ref = 1 - df["estresse_hidrico"].mean()
print(f"acuracia de quem chuta sempre 'sem estresse' = {base_ref:.4f}")

casos = pd.DataFrame({"const": [1.0, 1.0], "umidade_20cm": [5.0, 10.0],
                      "chuva_7d_mm": [0.0, 15.0], "chuva_30d_mm": [5.0, 60.0]})
p_casos = mod_l.predict(casos)
for i, p in enumerate(p_casos):
    linha = casos.iloc[i]
    print(f"caso {i + 1}: X1 = {linha['umidade_20cm']}%, X2 = {linha['chuva_7d_mm']} mm, X3 = {linha['chuva_30d_mm']} mm "
          f"-> p = {p:.4f} -> classe {int(p >= 0.5)}")

plt.figure(figsize=(5, 4.2))
plt.imshow(mc, cmap="Reds")
for i in range(2):
    for j in range(2):
        plt.text(j, i, mc[i, j], ha="center", va="center", fontsize=16,
                 color="white" if mc[i, j] > mc.max() / 2 else "black")
plt.xticks([0, 1], ["Sem estresse (0)", "Estresse (1)"])
plt.yticks([0, 1], ["Sem estresse (0)", "Estresse (1)"])
plt.xlabel("Classe prevista")
plt.ylabel("Classe real")
plt.title(f"Matriz de confusão - acurácia {acc:.2%}")
salvar("08_matriz_confusao.png")

print(f"\nGraficos salvos em {PASTA_GRAFICOS}/")
