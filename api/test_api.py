# test_api.py
# Testes automaticos com unittest. Nao precisa subir o servidor.
# Grava numa pasta temporaria, entao nao mexe nos dados reais.
#
# Uso: python -m unittest test_api -v

import os
import shutil
import tempfile
import unittest

# a pasta temporaria tem que ser definida antes de importar a API
PASTA_TESTE = tempfile.mkdtemp(prefix="heimdall_teste_")
os.environ["DATA_DIR"] = PASTA_TESTE

from fastapi.testclient import TestClient  # noqa: E402

import app as api  # noqa: E402
import config  # noqa: E402

cliente = TestClient(api.app)


def leitura_base(**mudancas):
    leitura = {
        "id_sensor": "S01", "fazenda": "Sitio Boa Esperanca", "cultivo": "Tomate",
        "umidade": 50.0, "temperatura": 25.0, "umidade_ar": 50.0,
        "nivel_reservatorio": 80.0, "data_hora": "2026-11-12 22:15:00",
    }
    leitura.update(mudancas)
    return leitura


def enviar(**mudancas):
    return cliente.post("/leituras", json=leitura_base(**mudancas))


class TesteMotivos(unittest.TestCase):

    def setUp(self):
        shutil.rmtree(PASTA_TESTE, ignore_errors=True)

    def test_condicoes_estaveis(self):
        r = enviar()
        self.assertEqual(r.status_code, 201)
        self.assertEqual(r.json()["leitura"]["motivo"], "CONDICOES_ESTAVEIS")
        self.assertFalse(r.json()["leitura"]["bomba"])

    def test_solo_seco_na_janela_liga_bomba(self):
        r = enviar(umidade=28.0, data_hora="2026-11-12 22:15:00")
        self.assertEqual(r.json()["leitura"]["motivo"], "SOLO_SECO_JANELA_DESCONTO")
        self.assertTrue(r.json()["leitura"]["bomba"])

    def test_solo_seco_na_ponta_espera(self):
        r = enviar(umidade=28.0, data_hora="2026-11-12 19:00:00")
        self.assertEqual(r.json()["leitura"]["motivo"], "AGUARDANDO_JANELA_DESCONTO")
        self.assertFalse(r.json()["leitura"]["bomba"])

    def test_solo_critico_fora_da_janela_irriga(self):
        r = enviar(umidade=15.0, data_hora="2026-11-12 19:00:00")
        self.assertEqual(r.json()["leitura"]["motivo"], "IRRIGACAO_EMERGENCIAL_SOLO_CRITICO")
        self.assertTrue(r.json()["leitura"]["bomba"])

    def test_reservatorio_baixo_trava_bomba(self):
        r = enviar(umidade=15.0, nivel_reservatorio=12.0)
        self.assertEqual(r.json()["leitura"]["motivo"], "BLOQUEIO_RESERVATORIO_BAIXO")
        self.assertFalse(r.json()["leitura"]["bomba"])
        self.assertEqual(r.json()["leitura"]["status_reservatorio"], "ALERTA")

    def test_calor_extremo_risco_alto(self):
        r = enviar(temperatura=38.5)
        self.assertEqual(r.json()["leitura"]["motivo"], "ALERTA_CALOR_EXTREMO")
        self.assertEqual(r.json()["leitura"]["risco_perda_lote"], "ALTO")

    def test_reservatorio_ganha_do_calor(self):
        r = enviar(temperatura=38.5, nivel_reservatorio=10.0)
        self.assertEqual(r.json()["leitura"]["motivo"], "BLOQUEIO_RESERVATORIO_BAIXO")


class TesteLimiarPorCultivo(unittest.TestCase):

    def setUp(self):
        shutil.rmtree(PASTA_TESTE, ignore_errors=True)

    def test_mesma_umidade_cultivos_diferentes(self):
        # 32% e seco pro tomate (limite 35) mas ok pra soja (limite 30)
        tomate = enviar(cultivo="Tomate", umidade=32.0)
        soja = enviar(cultivo="Soja", umidade=32.0)
        self.assertEqual(tomate.json()["leitura"]["status_umidade"], "ALERTA")
        self.assertEqual(soja.json()["leitura"]["status_umidade"], "OK")

    def test_cultivo_desconhecido_usa_padrao(self):
        r = enviar(cultivo="Alface", umidade=32.0)
        self.assertEqual(r.status_code, 201)
        self.assertEqual(r.json()["leitura"]["status_umidade"], "ALERTA")
        self.assertIn("avisos", r.json())


class TesteHorarios(unittest.TestCase):

    def setUp(self):
        shutil.rmtree(PASTA_TESTE, ignore_errors=True)

    def motivo_seco(self, hora):
        r = enviar(umidade=28.0, data_hora="2026-11-12 " + hora)
        return r.json()["leitura"]["motivo"]

    def test_limites_da_ponta_e_da_janela(self):
        self.assertEqual(self.motivo_seco("16:59:00"), "AGUARDANDO_JANELA_DESCONTO")
        self.assertEqual(self.motivo_seco("17:00:00"), "AGUARDANDO_JANELA_DESCONTO")
        self.assertEqual(self.motivo_seco("21:29:00"), "AGUARDANDO_JANELA_DESCONTO")
        self.assertEqual(self.motivo_seco("21:30:00"), "SOLO_SECO_JANELA_DESCONTO")
        self.assertEqual(self.motivo_seco("23:59:00"), "SOLO_SECO_JANELA_DESCONTO")
        self.assertEqual(self.motivo_seco("00:00:00"), "SOLO_SECO_JANELA_DESCONTO")
        self.assertEqual(self.motivo_seco("05:59:00"), "SOLO_SECO_JANELA_DESCONTO")
        self.assertEqual(self.motivo_seco("06:00:00"), "AGUARDANDO_JANELA_DESCONTO")


class TesteValidacao(unittest.TestCase):

    def setUp(self):
        shutil.rmtree(PASTA_TESTE, ignore_errors=True)

    def test_valores_fora_da_faixa(self):
        self.assertEqual(enviar(umidade=150.0).status_code, 422)
        self.assertEqual(enviar(umidade=-1.0).status_code, 422)
        self.assertEqual(enviar(temperatura=70.0).status_code, 422)
        self.assertEqual(enviar(nivel_reservatorio=101.0).status_code, 422)

    def test_tipos_errados(self):
        self.assertEqual(enviar(umidade="28.4").status_code, 422)
        self.assertEqual(enviar(bomba="sim").status_code, 422)
        self.assertEqual(enviar(motivo="QUALQUER").status_code, 422)
        self.assertEqual(enviar(data_hora="12/11/2026").status_code, 422)

    def test_campo_faltando(self):
        leitura = leitura_base()
        del leitura["umidade"]
        self.assertEqual(cliente.post("/leituras", json=leitura).status_code, 422)

    def test_corpo_quebrado(self):
        r = cliente.post("/leituras", content=b"{quebrado", headers={"content-type": "application/json"})
        self.assertEqual(r.status_code, 422)

    def test_leitura_invalida_nao_grava(self):
        enviar(umidade=150.0)
        self.assertFalse(os.path.exists(config.ARQUIVO_CSV))

    def test_acento_e_removido(self):
        r = enviar(fazenda="Sítio Boa Esperança")
        self.assertEqual(r.json()["leitura"]["fazenda"], "Sitio Boa Esperanca")


class TesteDivergencia(unittest.TestCase):

    def setUp(self):
        shutil.rmtree(PASTA_TESTE, ignore_errors=True)

    def test_dispositivo_mandou_decisao_errada(self):
        # ESP32 diz que ta tudo ok, mas o reservatorio ta em 10%
        r = enviar(nivel_reservatorio=10.0, motivo="CONDICOES_ESTAVEIS", bomba=True)
        self.assertTrue(r.json()["divergencia_dispositivo"])
        self.assertFalse(r.json()["leitura"]["bomba"])

    def test_dispositivo_concorda(self):
        r = enviar(motivo="CONDICOES_ESTAVEIS", bomba=False)
        self.assertFalse(r.json()["divergencia_dispositivo"])


class TesteConsultas(unittest.TestCase):

    def setUp(self):
        shutil.rmtree(PASTA_TESTE, ignore_errors=True)

    def test_get_sem_dados(self):
        r = cliente.get("/leituras")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["total"], 0)

    def test_indicadores_sem_dados(self):
        r = cliente.get("/indicadores")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["total_leituras"], 0)

    def test_get_com_filtro_e_limite(self):
        enviar(id_sensor="S01")
        enviar(id_sensor="S02")
        enviar(id_sensor="S01")
        self.assertEqual(cliente.get("/leituras?id_sensor=S01").json()["total"], 2)
        self.assertEqual(cliente.get("/leituras?limite=1").json()["total"], 1)

    def test_indicadores_calculados(self):
        enviar(umidade=28.0, data_hora="2026-11-12 22:15:00")  # bomba na janela
        enviar(temperatura=38.0)                                # calor, risco alto
        enviar(umidade=60.0)                                    # estavel
        r = cliente.get("/indicadores").json()
        self.assertEqual(r["total_leituras"], 3)
        self.assertEqual(r["media_umidade_solo"], round((28 + 50 + 60) / 3, 2))
        self.assertEqual(r["temperatura_maxima"]["valor"], 38.0)
        self.assertEqual(r["total_alertas_criticos"], 1)
        self.assertEqual(r["pct_bombeamento_na_janela"], 100.0)
        self.assertGreater(r["economia"]["economia_estimada_reais"], 0)

    def test_linha_corrompida_e_ignorada(self):
        enviar()
        with open(config.ARQUIVO_CSV, "a", encoding="utf-8") as arq:
            arq.write("lixo,quebrado\n")
        r = cliente.get("/leituras").json()
        self.assertEqual(r["total"], 1)
        self.assertEqual(r["linhas_ignoradas"], 1)


class TesteEconomia(unittest.TestCase):

    def test_formula_confere_com_a_ficha(self):
        # com f = 0,90 a conta cai de 224,40 pra 57,73
        import indicadores
        resultado = indicadores.calcular_economia(0.90)
        self.assertEqual(resultado["conta_mensal_sem_sistema_reais"], 224.40)
        self.assertEqual(resultado["conta_mensal_com_sistema_reais"], 57.73)
        self.assertEqual(resultado["economia_estimada_reais"], 166.67)


def tearDownModule():
    # apaga a pasta temporaria no final
    shutil.rmtree(PASTA_TESTE, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
