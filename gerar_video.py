"""
Gerador automático de vídeos - Nicho: Histórias de Suspense/Mistério Fictícias
----------------------------------------------------------------
Pipeline: roteiro (IA) -> voz + legenda (edge-tts) -> clipes (Pexels)
          -> montagem (FFmpeg) -> envio para aprovação (Telegram)

Como usar:
    1. Configure as chaves em config.py (ou variáveis de ambiente)
    2. Rode: python gerar_video.py
    3. Aprove ou descarte o vídeo pelo Telegram
    4. Depois de aprovado, poste manualmente no YouTube/TikTok/Reels
       (ou automatize o upload mais tarde, quando as contas de API
       estiverem auditadas pelas plataformas)
"""

import os
import json
import random
import subprocess
import asyncio
from datetime import datetime
from pathlib import Path

import requests
import anthropic
import edge_tts

import config  # suas chaves ficam em config.py (veja config_exemplo.py)

# ----------------------------------------------------------------
# Pastas de trabalho
# ----------------------------------------------------------------
BASE_DIR = Path(__file__).parent
SAIDA_DIR = BASE_DIR / "saida"
MUSICA_DIR = BASE_DIR / "musica"
TEMAS_USADOS_PATH = BASE_DIR / "temas_usados.json"
SAIDA_DIR.mkdir(exist_ok=True)
MUSICA_DIR.mkdir(exist_ok=True)

VOZ = "pt-BR-AntonioNeural"  # alternativa: pt-BR-FranciscaNeural
FFMPEG_TIMEOUT_SEGUNDOS = 900  # rede de segurança: mata o FFmpeg se passar disso
MAX_SEGUNDOS_POR_CLIPE = 8  # duração de cada "clipe" (vídeo de banco OU imagem com Ken Burns)
LOGO_FAIXA_PATH = BASE_DIR / "assets" / "logo_faixa.png"  # faixa de marca (opcional)


# ----------------------------------------------------------------
# 1. Controle de temas já usados (evita repetição)
# ----------------------------------------------------------------
def carregar_temas_usados() -> list:
    if TEMAS_USADOS_PATH.exists():
        return json.loads(TEMAS_USADOS_PATH.read_text(encoding="utf-8"))
    return []


def salvar_tema_usado(tema: str):
    temas = carregar_temas_usados()
    temas.append(tema)
    TEMAS_USADOS_PATH.write_text(
        json.dumps(temas, ensure_ascii=False, indent=2), encoding="utf-8"
    )


# ----------------------------------------------------------------
# 2. Gerar roteiro com IA
# ----------------------------------------------------------------
# Categorias pra forçar variedade de verdade. A cada execução, o script usa
# a próxima da lista (round-robin), em vez de deixar 100% a critério da IA
# — assim o tema muda de fato, e não só o título do mesmo assunto.
#
# Nicho: histórias de suspense/mistério curtas e 100% FICTÍCIAS (estilo
# "creepypasta"). Personagens e locais inventados — isso evita qualquer
# risco de errar fatos sobre pessoas ou casos reais.
CATEGORIAS = [
    "Suspense psicológico em casa/apartamento",
    "Mistério em cidade pequena isolada",
    "Horror em floresta ou estrada deserta",
    "Suspense envolvendo um objeto ou achado estranho",
    "Mistério em prédio ou hotel abandonado",
    "História com reviravolta sobrenatural no final",
    "Suspense em ambiente de trabalho noturno",
    "Mistério envolvendo uma ligação, mensagem ou bilhete estranho",
    "Horror em viagem ou mudança para lugar novo",
    "Suspense com elemento de loop temporal ou déjà vu",
]


def escolher_categoria() -> str:
    temas_usados = carregar_temas_usados()
    indice = len(temas_usados) % len(CATEGORIAS)
    return CATEGORIAS[indice]


def gerar_roteiro() -> dict:
    client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
    temas_usados = carregar_temas_usados()[-30:]  # últimos 30, pra não repetir
    categoria = escolher_categoria()

    prompt = f"""Você escreve histórias curtas de suspense/mistério FICTÍCIAS (estilo
"creepypasta") para Shorts/TikTok, narradas em primeira pessoa.

Categoria de hoje (a história TEM que se encaixar nesta área): {categoria}

REGRAS IMPORTANTES:
- A história é 100% INVENTADA. Não use nomes de pessoas reais, casos reais
  ou lugares reais específicos (pode usar lugares genéricos como "uma
  cidade pequena no interior", sem apontar uma cidade real).
- Gancho forte logo nos primeiros 3 segundos (uma pergunta intrigante ou
  uma afirmação estranha que prende a atenção).
- Tom: suspense e mistério, pode ter um toque sobrenatural. Evite
  descrições gráficas de violência ou gore explícito.

ESTRUTURA OBRIGATÓRIA (história com camadas, não um fato só contado de forma
simples — o TikTok e o Kwai só pagam por visualização em vídeos de 60s+,
então a história PRECISA ter corpo suficiente pra isso, sem ficar enrolada):
1. Gancho (primeiros segundos): uma situação ou pergunta estranha que gera
   curiosidade imediata.
2. Contexto: quem é o narrador, onde está, o que parecia normal no início.
3. Primeiro sinal de que algo está errado — um detalhe pequeno e estranho.
4. Escalada: pelo menos DOIS momentos em que a situação piora ou fica mais
   confusa/assustadora (não pule direto do início pro final).
5. Clímax: o momento de maior tensão.
6. Reviravolta ou revelação final, que resignifica o que foi contado antes.

Isso deve resultar num roteiro de aproximadamente 160 a 190 palavras em
português (o suficiente pra ficar entre 60 e 75 segundos de narração).
Um roteiro curto demais, ou que só descreve uma cena sem desenvolver os
pontos acima, NÃO é aceitável.

Temas já usados recentemente (NÃO repita a mesma ideia de história, mesmo
com nomes diferentes):
{temas_usados}

Responda APENAS em JSON válido, neste formato exato, sem markdown, sem texto antes ou depois:
{{
  "tema": "nome curto da história (resume o gancho, sem spoiler do final)",
  "roteiro": "texto narrado de 60 a 75 segundos (160 a 190 palavras), em português do Brasil, em primeira pessoa, seguindo a estrutura de 6 pontos acima",
  "palavras_chave": ["palavra1", "palavra2", "palavra3", "palavra4", "palavra5", "palavra6", "palavra7", "palavra8"],
  "cenas": ["descrição 1", "descrição 2", "descrição 3", "descrição 4", "descrição 5", "descrição 6", "descrição 7", "descrição 8"]
}}

As palavras_chave devem ser termos em INGLÊS, simples, para buscar vídeos de banco de imagens
(ex: "empty hallway night", "foggy forest", "old house window"). Devem seguir a ordem
cronológica da história.

As "cenas" devem ser 8 descrições em INGLÊS, uma para cada momento da história em ordem
cronológica (acompanhando os 6 pontos da estrutura acima), MAIS DETALHADAS que as
palavras_chave — pensadas para um gerador de imagens por IA (estilo cinematográfico,
sombrio, com iluminação e atmosfera descritas). Exemplo: "a dim hallway in an old house,
moonlight through a cracked window, dust in the air, cinematic horror atmosphere,
photorealistic".
IMPORTANTE: evite cenas centradas em placas, letreiros, painéis, jornais ou qualquer coisa
que dependa de texto legível — geradores de imagem por IA erram muito ao escrever texto, e
isso passa impressão de descuido. Prefira ambientes, objetos e silhuetas sem texto."""

    msg = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=1500,
        messages=[{"role": "user", "content": prompt}],
    )
    texto = msg.content[0].text.strip()
    # remove possíveis cercas de markdown, caso a IA adicione por engano
    texto = texto.replace("```json", "").replace("```", "").strip()
    dados = json.loads(texto)
    return dados


# ----------------------------------------------------------------
# 3. Gerar voz — edge-tts (grátis, padrão atual) ou ElevenLabs (pago,
# melhor qualidade, desligado por padrão até você decidir ativar)
# ----------------------------------------------------------------
async def _gerar_voz_edge_tts_async(texto: str, audio_path: Path):
    voz = getattr(config, "VOZ", VOZ)
    # rate: velocidade da fala (ex: "-10%" fala mais devagar, "+15%" mais rápido)
    # pitch: tom da voz (ex: "-5Hz" fica mais grave, "+5Hz" mais aguda)
    rate = getattr(config, "VOZ_RATE", "+0%")
    pitch = getattr(config, "VOZ_PITCH", "+0Hz")
    communicate = edge_tts.Communicate(texto, voz, rate=rate, pitch=pitch)
    with open(audio_path, "wb") as f:
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                f.write(chunk["data"])


def gerar_voz_elevenlabs(texto: str, audio_path: Path):
    """Gera a narração usando a API da ElevenLabs. Só é chamada quando
    USAR_ELEVENLABS = True no config.py (ver config_exemplo.py)."""
    voice_id = getattr(config, "ELEVENLABS_VOICE_ID", "21m00Tcm4TlvDq8ikWAM")
    model_id = getattr(config, "ELEVENLABS_MODEL", "eleven_flash_v2_5")
    resp = requests.post(
        f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}",
        headers={
            "xi-api-key": config.ELEVENLABS_API_KEY,
            "Content-Type": "application/json",
            "Accept": "audio/mpeg",
        },
        json={
            "text": texto,
            "model_id": model_id,
            "voice_settings": {"stability": 0.5, "similarity_boost": 0.75},
        },
        timeout=60,
    )
    resp.raise_for_status()
    audio_path.write_bytes(resp.content)


def gerar_voz(texto: str, audio_path: Path):
    if getattr(config, "USAR_ELEVENLABS", False):
        gerar_voz_elevenlabs(texto, audio_path)
    else:
        asyncio.run(_gerar_voz_edge_tts_async(texto, audio_path))


# ----------------------------------------------------------------
# 3b. Gerar legenda ANIMADA baseada no tempo (não depende do edge-tts
# informar a temporização de cada palavra, que se mostrou pouco confiável).
# Divide o texto em blocos pequenos e distribui igualmente ao longo da
# duração real do áudio. Formato .ass (em vez de .srt simples), porque o
# .ass permite animação — cada bloco "nasce" na tela com um efeito de pop
# (cresce de 60% até o tamanho normal em 120ms), em vez de só aparecer e
# sumir sem transição.
# ----------------------------------------------------------------
def _formatar_tempo_ass(segundos: float) -> str:
    cs = int(round((segundos % 1) * 100))  # centésimos de segundo
    total_s = int(segundos)
    h = total_s // 3600
    m = (total_s % 3600) // 60
    s = total_s % 60
    return f"{h:01d}:{m:02d}:{s:02d}.{cs:02d}"


CABECALHO_ASS = """[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Arial,90,&H00FFFFFF,&H00FFFFFF,&H00000000,&H00000000,-1,0,0,0,100,100,0,0,1,6,0,2,10,10,300,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""


def gerar_legenda_por_tempo(
    texto: str, duracao_total: float, legenda_path: Path, palavras_por_bloco: int = 4
):
    palavras = texto.split()
    if not palavras:
        legenda_path.write_text(CABECALHO_ASS, encoding="utf-8")
        return

    blocos = [
        palavras[i:i + palavras_por_bloco]
        for i in range(0, len(palavras), palavras_por_bloco)
    ]
    textos_dos_blocos = [" ".join(b).replace("\n", " ") for b in blocos]

    # Duração proporcional ao tamanho de cada bloco (em caracteres), não
    # dividida igualmente. Blocos com palavras mais longas levam mais tempo
    # pra falar na vida real, então também recebem mais tempo de tela —
    # isso evita que a legenda "adiante" ou "atrase" em relação à voz ao
    # longo do vídeo, como acontecia com a divisão igual anterior.
    pesos = [max(len(t), 1) for t in textos_dos_blocos]
    peso_total = sum(pesos)

    linhas = [CABECALHO_ASS]
    acumulado = 0.0
    for i, (bloco, texto_bloco, peso) in enumerate(zip(blocos, textos_dos_blocos, pesos)):
        inicio = acumulado
        duracao_bloco = duracao_total * peso / peso_total
        fim = inicio + duracao_bloco
        acumulado = fim
        tags = r"{\fscx60\fscy60\t(0,120,\fscx100\fscy100)}"
        linhas.append(
            f"Dialogue: 0,{_formatar_tempo_ass(inicio)},{_formatar_tempo_ass(fim)},"
            f"Default,,0,0,0,,{tags}{texto_bloco}"
        )

    legenda_path.write_text("\n".join(linhas), encoding="utf-8")


# ----------------------------------------------------------------
# 4. Baixar clipe de vídeo do Pixabay
# ----------------------------------------------------------------
def _buscar_videos_pixabay(palavra_chave: str) -> list:
    params = {
        "key": config.PIXABAY_API_KEY,
        "q": palavra_chave,
        "per_page": 20,  # mínimo aceito pela API
    }
    resp = requests.get(
        "https://pixabay.com/api/videos/", params=params, timeout=30
    )
    resp.raise_for_status()
    return resp.json().get("hits", [])


def baixar_clipe(palavra_chave: str, destino: Path) -> bool:
    videos = _buscar_videos_pixabay(palavra_chave)

    if not videos:
        # Plano B: tenta só a primeira palavra (buscas de 2+ palavras às
        # vezes não encontram nada no Pixabay, mas a palavra isolada acha)
        primeira_palavra = palavra_chave.split()[0]
        if primeira_palavra != palavra_chave:
            print(f"    Nenhum resultado para '{palavra_chave}', "
                  f"tentando só '{primeira_palavra}'...")
            videos = _buscar_videos_pixabay(primeira_palavra)

    if not videos:
        # Plano C: um termo bem genérico, pra garantir que sempre vem algo
        print(f"    Ainda sem resultado, usando termo genérico de reserva...")
        videos = _buscar_videos_pixabay("nature")

    if not videos:
        return False

    video = random.choice(videos)
    # o Pixabay não tem filtro nativo de "vertical", então pegamos
    # o arquivo de maior resolução disponível (o FFmpeg recorta pra 9:16 depois)
    arquivos = video.get("videos", {})
    for qualidade in ("large", "medium", "small", "tiny"):
        if qualidade in arquivos:
            url_video = arquivos[qualidade]["url"]
            break
    else:
        return False

    video_resp = requests.get(url_video, timeout=60)
    destino.write_bytes(video_resp.content)
    return True


def montar_banco_de_clipes(palavras_chave: list, pasta: Path) -> list:
    clipes = []
    for i, palavra in enumerate(palavras_chave):
        destino = pasta / f"clipe_{i}.mp4"
        print(f"    Buscando clipe para '{palavra}'...")
        if baixar_clipe(palavra, destino):
            clipes.append(destino)
            print(f"    OK: clipe_{i}.mp4 baixado")
        else:
            print(f"    FALHOU: não achou nenhum clipe pra '{palavra}'")
    return clipes


# ----------------------------------------------------------------
# 4a-2. Gerar imagem com IA (Stability AI) + efeito Ken Burns
# ----------------------------------------------------------------
def gerar_imagem_stability(prompt: str, destino_png: Path):
    """Gera uma imagem vertical (9:16) usando a API da Stability AI."""
    # Geradores de imagem por IA costumam "inventar" texto ilegível em
    # placas, letreiros e cartazes dentro da cena (ex: um letreiro de táxi
    # escrito "TAXXI"). Isso passa uma impressão de descuido, então
    # reforçamos no próprio prompt e também via negative_prompt pra evitar
    # qualquer texto/letreiro legível na imagem.
    prompt_completo = (
        f"{prompt}, no text, no readable signage, no words, no letters, "
        f"no logos, blank signs"
    )
    resp = requests.post(
        "https://api.stability.ai/v2beta/stable-image/generate/core",
        headers={
            "Authorization": f"Bearer {config.STABILITY_API_KEY}",
            "Accept": "image/*",
        },
        # A API da Stability exige multipart/form-data mesmo sem anexar
        # nenhum arquivo — esse "files" vazio força o requests a montar a
        # requisição nesse formato.
        files={"none": (None, "")},
        data={
            "prompt": prompt_completo,
            "negative_prompt": (
                "text, letters, words, writing, signage, signs, logos, "
                "typography, captions, watermark, subtitles"
            ),
            "aspect_ratio": "9:16",
            "output_format": "png",
        },
        timeout=60,
    )
    resp.raise_for_status()
    destino_png.write_bytes(resp.content)


def gerar_clipe_com_ken_burns(
    imagem_path: Path, destino_mp4: Path, pasta: Path,
    duracao: float = MAX_SEGUNDOS_POR_CLIPE, zoom_out: bool = False,
):
    """Transforma uma imagem parada num clipe de vídeo com zoom lento
    (efeito Ken Burns), no mesmo formato que os clipes baixados do banco de
    vídeos — assim o resto do pipeline (concatenação, legenda, música,
    onda) funciona sem precisar saber de onde veio o clipe.

    zoom_out=True alterna a direção (começa aproximado e afasta, em vez de
    começar normal e aproximar) — dá mais variedade visual entre as cenas
    em vez de todas fazerem o mesmo movimento."""
    fps = 30
    frames = int(duracao * fps)
    if zoom_out:
        expressao_zoom = "if(eq(on,0),1.15,max(zoom-0.0007,1.0))"
    else:
        expressao_zoom = "min(zoom+0.0007,1.15)"
    comando = [
        "ffmpeg", "-y", "-loop", "1", "-i", imagem_path.name,
        "-vf", (
            "scale=2160:3840:force_original_aspect_ratio=increase,"
            "crop=2160:3840,"
            f"zoompan=z='{expressao_zoom}':d={frames}:s=1080x1920:fps={fps},"
            "setsar=1"
        ),
        "-t", str(duracao),
        "-pix_fmt", "yuv420p",
        "-c:v", "libx264", "-preset", "veryfast",
        destino_mp4.name,
    ]
    subprocess.run(
        comando, check=True, cwd=str(pasta), timeout=FFMPEG_TIMEOUT_SEGUNDOS,
    )


def montar_banco_de_imagens(cenas: list, pasta: Path) -> list:
    """Equivalente a montar_banco_de_clipes, mas gerando as imagens por IA
    em vez de baixar do Pixabay."""
    clipes = []
    for i, cena in enumerate(cenas):
        imagem_path = pasta / f"imagem_{i}.png"
        clipe_path = pasta / f"clipe_{i}.mp4"
        resumo = cena[:60] + ("..." if len(cena) > 60 else "")
        print(f"    Gerando imagem IA ({i+1}/{len(cenas)}): '{resumo}'")
        try:
            gerar_imagem_stability(cena, imagem_path)
            gerar_clipe_com_ken_burns(
                imagem_path, clipe_path, pasta, zoom_out=(i % 2 == 1)
            )
            clipes.append(clipe_path)
            print(f"    OK: clipe_{i}.mp4 gerado (imagem + Ken Burns)")
        except Exception as e:
            print(f"    FALHOU ao gerar a cena {i}: {e}")
    return clipes


# ----------------------------------------------------------------
# 4b. Trilha sonora
# ----------------------------------------------------------------
def escolher_musica() -> Path | None:
    """Escolhe um MP3 aleatório da pasta 'musica/'. Retorna None se a pasta
    estiver vazia (nesse caso o vídeo sai só com a narração, sem travar)."""
    faixas = list(MUSICA_DIR.glob("*.mp3"))
    if not faixas:
        return None
    return random.choice(faixas)


# ----------------------------------------------------------------
# 5. Montar vídeo final com FFmpeg
# ----------------------------------------------------------------
def obter_duracao_segundos(caminho_audio: Path) -> float:
    """Usa o ffprobe para descobrir a duração exata do áudio, em segundos."""
    resultado = subprocess.run(
        [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(caminho_audio),
        ],
        capture_output=True, text=True, check=True,
    )
    return float(resultado.stdout.strip())


def montar_video(
    clipes: list, audio_path: Path, legenda_path: Path, saida_path: Path,
    musica_path: Path | None = None,
):
    pasta = saida_path.parent
    duracao = obter_duracao_segundos(audio_path)

    # ------------------------------------------------------------
    # Concatenação via FILTRO (não via demuxer "-f concat").
    #
    # O demuxer "-f concat" lê os arquivos em baixo nível, antes de
    # decodificar, e é muito sensível a metadados de duração corrompidos
    # vindos de uma fonte (um clipe do banco de vídeos pode trazer um
    # cabeçalho de duração errado). Isso já causou o bug do vídeo saindo
    # com 40+ minutos em vez de ~30 segundos.
    #
    # Aqui, cada clipe é aberto como um input separado e já decodificado
    # (-t 8 limita cada um a no máximo 8s, como segurança extra), depois
    # o filtro "concat" junta os frames já normalizados. Isso elimina o
    # problema na raiz, porque nenhum metadado de duração de origem é
    # usado para decidir onde o vídeo termina.
    # ------------------------------------------------------------
    comando = ["ffmpeg", "-y"]
    for clipe in clipes:
        comando += ["-t", str(MAX_SEGUNDOS_POR_CLIPE), "-i", clipe.name]

    partes_filtro = []
    for i in range(len(clipes)):
        partes_filtro.append(
            f"[{i}:v]scale=1080:1920:force_original_aspect_ratio=increase,"
            f"crop=1080:1920,setsar=1,fps=30,setpts=PTS-STARTPTS[v{i}]"
        )

    # Transição suave (crossfade) entre cada cena, em vez de corte seco —
    # dá um acabamento bem mais profissional. Cada clipe tem duração fixa
    # (MAX_SEGUNDOS_POR_CLIPE), então dá pra calcular o "offset" de cada
    # transição com antecedência.
    TRANSICAO_SEGUNDOS = 0.5
    if len(clipes) == 1:
        filtro_transicoes = ";[v0]null[outv]"
    else:
        transicoes = []
        label_anterior = "v0"
        duracao_acumulada = MAX_SEGUNDOS_POR_CLIPE
        for i in range(1, len(clipes)):
            label_saida = f"x{i}" if i < len(clipes) - 1 else "outv"
            offset = duracao_acumulada - TRANSICAO_SEGUNDOS
            transicoes.append(
                f"[{label_anterior}][v{i}]xfade=transition=fade:"
                f"duration={TRANSICAO_SEGUNDOS}:offset={offset}[{label_saida}]"
            )
            label_anterior = label_saida
            duracao_acumulada += MAX_SEGUNDOS_POR_CLIPE - TRANSICAO_SEGUNDOS
        filtro_transicoes = ";" + ";".join(transicoes)

    filtro_concat = ";".join(partes_filtro) + filtro_transicoes

    comando += [
        "-filter_complex", filtro_concat,
        "-map", "[outv]",
        "-c:v", "libx264", "-preset", "veryfast",
        "-t", str(duracao + 10),  # trava de segurança (nunca passa disso)
        "concatenado.mp4",
    ]

    subprocess.run(
        comando,
        check=True,
        cwd=str(pasta),  # roda dentro da pasta pra evitar o "C:" ou "F:" no caminho
        timeout=FFMPEG_TIMEOUT_SEGUNDOS,
    )

    # Verifica se a legenda existe e tem conteúdo real antes de tentar usá-la.
    legenda_ok = legenda_path.exists() and legenda_path.stat().st_size > 10
    if not legenda_ok:
        print("    AVISO: legenda.ass não foi gerada corretamente (arquivo "
              "ausente ou vazio). O vídeo vai sair sem legenda desta vez.")

    tem_musica = musica_path is not None
    if tem_musica:
        print(f"    Trilha sonora: {musica_path.name}")

    tem_logo = LOGO_FAIXA_PATH.exists()
    if not tem_logo:
        print(f"    (sem faixa de logo — arquivo não encontrado em {LOGO_FAIXA_PATH})")

    def _rodar(com_legenda: bool, com_onda: bool):
        comando = [
            "ffmpeg", "-y",
            "-stream_loop", "-1", "-i", "concatenado.mp4",  # input 0: vídeo
            "-i", audio_path.name,                          # input 1: voz
        ]
        proximo_indice = 2
        if tem_musica:
            comando += ["-stream_loop", "-1", "-i", str(musica_path)]
            indice_musica = proximo_indice
            proximo_indice += 1
        if tem_logo:
            comando += ["-i", str(LOGO_FAIXA_PATH)]
            indice_logo = proximo_indice
            proximo_indice += 1

        filtro_video = (
            "[0:v]scale=1080:1920:force_original_aspect_ratio=increase,"
            "crop=1080:1920"
        )
        if com_legenda:
            # O estilo (bold, branco, contorno preto) e a animação de pop
            # (cresce ao aparecer) já vêm embutidos no próprio arquivo
            # .ass gerado em gerar_legenda_por_tempo — não precisa de
            # force_style aqui.
            filtro_video += f",subtitles={legenda_path.name}"

        if com_onda:
            # Visualizador de onda sonora: uma caixa escura com uma linha
            # amarela grossa que pulsa no ritmo da voz, posicionada no
            # TERÇO SUPERIOR do vídeo (longe da legenda, que fica embaixo).
            # A caixa preta por trás garante contraste em qualquer fundo de
            # clipe. Gerado a partir do áudio da narração (input 1), nunca
            # da música, pra pulsar certinho com o que está sendo dito.
            filtro_video += (
                ",drawbox=x=(iw-1000)/2:y=160:w=1000:h=220:"
                "color=black@0.55:t=fill[base]"
            )
            filtro_onda = (
                "[1:a]showwaves=s=960x180:mode=cline:rate=25:"
                "colors=0xFFD400,format=rgba,"
                "colorchannelmixer=aa=0.95[onda]"
            )
            filtro_video += (
                f";{filtro_onda};[base][onda]overlay=(main_w-overlay_w)/2:180[comonda]"
            )
            label_atual = "comonda"
        else:
            filtro_video += "[comonda]"
            label_atual = "comonda"

        if tem_logo:
            # Faixa de marca fixa no rodapé do vídeo — bem abaixo de onde a
            # legenda aparece (MarginV=300 no .ass garante essa distância),
            # então nunca sobrepõe o texto.
            filtro_video += (
                f";[{label_atual}][{indice_logo}:v]overlay=0:main_h-overlay_h[vout]"
            )
        else:
            filtro_video += f";[{label_atual}]null[vout]"

        if tem_musica:
            # Voz no volume normal, música bem mais baixa por baixo (0.12),
            # cortada na mesma duração da narração.
            filtro_audio = (
                f"[1:a]volume=1.0[voz];"
                f"[2:a]volume=0.12,atrim=0:{duracao}[musica];"
                f"[voz][musica]amix=inputs=2:duration=first:dropout_transition=0[aout]"
            )
            filtro_completo = f"{filtro_video};{filtro_audio}"
            mapeamento = ["-map", "[vout]", "-map", "[aout]"]
        else:
            filtro_completo = filtro_video
            mapeamento = ["-map", "[vout]", "-map", "1:a:0"]

        comando += [
            "-filter_complex", filtro_completo,
            *mapeamento,
            # -t força o corte exato na duração do áudio. Não confiamos só
            # no -shortest porque, com clipes concatenados de fontes
            # diferentes, os timestamps às vezes saem irregulares demais
            # pro -shortest calcular o fim corretamente.
            "-t", str(duracao),
            # yuv420p é o formato de cor padrão de vídeo (compatível com
            # TikTok/YouTube/Instagram). Sem isso, o filtro da onda sonora
            # (que usa transparência) força um formato mais pesado e quase
            # triplica o tamanho do arquivo, estourando o limite do Telegram.
            "-pix_fmt", "yuv420p",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
            "-c:a", "aac", "-b:a", "128k",
            saida_path.name,
        ]
        subprocess.run(
            comando, check=True, cwd=str(pasta), timeout=FFMPEG_TIMEOUT_SEGUNDOS,
        )

    # Tenta na ordem: (legenda + onda) -> (sem legenda + onda) ->
    # (sem legenda + sem onda). Cada etapa só desliga nessa ordem se a
    # anterior falhar, pra sempre entregar um vídeo no final.
    tentativas = []
    if legenda_ok:
        tentativas.append((True, True))
    tentativas.append((False, True))
    tentativas.append((False, False))

    erro_final = None
    for com_legenda, com_onda in tentativas:
        try:
            _rodar(com_legenda=com_legenda, com_onda=com_onda)
            return
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
            erro_final = e
            motivo = "demorou demais (timeout)" if isinstance(e, subprocess.TimeoutExpired) else "erro no FFmpeg"
            print(f"    AVISO: falhou com legenda={com_legenda}, onda={com_onda} "
                  f"({motivo}). Tentando a próxima configuração...")

    raise erro_final


# ----------------------------------------------------------------
# 6. Enviar para aprovação no Telegram
# ----------------------------------------------------------------
def enviar_para_telegram(video_path: Path, legenda_texto: str):
    tamanho_mb = video_path.stat().st_size / (1024 * 1024)
    if tamanho_mb > 48:
        print(f"    AVISO: vídeo tem {tamanho_mb:.1f}MB — acima do limite de "
              f"50MB do Telegram pra bots. Pegue o arquivo direto na pasta "
              f"'saida' em vez de esperar o envio:\n    {video_path.resolve()}")
        return

    url = f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/sendVideo"
    for tentativa in range(1, 4):
        try:
            with open(video_path, "rb") as f:
                resp = requests.post(
                    url,
                    data={"chat_id": config.TELEGRAM_CHAT_ID, "caption": legenda_texto[:1024]},
                    files={"video": f},
                    timeout=180,
                )
            resp.raise_for_status()
            print("Vídeo enviado para o Telegram com sucesso.")
            return
        except requests.exceptions.RequestException as e:
            print(f"    Tentativa {tentativa}/3 de envio falhou: {e}")

    print(f"    Não consegui enviar pro Telegram após 3 tentativas. "
          f"Pegue o arquivo direto na pasta 'saida':\n    {video_path.resolve()}")


# ----------------------------------------------------------------
# Fluxo principal
# ----------------------------------------------------------------
def main():
    print(f"[{datetime.now()}] Iniciando geração de vídeo...")

    pasta_trabalho = SAIDA_DIR / datetime.now().strftime("%Y%m%d_%H%M%S")
    pasta_trabalho.mkdir(parents=True, exist_ok=True)

    print("1/5 Gerando roteiro...")
    dados = gerar_roteiro()
    print(f"    Categoria: {escolher_categoria()}")
    print(f"    Tema: {dados['tema']}")

    print("2/5 Gerando voz e legenda...")
    audio_path = pasta_trabalho / "voz.mp3"
    legenda_path = pasta_trabalho / "legenda.ass"
    gerar_voz(dados["roteiro"], audio_path)
    duracao_audio = obter_duracao_segundos(audio_path)
    gerar_legenda_por_tempo(dados["roteiro"], duracao_audio, legenda_path)
    print(f"    (voz com {duracao_audio:.1f}s, legenda.ass gerada com "
          f"{legenda_path.stat().st_size} bytes)")

    usar_ia = getattr(config, "USAR_IMAGENS_IA", False)
    if usar_ia:
        print("3/5 Gerando imagens com IA (Stability AI)...")
        clipes = montar_banco_de_imagens(dados["cenas"], pasta_trabalho)
    else:
        print("3/5 Baixando clipes...")
        clipes = montar_banco_de_clipes(dados["palavras_chave"], pasta_trabalho)
    if not clipes:
        print("    Nenhum clipe/imagem disponível. Abortando.")
        return

    print("4/5 Montando vídeo final...")
    video_final = pasta_trabalho / "video_final.mp4"
    musica_path = escolher_musica()
    if musica_path is None:
        print("    (nenhuma música encontrada na pasta 'musica/' — "
              "vídeo sai só com a narração)")
    montar_video(clipes, audio_path, legenda_path, video_final, musica_path)

    print("5/5 Enviando para aprovação no Telegram...")
    enviar_para_telegram(video_final, f"Tema: {dados['tema']}\n\n{dados['roteiro']}")

    salvar_tema_usado(dados["tema"])
    print(f"[{datetime.now()}] Concluído! Vídeo em: {video_final}")


if __name__ == "__main__":
    main()
