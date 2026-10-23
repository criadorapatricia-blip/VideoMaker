import importlib.util
import json
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('psico_em_teste', ROOT / 'gerar_video.py')
g = importlib.util.module_from_spec(spec)
with tempfile.TemporaryDirectory() as work:
    g.__file__ = str(Path(work) / 'gerar_video.py')
    with patch.dict(sys.modules, {'config': types.SimpleNamespace(ANTHROPIC_API_KEY='teste')}):
        spec.loader.exec_module(g)
g.BASE_DIR = ROOT


def dados():
    return {'tema': 'Começar uma tarefa', 'base_id': 'procrastinacao', 'plano_cenas': [
        {'narracao': f'Trecho {i}.', 'visual': 'adult at a desk', 'corte': 'suave'}
        for i in range(6)]}


class PsicologiaTest(unittest.TestCase):
    def test_catalogo_tem_fontes_e_identificadores_unicos(self):
        bases = g.carregar_bases()
        self.assertEqual(len({b['id'] for b in bases}), len(bases))
        for b in bases:
            self.assertTrue(b['base_conceitual'])
            self.assertTrue(b['fontes'][0]['url'].startswith('https://doi.org/'))

    def test_fontes_do_modelo_sao_substituidas_pelo_catalogo(self):
        resposta = dados()
        resposta['fontes'] = [{'url': 'https://inventada.invalid'}]
        pronto = g.preparar_psicologia(resposta)
        self.assertEqual(pronto['fontes'], g.carregar_bases()[0]['fontes'])
        self.assertEqual(len(pronto['plano_cenas']), 6)

    def test_base_inexistente_nao_e_aceita(self):
        resposta = dados()
        resposta['base_id'] = 'inventada'
        with self.assertRaisesRegex(ValueError, 'base_id'):
            g.preparar_psicologia(resposta)

    def test_diagnostico_direto_e_rejeitado(self):
        resposta = dados()
        resposta['plano_cenas'][0]['narracao'] = 'Você tem depressão.'
        with self.assertRaisesRegex(ValueError, 'diagnóstica'):
            g.preparar_psicologia(resposta)

    def test_revisao_salva_texto_e_referencias(self):
        pronto = g.preparar_psicologia(dados())
        with tempfile.TemporaryDirectory() as work:
            g.salvar_revisao(pronto, Path(work))
            texto = (Path(work) / 'revisao_roteiro.md').read_text()
            self.assertIn(pronto['roteiro'], texto)
            self.assertIn('10.1037/0033-2909.133.1.65', texto)

    def test_somente_roteiro_nao_solicita_voz_ou_imagens(self):
        pronto = g.preparar_psicologia(dados())
        with tempfile.TemporaryDirectory() as work, \
             patch.object(g, 'SAIDA_DIR', Path(work)), \
             patch.object(sys, 'argv', ['gerar_video.py', '--somente-roteiro']), \
             patch.object(g, 'gerar_roteiro', return_value=pronto) as roteiro, \
             patch.object(g, 'gerar_narracao_cenas') as voz, \
             patch.object(g, 'montar_banco_de_imagens') as imagens:
            g.main()
            roteiro.assert_called_once()
            voz.assert_not_called()
            imagens.assert_not_called()
            self.assertEqual(len(list(Path(work).rglob('revisao_roteiro.md'))), 1)

    def test_logo_ausente_nao_busca_marca_do_suspense(self):
        with patch.object(g.requests, 'get') as rede:
            g.preparar_logo_faixa()
            rede.assert_not_called()

    def test_resposta_ia_recebe_base_local(self):
        resposta = types.SimpleNamespace(content=[types.SimpleNamespace(type='text', text=json.dumps(dados()))], stop_reason='end_turn')
        create = Mock(return_value=resposta)
        client = types.SimpleNamespace(messages=types.SimpleNamespace(create=create))
        with tempfile.TemporaryDirectory() as work, \
             patch.object(g.anthropic, 'Anthropic', return_value=client), \
             patch.object(g, 'carregar_temas_usados', return_value=[]):
            pronto = g.gerar_roteiro(Path(work))
            self.assertEqual(pronto['base_id'], 'procrastinacao')
            self.assertEqual(create.call_count, 1)
            self.assertIn('Não diagnostique', create.call_args.kwargs['messages'][0]['content'])

    def test_setima_imagem_nao_chama_api(self):
        with patch.object(g, 'gerar_imagem_com_alternativa') as api:
            with self.assertRaises(ValueError):
                g.montar_banco_de_imagens(['desk'] * 7, Path('/tmp'))
            api.assert_not_called()


if __name__ == '__main__':
    unittest.main()
