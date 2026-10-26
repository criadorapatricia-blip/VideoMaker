import importlib.util
import json
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('video_cidades_teste', ROOT / 'gerar_video.py')
g = importlib.util.module_from_spec(spec)
with tempfile.TemporaryDirectory() as work:
    g.__file__ = str(Path(work) / 'gerar_video.py')
    with patch.dict(sys.modules, {'config': types.SimpleNamespace(ANTHROPIC_API_KEY='teste')}):
        spec.loader.exec_module(g)


def roteiro(primeira='Eu estava sozinho no escritório.'):
    return {'tema': 'O plantão', 'plano_cenas': [
        {'narracao': primeira if i == 0 else f'Trecho {i}.', 'visual': 'empty office', 'corte': 'seco'}
        for i in range(6)]}


class CidadesTest(unittest.TestCase):
    def test_catalogo_cobre_todas_as_ufs_sem_duplicatas(self):
        ufs = {'AC','AL','AP','AM','BA','CE','DF','ES','GO','MA','MT','MS','MG','PA',
               'PB','PR','PE','PI','RJ','RN','RS','RO','RR','SC','SP','SE','TO'}
        self.assertEqual({c.rsplit('/', 1)[1] for c in g.CAPITAIS_BRASILEIRAS}, ufs)
        self.assertEqual(len(g.CAPITAIS_BRASILEIRAS), 27)
        todas = g.CAPITAIS_BRASILEIRAS + g.CIDADES_GRANDES_BRASILEIRAS
        self.assertEqual(len(todas), len(set(todas)))

    def test_sorteio_respeita_pesos_e_remove_recentes(self):
        recentes = ['São Paulo/SP', 'Campinas/SP']
        with patch.object(g, 'carregar_cidades_usadas', return_value=recentes), \
             patch.object(g.random, 'choices', side_effect=lambda grupos, **kwargs: [grupos[0]]) as escolha:
            cidade = g.escolher_cidade_brasileira()
            grupos = escolha.call_args.args[0]
            self.assertEqual(escolha.call_args.kwargs['weights'], [55,45])
            self.assertNotIn('São Paulo/SP', grupos[0])
            self.assertNotIn('Campinas/SP', grupos[1])
            self.assertIn(f"{cidade['nome']}/{cidade['uf']}", grupos[0])

    def test_nao_repete_as_duas_cidades_ja_testadas_no_primeiro_sorteio(self):
        with tempfile.TemporaryDirectory() as work, patch.object(g, 'CIDADES_USADAS_PATH', Path(work)/'cidades.json'):
            self.assertEqual(g.carregar_cidades_usadas(), ['Ribeirão Preto/SP', 'Belo Horizonte/MG'])
            for _ in range(30):
                cidade = g.escolher_cidade_brasileira()
                self.assertNotIn(f"{cidade['nome']}/{cidade['uf']}", g.carregar_cidades_usadas())

    def test_prefixo_preserva_texto_e_sincroniza_roteiro(self):
        pronto = g.aplicar_cidade_ao_roteiro(roteiro(), {'nome':'Natal','uf':'RN'})
        self.assertTrue(pronto['roteiro'].startswith('Em Natal, tudo começou assim.'))
        self.assertIn('Eu estava sozinho no escritório.', pronto['roteiro'])
        self.assertEqual(len(pronto['plano_cenas']), 6)
        g.validar_plano_cenas(pronto)

    def test_cidade_ja_presente_na_primeira_frase_nao_duplica(self):
        original = 'Em Belo Horizonte, aceitei um plantão.'
        pronto = g.aplicar_cidade_ao_roteiro(roteiro(original), {'nome':'Belo Horizonte','uf':'MG'})
        self.assertEqual(pronto['plano_cenas'][0]['narracao'], original)

    def test_historico_invalido_bloqueia_antes_da_api(self):
        with tempfile.TemporaryDirectory() as work:
            path = Path(work)/'cidades.json'
            path.write_text('{"formato":"errado"}')
            with patch.object(g, 'CIDADES_USADAS_PATH', path), patch.object(g.anthropic, 'Anthropic') as api:
                with self.assertRaises(ValueError):
                    g.gerar_roteiro(Path(work))
                api.assert_not_called()
                self.assertEqual(path.read_text(), '{"formato":"errado"}')

    def test_resposta_valida_registra_cidade_e_ficcao(self):
        resposta = types.SimpleNamespace(content=[types.SimpleNamespace(type='text', text=json.dumps(roteiro()))], stop_reason='end_turn')
        chamada = Mock(return_value=resposta)
        client = types.SimpleNamespace(messages=types.SimpleNamespace(create=chamada))
        with tempfile.TemporaryDirectory() as work:
            path = Path(work)/'cidades.json'
            with patch.object(g, 'CIDADES_USADAS_PATH', path), \
                 patch.object(g, 'escolher_cidade_brasileira', return_value={'nome':'Natal','uf':'RN'}), \
                 patch.object(g, 'carregar_temas_usados', return_value=[]), \
                 patch.object(g.anthropic, 'Anthropic', return_value=client):
                pronto = g.gerar_roteiro(Path(work))
            self.assertEqual(json.loads(path.read_text())[-1], 'Natal/RN')
            self.assertEqual(pronto['cidade'], {'nome':'Natal','uf':'RN'})
            self.assertEqual(pronto['aviso_ficcao'], 'História fictícia ambientada no Brasil.')
            self.assertEqual(chamada.call_count, 1)
            self.assertIn('Natal', chamada.call_args.kwargs['messages'][0]['content'])

    def test_resposta_invalida_nao_reserva_cidade_nem_repete_api(self):
        resposta = types.SimpleNamespace(content=[types.SimpleNamespace(type='text', text='{"tema":"Sem cenas"}')], stop_reason='end_turn')
        chamada = Mock(return_value=resposta)
        client = types.SimpleNamespace(messages=types.SimpleNamespace(create=chamada))
        with tempfile.TemporaryDirectory() as work:
            path = Path(work)/'cidades.json'
            with patch.object(g, 'CIDADES_USADAS_PATH', path), \
                 patch.object(g, 'carregar_temas_usados', return_value=[]), \
                 patch.object(g.anthropic, 'Anthropic', return_value=client):
                with self.assertRaises(ValueError):
                    g.gerar_roteiro(Path(work))
            self.assertFalse(path.exists())
            self.assertTrue((Path(work)/'roteiro_resposta.txt').exists())
            self.assertEqual(chamada.call_count, 1)


if __name__ == '__main__':
    unittest.main()
