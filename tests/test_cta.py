import importlib.util
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('video_cta_teste', ROOT / 'gerar_video.py')
g = importlib.util.module_from_spec(spec)
with tempfile.TemporaryDirectory() as work:
    g.__file__ = str(Path(work) / 'gerar_video.py')
    with patch.dict(sys.modules, {'config': types.SimpleNamespace()}):
        spec.loader.exec_module(g)


def roteiro(titulo='A chave do último andar'):
    return {'tema': titulo, 'plano_cenas': [
        {'narracao': 'Aceitei um plantão.' if i == 0 else f'Trecho {i}.',
         'visual': 'empty office', 'corte': 'seco'} for i in range(6)]}


class CTATest(unittest.TestCase):
    def test_ordem_titulo_cta_historia_sem_aumentar_imagens(self):
        pronto = g.aplicar_abertura_cta(roteiro())
        self.assertTrue(pronto['roteiro'].startswith(
            'A chave do último andar. Já segue o canal para ver mais histórias como essa. Aceitei um plantão.'))
        self.assertEqual(len(pronto['plano_cenas']), 6)
        self.assertEqual(pronto['historia_sem_abertura'], ' '.join(
            c['narracao'] for c in roteiro()['plano_cenas']))
        g.validar_plano_cenas(pronto)

    def test_reaproveitamento_nao_duplica_abertura(self):
        pronto = g.aplicar_abertura_cta(roteiro())
        repetido = g.aplicar_abertura_cta(pronto)
        self.assertEqual(pronto['roteiro'], repetido['roteiro'])
        self.assertEqual(repetido['roteiro'].count(g.CTA_SUSPENSE), 1)

    def test_titulo_longo_recebe_alternativa_curta_e_preserva_original(self):
        original = 'A história daquela noite em que descobri um segredo no prédio'
        pronto = g.aplicar_abertura_cta(roteiro(original))
        self.assertLessEqual(len(pronto['tema'].split()), 7)
        self.assertEqual(pronto['titulo_original'], original)

    def test_cidade_no_titulo_nao_e_acrescentada_novamente_ao_gancho(self):
        cidade = {'nome': 'Curitiba', 'uf': 'PR'}
        pronto = g.aplicar_cidade_ao_roteiro(roteiro('O último plantão em Curitiba'), cidade)
        pronto = g.aplicar_abertura_cta(pronto)
        self.assertEqual(pronto['roteiro'].count('Curitiba'), 1)
        self.assertIn('Aceitei um plantão.', pronto['roteiro'])

    def test_titulo_encurtado_nao_perde_cidade(self):
        cidade = {'nome': 'Curitiba', 'uf': 'PR'}
        pronto = g.aplicar_cidade_ao_roteiro(roteiro('A história da noite em que encontrei um segredo em Curitiba'), cidade)
        pronto = g.aplicar_abertura_cta(pronto)
        self.assertIn('Curitiba', pronto['roteiro'])
        self.assertLessEqual(len(pronto['tema'].split()), 7)

    def test_abertura_alterada_no_json_nao_e_aceita_silenciosamente(self):
        pronto = g.aplicar_abertura_cta(roteiro())
        pronto['abertura_cta']['texto'] = 'Outro texto.'
        with self.assertRaisesRegex(ValueError, 'abertura salva'):
            g.aplicar_abertura_cta(pronto)

    def test_titulo_com_subtitulo_aproveita_parte_curta(self):
        pronto = g.aplicar_abertura_cta(roteiro('A chave perdida: uma história sobre o último plantão no prédio'))
        self.assertEqual(pronto['tema'], 'A chave perdida')


if __name__ == '__main__':
    unittest.main()
