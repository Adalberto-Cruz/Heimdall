# test_ia_seguranca.py
# Testes das protecoes de IA. Uso: python -m unittest test_ia_seguranca -v

import json
import os
import shutil
import tempfile
import unittest

from PIL import Image

import ia_seguranca

LEITURA_OK = {
    "id_sensor": "S01", "fazenda": "Sitio Boa Esperanca", "cultivo": "Tomate", "umidade": 40.0,
    "temperatura": 25.0, "umidade_ar": 50.0, "nivel_reservatorio": 70.0, "status_umidade": "OK",
    "status_temperatura": "OK", "status_reservatorio": "OK", "bomba": False,
    "risco_perda_lote": "BAIXO", "motivo": "CONDICOES_ESTAVEIS", "data_hora": "2026-11-12 06:00:00",
}


class TesteMetadados(unittest.TestCase):

    def setUp(self):
        self.pasta = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.pasta, ignore_errors=True)

    def caminho(self, nome):
        return os.path.join(self.pasta, nome)

    def test_remove_gps_e_exif(self):
        imagem = Image.new("RGB", (32, 32), (0, 120, 0))
        exif = Image.Exif()
        exif[0x010F] = "Celular"
        exif[0x8825] = {1: "S", 2: (9.0, 23.0, 30.0)}
        imagem.save(self.caminho("a.jpg"), exif=exif)
        r = ia_seguranca.remover_metadados(self.caminho("a.jpg"), self.caminho("b.jpg"))
        self.assertTrue(r["antes"]["tem_gps"])
        self.assertFalse(r["depois"]["tem_gps"])
        self.assertEqual(r["depois"]["campos_exif"], 0)

    def test_png_tambem_funciona(self):
        Image.new("RGB", (16, 16)).save(self.caminho("a.png"))
        r = ia_seguranca.remover_metadados(self.caminho("a.png"), self.caminho("b.png"))
        self.assertFalse(r["depois"]["tem_gps"])

    def test_arquivo_inexistente(self):
        with self.assertRaises(ia_seguranca.ImagemInvalida):
            ia_seguranca.remover_metadados(self.caminho("nao_existe.jpg"), self.caminho("b.jpg"))

    def test_arquivo_vazio(self):
        open(self.caminho("vazio.jpg"), "w").close()
        with self.assertRaises(ia_seguranca.ImagemInvalida):
            ia_seguranca.remover_metadados(self.caminho("vazio.jpg"), self.caminho("b.jpg"))

    def test_texto_com_extensao_jpg(self):
        with open(self.caminho("falso.jpg"), "w") as arq:
            arq.write("nao sou imagem")
        with self.assertRaises(ia_seguranca.ImagemInvalida):
            ia_seguranca.remover_metadados(self.caminho("falso.jpg"), self.caminho("b.jpg"))

    def test_formato_nao_aceito(self):
        Image.new("RGB", (16, 16)).save(self.caminho("a.gif"))
        with self.assertRaises(ia_seguranca.ImagemInvalida):
            ia_seguranca.remover_metadados(self.caminho("a.gif"), self.caminho("b.gif"))


class TesteDiagnostico(unittest.TestCase):

    def test_confianca_baixa_vai_pro_tecnico(self):
        d = ia_seguranca.decidir_diagnostico("Tomato___Early_blight", 0.61)
        self.assertEqual(d["acao"], "ACIONAR_TECNICO")
        self.assertFalse(d["decisao_automatica"])

    def test_limite_exato_e_aceito(self):
        self.assertEqual(ia_seguranca.decidir_diagnostico("Tomato___Late_blight", 0.75)["acao"], "ALERTA_DOENCA")

    def test_saudavel(self):
        self.assertEqual(ia_seguranca.decidir_diagnostico("Tomato___healthy", 0.9)["acao"], "PLANTA_SAUDAVEL")

    def test_entradas_invalidas(self):
        for classe, conf in [("", 0.9), ("x", 1.5), ("x", -0.1), ("x", float("nan")), ("x", "0.9"), ("x", True)]:
            with self.assertRaises(ValueError):
                ia_seguranca.decidir_diagnostico(classe, conf)


class TesteFiltroTreino(unittest.TestCase):

    def setUp(self):
        self.pasta = tempfile.mkdtemp()
        self.entrada = os.path.join(self.pasta, "in.jsonl")
        self.saida = os.path.join(self.pasta, "out.jsonl")

    def tearDown(self):
        shutil.rmtree(self.pasta, ignore_errors=True)

    def gravar(self, linhas):
        with open(self.entrada, "w", encoding="utf-8") as arq:
            for linha in linhas:
                arq.write((linha if isinstance(linha, str) else json.dumps(linha)) + "\n")

    def test_so_leitura_limpa_passa(self):
        self.gravar([
            LEITURA_OK,
            dict(LEITURA_OK, umidade=250.0),
            dict(LEITURA_OK, fazenda="=cmd"),
            dict(LEITURA_OK, motivo="INVENTADO"),
            dict(LEITURA_OK, extra=1),
            dict(LEITURA_OK, bomba="sim"),
            "{quebrado",
            "",
        ])
        r = ia_seguranca.filtrar_jsonl_para_treino(self.entrada, self.saida)
        self.assertEqual(r["aceitas"], 1)
        self.assertEqual(r["descartadas"], 6)
        with open(self.saida, encoding="utf-8") as arq:
            self.assertEqual(len(arq.readlines()), 1)

    def test_arquivo_inexistente(self):
        with self.assertRaises(FileNotFoundError):
            ia_seguranca.filtrar_jsonl_para_treino(os.path.join(self.pasta, "nada.jsonl"), self.saida)

    def test_jsonl_oficial_passa_inteiro(self):
        oficial = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "dados", "leituras_sensores.jsonl")
        if not os.path.exists(oficial):
            self.skipTest("arquivo oficial nao encontrado")
        r = ia_seguranca.filtrar_jsonl_para_treino(oficial, self.saida)
        self.assertEqual(r["descartadas"], 0)
        self.assertEqual(r["aceitas"], 50)


if __name__ == "__main__":
    unittest.main()
