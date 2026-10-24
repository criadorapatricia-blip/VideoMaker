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
        self.assertEqual(config.VOZ_RATE, '-20%')
        self.assertTrue(config.USAR_IMAGENS_IA)
        self.assertFalse(config.USAR_ELEVENLABS)

    def test_fala_longa_nao_e_acelerada(self):
        with patch.object(g, 'obter_duracao_segundos', return_value=75), \
             patch.object(g.subprocess, 'run') as ffmpeg:
            with self.assertRaisesRegex(ValueError, 'Não será acelerada'):
                g.ajustar_duracao_narracao(Path('voz.wav'), [], Path('/tmp'))
            ffmpeg.assert_not_called()

    def test_pausas_preservam_amostras_originais(self):
        import wave
        taxa = 24000
        primeiro = b'\x01\x00' * (15 * taxa)
        segundo = b'\x02\x00' * (15 * taxa)
        cenas = [{'inicio': 0, 'duracao': 15}, {'inicio': 15, 'duracao': 15}]
        with tempfile.TemporaryDirectory() as work:
            pasta = Path(work)
            original = pasta / 'voz.wav'
            with wave.open(str(original), 'wb') as f:
                f.setnchannels(1)
                f.setsampwidth(2)
                f.setframerate(taxa)
                f.writeframes(primeiro + segundo)
            with patch.object(g, 'obter_duracao_segundos', return_value=30):
                destino, timeline = g.ajustar_duracao_narracao(original, cenas, pasta)
            with wave.open(str(destino), 'rb') as f:
                self.assertEqual(f.getnframes() / taxa, 64)
                resultado = f.readframes(f.getnframes())
            self.assertEqual(resultado[:len(primeiro)], primeiro)
            inicio_segundo = round(timeline[1]['inicio'] * taxa) * 2
            self.assertEqual(resultado[inicio_segundo:inicio_segundo+len(segundo)], segundo)
            self.assertEqual(timeline[0]['duracao_fala'], 15)
            self.assertEqual(sum(c['duracao'] for c in timeline), 64)

    def test_legenda_some_antes_da_pausa(self):
        with tempfile.TemporaryDirectory() as work:
            path = Path(work) / 'legenda.ass'
            g.gerar_legenda_por_tempo('Uma reflexão.', 10, path, segmentos=[
                {'narracao': 'Uma reflexão.', 'inicio': 0, 'duracao': 10, 'duracao_fala': 6}])
            self.assertIn('0:00:00.00,0:00:06.00', path.read_text())

    def test_edge_recebe_voz_mais_lenta_e_grave(self):
        import asyncio
        class AudioSimulado:
            async def stream(self):
                yield {'type': 'audio', 'data': b'audio simulado'}
        with tempfile.TemporaryDirectory() as work, \
             patch.object(g.edge_tts, 'Communicate', return_value=AudioSimulado()) as tts:
            asyncio.run(g._gerar_voz_edge_tts_async('Uma reflexão.', Path(work) / 'teste.mp3'))
            self.assertEqual(tts.call_args.kwargs['rate'], '-20%')
            self.assertEqual(tts.call_args.kwargs['pitch'], '-12Hz')

    def test_texto_longo_e_compactado_em_frases_completas(self):
        resposta = dados()
        for cena in resposta['plano_cenas']:
            cena['narracao'] = ' '.join(['Precisamos aprender a reconhecer nossas escolhas e ajudar o próximo.'] * 4)
        pronto = g.aplicar_data(g.preparar_roteiro(resposta), g.contexto_do_dia(datetime(2026, 10, 24)))
        curto = g.limitar_texto_devocional(pronto)
        self.assertLessEqual(len(curto['roteiro'].split()), 70)
        self.assertEqual(len(curto['plano_cenas']), 6)
        self.assertTrue(curto['roteiro'].startswith('Hoje é sábado, 24 de outubro de 2026.'))
        self.assertTrue(all(c['narracao'].endswith('.') for c in curto['plano_cenas']))
        g.validar_plano_cenas(curto)

    def test_texto_curto_preserva_conteudo(self):
        pronto = g.aplicar_data(g.preparar_roteiro(dados()), g.contexto_do_dia(datetime(2026, 10, 24)))
        self.assertEqual(g.limitar_texto_devocional(pronto), pronto)

    def test_duracao_longa_tenta_uma_unica_voz_menor(self):
        resposta = dados()
        for cena in resposta['plano_cenas']:
            cena['narracao'] = 'Escolho agir com bondade e aprender com minhas dificuldades.'
        pronto = g.aplicar_data(g.preparar_roteiro(resposta), g.contexto_do_dia(datetime(2026, 10, 24)))
        with tempfile.TemporaryDirectory() as work, \
             patch.object(g, 'gerar_narracao_cenas', return_value=(Path('voz.wav'), [])) as voz, \
             patch.object(g, 'obter_duracao_segundos', return_value=111.1), \
             patch.object(g.config, 'USAR_ELEVENLABS', False, create=True), \
             patch.object(g.anthropic, 'Anthropic') as api:
            curto, _, _ = g.narrar_com_limite(pronto, Path(work))
            self.assertEqual(voz.call_count, 2)
            self.assertLess(len(curto['roteiro'].split()), len(pronto['roteiro'].split()))
            self.assertTrue((Path(work) / 'roteiro_antes_ajuste.json').exists())
            api.assert_not_called()

    def test_elevenlabs_nao_recebe_nova_chamada_paga_automatica(self):
        pronto = g.aplicar_data(g.preparar_roteiro(dados()), g.contexto_do_dia(datetime(2026, 10, 24)))
        with tempfile.TemporaryDirectory() as work, \
             patch.object(g, 'gerar_narracao_cenas', return_value=(Path('voz.wav'), [])) as voz, \
             patch.object(g, 'obter_duracao_segundos', return_value=111.1), \
             patch.object(g.config, 'USAR_ELEVENLABS', True, create=True):
            g.narrar_com_limite(pronto, Path(work))
            self.assertEqual(voz.call_count, 1)

    def test_parametros_sem_sinal_sao_normalizados(self):
        self.assertEqual(g.parametro_de_voz('0Hz', 'Hz', 'VOZ_PITCH'), '+0Hz')
        self.assertEqual(g.parametro_de_voz('20Hz', 'Hz', 'VOZ_PITCH'), '+20Hz')
        self.assertEqual(g.parametro_de_voz('-20%', '%', 'VOZ_RATE'), '-20%')
        with self.assertRaises(ValueError):
            g.parametro_de_voz('devagar', '%', 'VOZ_RATE')

    def test_edge_repete_falha_e_preserva_voz_escolhida(self):
        import asyncio
        from unittest.mock import AsyncMock
        class Falha:
            async def stream(self):
                yield {'type': 'audio', 'data': b'parcial'}
                raise g.edge_tts.exceptions.NoAudioReceived('falha')
        class Sucesso:
            async def stream(self):
                yield {'type': 'audio', 'data': b'audio completo'}
        with tempfile.TemporaryDirectory() as work, \
             patch.object(g.config, 'VOZ', 'pt-PT-DuarteNeural', create=True), \
             patch.object(g.edge_tts, 'Communicate', side_effect=[Falha(), Sucesso()]) as tts, \
             patch.object(g.asyncio, 'sleep', new_callable=AsyncMock):
            destino = Path(work) / 'voz.mp3'
            asyncio.run(g._gerar_voz_edge_tts_async('Texto.', destino))
            self.assertEqual(destino.read_bytes(), b'audio completo')
            self.assertFalse(destino.with_name('voz.mp3.part').exists())
            self.assertEqual(tts.call_count, 2)
            self.assertTrue(all(c.args[1] == 'pt-PT-DuarteNeural' for c in tts.call_args_list))

    def test_edge_falha_final_preserva_audio_existente(self):
        import asyncio
        from unittest.mock import AsyncMock
        class Falha:
            async def stream(self):
                yield {'type': 'audio', 'data': b'incompleto'}
                raise g.edge_tts.exceptions.NoAudioReceived('falha')
        with tempfile.TemporaryDirectory() as work, \
             patch.object(g.edge_tts, 'Communicate', return_value=Falha()) as tts, \
             patch.object(g.asyncio, 'sleep', new_callable=AsyncMock):
            destino = Path(work) / 'teste_voz.mp3'
            destino.write_bytes(b'amostra anterior')
            with self.assertRaisesRegex(RuntimeError, 'após 3 tentativas'):
                asyncio.run(g._gerar_voz_edge_tts_async('Texto.', destino))
            self.assertEqual(tts.call_count, 3)
            self.assertEqual(destino.read_bytes(), b'amostra anterior')
            self.assertFalse(destino.with_name('teste_voz.mp3.part').exists())

    def test_montagem_sem_onda_preserva_logo_musica_e_legenda(self):
        with tempfile.TemporaryDirectory() as work:
            p = Path(work)
            legenda = p / 'legenda.ass'
            legenda.write_text(g.CABECALHO_ASS)
            logo = p / 'logo.png'
            logo.write_bytes(b'logo simulada')
            with patch.object(g, 'LOGO_FAIXA_PATH', logo), \
                 patch.object(g, 'obter_duracao_segundos', return_value=2), \
                 patch.object(g.subprocess, 'run') as ffmpeg:
                g.montar_video([p / 'clipe.mp4'], p / 'voz.wav', legenda,
                               p / 'final.mp4', p / 'musica.wav')
                comando = ffmpeg.call_args.args[0]
                filtro = comando[comando.index('-filter_complex') + 1]
                self.assertNotIn('showwaves', filtro)
                self.assertNotIn('drawbox', filtro)
                self.assertIn('subtitles=', filtro)
                self.assertIn('overlay=0:main_h-overlay_h', filtro)
                self.assertIn('sidechaincompress', filtro)


if __name__ == '__main__':
    unittest.main()
