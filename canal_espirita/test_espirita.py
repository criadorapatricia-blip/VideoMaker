"""Testes sem APIs, chaves ou criação de vídeo pago."""
import importlib.util
import json
import sys
import tempfile
import types
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('espirita_em_teste', ROOT / 'gerar_video.py')
g = importlib.util.module_from_spec(spec)
with tempfile.TemporaryDirectory() as work:
    g.__file__ = str(Path(work) / 'gerar_video.py')
    with patch.dict(sys.modules, {'config': types.SimpleNamespace(ANTHROPIC_API_KEY='teste')}):
        spec.loader.exec_module(g)


def dados():
    return {'tema': 'Caridade', 'plano_cenas': [
        {'narracao': f'Reflexão {i}.', 'visual': 'a quiet garden', 'corte': 'suave'}
        for i in range(6)]}


class EspiritaTest(unittest.TestCase):
    def test_data_em_portugues(self):
        ctx = g.contexto_do_dia(datetime(2026, 10, 23))
        self.assertEqual(ctx['abertura'], 'Hoje é sexta-feira, 23 de outubro de 2026.')
        self.assertEqual(ctx['data'], '2026-10-23')

    def test_data_bissexta(self):
        self.assertEqual(g.contexto_do_dia(datetime(2024, 2, 29))['abertura'],
                         'Hoje é quinta-feira, 29 de fevereiro de 2024.')

    def test_abertura_nao_duplica_e_preserva_seis_cenas(self):
        ctx = g.contexto_do_dia(datetime(2026, 10, 23))
        pronto = g.aplicar_data(g.preparar_roteiro(dados()), ctx)
        repetido = g.aplicar_data(pronto, ctx)
        self.assertEqual(len(pronto['plano_cenas']), 6)
        self.assertEqual(repetido['roteiro'].count(ctx['abertura']), 1)
        g.validar_plano_cenas(pronto)

    def test_data_antiga_e_rejeitada(self):
        pronto = g.aplicar_data(g.preparar_roteiro(dados()), g.contexto_do_dia(datetime(2026, 10, 23)))
        with self.assertRaisesRegex(ValueError, 'data antiga'):
            g.aplicar_data(pronto, g.contexto_do_dia(datetime(2026, 10, 24)))

    def test_logo_ausente_nao_faz_download(self):
        with patch.object(g.requests, 'get') as rede:
            g.preparar_logo_faixa()
            rede.assert_not_called()

    def test_resposta_ia_recebe_data_deterministica(self):
        resposta = types.SimpleNamespace(content=[types.SimpleNamespace(type='text', text=json.dumps(dados()))], stop_reason='end_turn')
        create = Mock(return_value=resposta)
        client = types.SimpleNamespace(messages=types.SimpleNamespace(create=create))
        with tempfile.TemporaryDirectory() as work, \
             patch.object(g.anthropic, 'Anthropic', return_value=client), \
             patch.object(g, 'carregar_temas_usados', return_value=[]), \
             patch.object(g, 'contexto_do_dia', return_value=g.contexto_do_dia(datetime(2026, 10, 23))):
            pronto = g.gerar_roteiro(Path(work))
            self.assertTrue(pronto['roteiro'].startswith('Hoje é sexta-feira, 23 de outubro de 2026.'))
            self.assertEqual(create.call_count, 1)
            self.assertTrue((Path(work) / 'roteiro_resposta.txt').exists())
            self.assertIn('AUTORAL', create.call_args.kwargs['messages'][0]['content'])

    def test_limite_imagens_bloqueia_cobranca(self):
        with patch.object(g, 'gerar_imagem_com_alternativa') as api:
            with self.assertRaises(ValueError):
                g.montar_banco_de_imagens(['garden'] * 7, Path('/tmp'))
            api.assert_not_called()

    def test_config_masculina_e_stability(self):
        spec_config = importlib.util.spec_from_file_location('config_teste', ROOT / 'config_exemplo.py')
        config = importlib.util.module_from_spec(spec_config)
        spec_config.loader.exec_module(config)
        self.assertEqual(config.VOZ, 'pt-BR-AntonioNeural')
        self.assertEqual(config.VOZ_RATE, '-8%')
        self.assertTrue(config.USAR_IMAGENS_IA)
        self.assertFalse(config.USAR_ELEVENLABS)


if __name__ == '__main__':
    unittest.main()
