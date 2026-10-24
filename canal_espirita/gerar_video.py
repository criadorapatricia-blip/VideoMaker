"""Canal espírita independente: reflexão autoral e prece diária inspiradas em Allan Kardec.
Configure config.py localmente e execute python gerar_video.py.
"""

import os
import argparse
import hashlib
import json
import random
import re
import subprocess
import asyncio
from datetime import datetime
from pathlib import Path

import requests
import anthropic
import edge_tts

try:
    import config  # somente o config.py desta pasta; nunca reutiliza o canal de suspense
except ModuleNotFoundError as erro:
    if erro.name != "config":
        raise
    raise SystemExit("Copie config_exemplo.py para config.py nesta pasta e preencha suas chaves localmente.")

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
MAX_IMAGENS = 6
DURACAO_MINIMA = 62.0
DURACAO_MAXIMA = 65.0
DURACAO_ALVO = 64.0
MAX_SEGUNDOS_POR_CLIPE = 8  # duração de cada "clipe" (vídeo de banco OU imagem com Ken Burns)
LOGO_FAIXA_PATH = BASE_DIR / "assets" / "logo_faixa.png"




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
# Temas em rotação; as referências servem para estudo, não são citações literais.
CATEGORIAS = [
    "Caridade no cotidiano e serviço ao próximo",
    "Reforma íntima e responsabilidade pelas escolhas",
    "Perdão, reconciliação e compreensão",
    "Gratidão pela vida e pelas oportunidades de aprender",
    "Paciência diante das dificuldades",
    "Trabalho honesto e solidariedade",
    "Prece, confiança em Deus e ação no bem",
]
FONTES_DE_ESTUDO = [
    {"obra": "O Livro dos Espíritos", "local": "questão 886", "assunto": "Caridade"},
    {"obra": "O Livro dos Espíritos", "local": "questão 919", "assunto": "Conhecimento de si mesmo"},
    {"obra": "O Evangelho segundo o Espiritismo", "local": "capítulo X", "assunto": "Misericórdia e perdão"},
    {"obra": "O Evangelho segundo o Espiritismo", "local": "capítulo XVII", "assunto": "Aperfeiçoamento moral"},
    {"obra": "O Evangelho segundo o Espiritismo", "local": "capítulo XXVII", "assunto": "A prece"},
]


def contexto_do_dia(agora=None) -> dict:
    hoje = agora if agora is not None else datetime.now()
    dias = ["segunda-feira", "terça-feira", "quarta-feira", "quinta-feira", "sexta-feira", "sábado", "domingo"]
    meses = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto", "setembro", "outubro", "novembro", "dezembro"]
    abertura = f"Hoje é {dias[hoje.weekday()]}, {hoje.day} de {meses[hoje.month-1]} de {hoje.year}."
    return {"data": hoje.date().isoformat(), "abertura": abertura}


def escolher_categoria() -> str:
    temas_usados = carregar_temas_usados()
    indice = len(temas_usados) % len(CATEGORIAS)
    return CATEGORIAS[indice]


def preparar_roteiro(dados: dict) -> dict:
    """A narração das cenas é a fonte única do roteiro, sem duplicá-la no pedido."""
    if not isinstance(dados, dict):
        raise ValueError("A resposta precisa ser um objeto JSON.")
    cenas = dados.get("plano_cenas")
    if not isinstance(cenas, list) or not 1 <= len(cenas) <= MAX_IMAGENS:
        raise ValueError("A resposta precisa conter plano_cenas com 1 a 6 cenas.")
    normalizadas = []
    for i, cena in enumerate(cenas):
        if not isinstance(cena, dict):
            raise ValueError(f"Cena {i + 1} não é um objeto.")
        narracao = cena.get("narracao")
        visual = cena.get("visual")
        if not isinstance(narracao, str) or not narracao.strip():
            raise ValueError(f"Cena {i + 1} sem narração.")
        if not isinstance(visual, str) or not visual.strip():
            raise ValueError(f"Cena {i + 1} sem descrição visual.")
        corte = str(cena.get("corte", "seco")).strip().lower()
        if corte not in ("seco", "suave"):
            corte = "seco"
        busca = cena.get("busca")
        normalizadas.append({**cena, "narracao": " ".join(narracao.split()),
                             "visual": visual.strip(), "corte": corte,
                             "busca": busca.strip() if isinstance(busca, str) and busca.strip() else visual.strip()})
    roteiro = " ".join(c["narracao"] for c in normalizadas)
    # Compatibilidade com arquivos antigos: não descarta texto omitido nas cenas.
    original = dados.get("roteiro")
    if isinstance(original, str) and " ".join(original.split()) != roteiro:
        raise ValueError("O roteiro antigo contém diferenças em relação às cenas; revise o JSON salvo.")
    tema = dados.get("tema")
    if not isinstance(tema, str) or not tema.strip():
        raise ValueError("Resposta sem título (tema).")
    pronto = {**dados, "tema": tema.strip(), "roteiro": roteiro, "plano_cenas": normalizadas}
    validar_plano_cenas(pronto)
    return pronto


def aplicar_data(dados: dict, contexto: dict) -> dict:
    """Acrescenta a abertura calculada, sem confiar a data ao modelo."""
    dados = {**dados, "plano_cenas": [dict(c) for c in dados["plano_cenas"]]}
    if dados.get("data_mensagem"):
        if dados["data_mensagem"] != contexto["data"]:
            raise ValueError("Esse roteiro tem data antiga. Gere uma mensagem nova para hoje.")
        if not dados["plano_cenas"][0]["narracao"].startswith(contexto["abertura"]):
            raise ValueError("A abertura não corresponde à data registrada.")
        return dados
    primeira = dados["plano_cenas"][0]
    primeira["narracao"] = contexto["abertura"] + " " + primeira["narracao"]
    dados["roteiro"] = " ".join(c["narracao"] for c in dados["plano_cenas"])
    dados["data_mensagem"] = contexto["data"]
    dados["tipo_texto"] = "Reflexão autoral inspirada nos princípios espíritas; não é citação de Kardec."
    dados["fontes_de_estudo"] = FONTES_DE_ESTUDO
    validar_plano_cenas(dados)
    return dados


def limitar_texto_devocional(dados: dict, limite: int = 70, forcar: bool = False) -> dict:
    """Compacta localmente em frases completas; nunca pede outro roteiro pago."""
    if not forcar and len(dados["roteiro"].split()) <= limite:
        return dados
    contexto = contexto_do_dia(datetime.fromisoformat(dados["data_mensagem"]))
    abertura = contexto["abertura"]
    # Primeiro aproveita uma frase curta completa de cada cena, se isso couber.
    cenas = [dict(c) for c in dados["plano_cenas"]]
    for i, cena in enumerate(cenas):
        texto = cena["narracao"]
        if i == 0 and texto.startswith(abertura):
            texto = texto[len(abertura):].strip()
        frases = re.split(r"(?<=[.!?])\s+", texto)
        cena["narracao"] = frases[0].strip()
    texto = abertura + " " + " ".join(c["narracao"] for c in cenas)
    if (not forcar and all(c["narracao"] for c in cenas)
            and len(texto.split()) <= limite):
        cenas[0]["narracao"] = abertura + " " + cenas[0]["narracao"]
    else:
        # Prece autoral local, sem atribuição a Kardec, quando não há frases
        # completas curtas o bastante. Descrições visuais também são trocadas.
        normais = [
            "Deus, agradeço por este novo dia.",
            "Ajuda-me a reconhecer minhas próprias falhas.",
            "Que eu escolha agir com bondade.",
            "Ensina-me a compreender antes de julgar.",
            "Que minhas atitudes levem paz ao próximo.",
            "Dá-me coragem para melhorar, um passo por vez.",
        ]
        breves = ["Agradeço pela vida.", "Desejo aprender.", "Escolho fazer o bem.",
                  "Quero compreender e perdoar.", "Que eu sirva com amor.", "Deus, guia meus passos."]
        frases = normais if len((abertura + " " + " ".join(normais)).split()) <= limite else breves
        visuais = ["a peaceful sunrise over a garden", "an adult reflecting beside a window",
                   "adult hands gently caring for a small plant", "two adults talking calmly in a garden",
                   "an adult helping another adult carry a basket", "a quiet garden path in warm morning light"]
        cenas = [{"narracao": frase, "visual": visual + ", photorealistic, no text",
                  "busca": visual, "corte": "suave"} for frase, visual in zip(frases, visuais)]
        cenas[0]["narracao"] = abertura + " " + cenas[0]["narracao"]
    pronto = {**dados, "plano_cenas": cenas,
              "roteiro": " ".join(c["narracao"] for c in cenas),
              "compactacao_local": True}
    if len(pronto["roteiro"].split()) > limite:
        raise ValueError("Não foi possível compactar o texto sem cortar frases. Nenhuma imagem foi solicitada.")
    validar_plano_cenas(pronto)
    print(f"    Texto compactado localmente para {len(pronto['roteiro'].split())} palavras, incluindo a data.")
    return pronto


def narrar_com_limite(dados: dict, pasta: Path) -> tuple[dict, Path, list]:
    """Confere palavras antes da voz e tempo antes de qualquer imagem."""
    original = pasta / "roteiro_antes_ajuste.json"
    if not original.exists():
        original.write_text(json.dumps(dados, ensure_ascii=False, indent=2), encoding="utf-8")
    dados = limitar_texto_devocional(dados)
    (pasta / "roteiro.json").write_text(json.dumps(dados, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"    Narração: {len(dados['roteiro'].split())} palavras, incluindo dia e data.")
    audio, segmentos = gerar_narracao_cenas(dados["plano_cenas"], pasta)
    duracao = obter_duracao_segundos(audio)
    if duracao > DURACAO_MAXIMA and not getattr(config, "USAR_ELEVENLABS", False):
        # Edge TTS não usa Anthropic/Stability; limita a uma nova narração curta.
        limite = max(36, min(55, int(len(dados["roteiro"].split()) * 52 / duracao)))
        curto = limitar_texto_devocional(dados, limite=limite, forcar=True)
        if curto["roteiro"] != dados["roteiro"]:
            print("    A fala ainda ficou longa. Uma única nova narração Edge TTS será feita com texto menor.")
            dados = curto
            (pasta / "roteiro.json").write_text(json.dumps(dados, ensure_ascii=False, indent=2), encoding="utf-8")
            audio, segmentos = gerar_narracao_cenas(dados["plano_cenas"], pasta)
    return dados, audio, segmentos


def gerar_roteiro(pasta: Path) -> dict:
    client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
    contexto = contexto_do_dia()
    prompt = f"""Crie uma reflexão devocional AUTORAL em português brasileiro, inspirada
nos princípios do Espiritismo de Allan Kardec. Tema: {escolher_categoria()}.
Contexto real do computador: {contexto['abertura']}
Use 45 a 55 palavras no total, em EXATAMENTE SEIS cenas, terminando numa prece
breve a Deus. Frases curtas, com pontuação natural para pausas. Não acrescente
mais texto para preencher tempo: o programa reserva pausas para reflexão.
Tom acolhedor, sereno, fraterno e esperançoso, sem suspense.
Não escreva a data nem o dia da semana na narração: o programa acrescentará a
abertura correta. Não invente fatos da vida do espectador nem previsões.
Temas recentes a evitar: {carregar_temas_usados()[-30:]}

Bases de estudo (não copie citações): {json.dumps(FONTES_DE_ESTUDO, ensure_ascii=False)}
Aborde livre-arbítrio, responsabilidade pessoal, caridade, perdão, reforma íntima,
prece e progresso moral conforme o tema. Não prometa cura, riqueza ou proteção
garantida; não apresente sofrimento como punição individual. Não crie mensagens
atribuídas a espíritos, médiuns ou Kardec. NÃO use citações literais, versículos,
nomes de autores ou afirmações de que o texto veio de uma obra: é reflexão autoral.
Não confunda a proposta com horóscopo, rituais de prosperidade ou outra doutrina.

Responda APENAS JSON com tema e plano_cenas:
{{"tema": "Título da reflexão", "plano_cenas": [
 {{"narracao": "Trecho da reflexão.", "visual": "English visual description",
   "busca": "English search terms", "corte": "suave"}}
]}}
Complete seis cenas. O texto aparece somente nos trechos narracao.
Imagens: natureza, amanhecer, caminhos, jardins ou gestos cotidianos de bondade,
coerentes com o trecho, serenas, claras, realistas e sem texto ou símbolos de
outras religiões. Evite livros abertos com escrita e representações de espíritos.
Use transições suaves; mantenha consistência de local e pessoas se aparecerem.
"""
    msg = client.messages.create(
        model="claude-haiku-4-5-20251001", max_tokens=3500,
        messages=[{"role": "user", "content": prompt}],
    )
    texto = "\n".join(bloco.text for bloco in msg.content if getattr(bloco, "type", "text") == "text").strip()
    resposta_path = pasta / "roteiro_resposta.txt"
    resposta_path.write_text(texto, encoding="utf-8")
    try:
        if getattr(msg, "stop_reason", None) == "max_tokens":
            raise ValueError("A resposta da IA foi interrompida pelo limite de saída.")
        texto = re.sub(r"^```(?:json)?\s*|\s*```$", "", texto).strip()
        dados = json.loads(texto)
        return aplicar_data(preparar_roteiro(dados), contexto)
    except (ValueError, TypeError, KeyError, AttributeError) as erro:
        raise ValueError(
            f"Roteiro não aceito: {erro}\nResposta preservada em: {resposta_path.resolve()}\n"
            "Nenhum segundo roteiro foi solicitado e nenhuma imagem foi gerada.") from erro


# ----------------------------------------------------------------
# 3. Gerar voz — edge-tts (grátis, padrão atual) ou ElevenLabs (pago,
# melhor qualidade, desligado por padrão até você decidir ativar)
# ----------------------------------------------------------------
def parametro_de_voz(valor, unidade: str, nome: str) -> str:
    texto = str(valor).strip()
    if not re.fullmatch(r"[+-]?\d+" + re.escape(unidade), texto):
        raise ValueError(f"{nome} inválido: use um valor como -20% para velocidade ou +0Hz para tom.")
    return texto if texto.startswith(("+", "-")) else "+" + texto


async def _gerar_voz_edge_tts_async(texto: str, audio_path: Path):
    voz = str(getattr(config, "VOZ", VOZ)).strip()
    rate = parametro_de_voz(getattr(config, "VOZ_RATE", "-20%"), "%", "VOZ_RATE")
    pitch = parametro_de_voz(getattr(config, "VOZ_PITCH", "-12Hz"), "Hz", "VOZ_PITCH")
    temporario = audio_path.with_name(audio_path.name + ".part")
    try:
        for tentativa in range(3):
            try:
                communicate = edge_tts.Communicate(texto, voz, rate=rate, pitch=pitch)
                with open(temporario, "wb") as f:
                    async for chunk in communicate.stream():
                        if chunk["type"] == "audio":
                            f.write(chunk["data"])
                if temporario.stat().st_size == 0:
                    raise edge_tts.exceptions.NoAudioReceived("Nenhum áudio recebido.")
                temporario.replace(audio_path)
                return
            except (edge_tts.exceptions.NoAudioReceived, TimeoutError) as erro:
                if tentativa == 2:
                    raise RuntimeError(
                        "Edge TTS não retornou áudio após 3 tentativas. "
                        f"Voz mantida: {voz}; velocidade: {rate}; tom: {pitch}. "
                        "Pode ser indisponibilidade do serviço ou incompatibilidade dos parâmetros. "
                        "Confira o nome exato da voz e teste com --teste-voz. "
                        "Depois repita --roteiro com o arquivo salvo, sem nova chamada à Anthropic. "
                        "Nenhuma imagem foi solicitada nesta etapa.") from erro
                espera = 2 * (tentativa + 1)
                print(f"    Edge TTS sem áudio; nova tentativa {tentativa + 2}/3 em {espera}s, com a mesma voz.")
                await asyncio.sleep(espera)
    finally:
        temporario.unlink(missing_ok=True)


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
# 3b. Legendas por pontuação, temporizadas dentro de cada cena narrada.
# ----------------------------------------------------------------
def _formatar_tempo_ass(segundos: float) -> str:
    total_cs = max(0, round(segundos * 100))
    total_s, cs = divmod(total_cs, 100)
    h, resto = divmod(total_s, 3600)
    m, segundo = divmod(resto, 60)
    return f"{h}:{m:02d}:{segundo:02d}.{cs:02d}"


CABECALHO_ASS = """[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Arial,76,&H00FFFFFF,&H00FFFFFF,&H00000000,&H00000000,-1,0,0,0,100,100,0,0,1,6,0,2,90,90,320,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""


def dividir_legendas(texto: str, limite: int = 6) -> list[str]:
    """Prefere pontuação e não deixa conectivos soltos no final do bloco."""
    conectivos = {"a", "o", "as", "os", "um", "uma", "de", "do", "da", "dos",
                  "das", "em", "no", "na", "nos", "nas", "por", "para", "com",
                  "e", "mas", "que", "meu", "minha", "seu", "sua"}
    palavras = texto.split()
    blocos = []
    while palavras:
        n = min(limite, len(palavras))
        for i, palavra in enumerate(palavras[:n]):
            if re.search(r"[.!?;,:…][\"'”’]*$", palavra):
                n = i + 1
                break
        while n > 1 and palavras[n - 1].lower() in conectivos:
            n -= 1
        # Limita largura sem depender de quebra automática junto à margem.
        while n > 1 and len(" ".join(palavras[:n])) > 38:
            n -= 1
        while n > 1 and palavras[n - 1].lower() in conectivos:
            n -= 1
        blocos.append(" ".join(palavras[:n]))
        palavras = palavras[n:]
    return blocos


def gerar_legenda_por_tempo(
    texto: str, duracao_total: float, legenda_path: Path,
    palavras_por_bloco: int = 6, segmentos: list | None = None,
):
    # Com segmentos, cada cena usa seu próprio áudio medido: não acumula
    # o desvio de uma estimativa feita sobre a narração inteira.
    segmentos = segmentos if segmentos is not None else [
        {"narracao": texto, "inicio": 0, "duracao": duracao_total}]
    linhas = [CABECALHO_ASS]
    for cena in segmentos:
        blocos = dividir_legendas(cena["narracao"], palavras_por_bloco)
        pesos = [len(t) + 6 * bool(re.search(r"[.!?,;:]$", t)) for t in blocos]
        total = sum(pesos)
        acumulado = cena["inicio"]
        for bloco, peso in zip(blocos, pesos):
            fim = acumulado + cena.get("duracao_fala", cena["duracao"]) * peso / total
            seguro = bloco.replace("\\", " ").replace("{", "").replace("}", "")
            tags = r"{\fad(60,60)}"
            linhas.append(
                f"Dialogue: 0,{_formatar_tempo_ass(acumulado)},{_formatar_tempo_ass(fim)},"
                f"Default,,0,0,0,,{tags}{seguro}")
            acumulado = fim
    legenda_path.write_text("\n".join(linhas), encoding="utf-8")


def validar_plano_cenas(dados: dict):
    cenas = dados.get("plano_cenas", [])
    if not isinstance(cenas, list) or not 1 <= len(cenas) <= MAX_IMAGENS:
        raise ValueError("O roteiro precisa de 1 a 6 cenas alinhadas à narração.")
    for cena in cenas:
        if not isinstance(cena, dict):
            raise ValueError("Cena precisa ser um objeto.")
        if any(not isinstance(cena.get(k), str) or not cena[k].strip()
               for k in ("narracao", "visual", "busca")):
            raise ValueError("Cena sem narração, visual ou busca.")
        if cena.get("corte") not in ("seco", "suave"):
            raise ValueError("Tipo de corte inválido.")
    if " ".join(dados["roteiro"].split()) != " ".join(
            " ".join(c["narracao"] for c in cenas).split()):
        raise ValueError("As cenas não cobrem exatamente o roteiro; geração interrompida.")


def gerar_narracao_cenas(cenas: list, pasta: Path) -> tuple[Path, list]:
    """Mede cada trecho em PCM para manter cortes e legendas na mesma linha de tempo."""
    import wave
    timeline = []
    inicio = 0.0
    destino = pasta / "voz.wav"
    with wave.open(str(destino), "wb") as unido:
        unido.setnchannels(1)
        unido.setsampwidth(2)
        unido.setframerate(24000)
        for i, cena in enumerate(cenas):
            mp3 = pasta / f"voz_{i}.mp3"
            wav = pasta / f"voz_{i}.wav"
            gerar_voz(cena["narracao"], mp3)
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(mp3),
                            "-ar", "24000", "-ac", "1", "-c:a", "pcm_s16le", str(wav)],
                           check=True, timeout=FFMPEG_TIMEOUT_SEGUNDOS)
            with wave.open(str(wav), "rb") as trecho:
                duracao = trecho.getnframes() / trecho.getframerate()
                unido.writeframes(trecho.readframes(trecho.getnframes()))
            timeline.append({**cena, "inicio": inicio, "duracao": duracao})
            inicio += duracao
    (pasta / "plano_cenas.json").write_text(
        json.dumps(timeline, ensure_ascii=False, indent=2), encoding="utf-8")
    return destino, timeline


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
        # Não substituir uma cena específica por natureza ou outro tema aleatório.
        return False
    termos = set(re.findall(r"[a-z]+", palavra_chave.lower()))
    def relevancia(video):
        tags = set(re.findall(r"[a-z]+", video.get("tags", "").lower()))
        return len(termos & tags)
    videos.sort(key=relevancia, reverse=True)
    video = videos[0]
    if relevancia(video) == 0:
        return False
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
    video_resp.raise_for_status()
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
            raise RuntimeError(f"Sem clipe relevante para a cena {i}: {palavra}")
    return clipes


# ----------------------------------------------------------------
# 4a-2. Gerar imagem com IA (Stability AI) + efeito Ken Burns
# ----------------------------------------------------------------
class ImagemModeradaError(RuntimeError):
    """Pedido recusado pelo sistema de moderação do provedor."""


def visual_de_ambiente(cena: str) -> str:
    """Substitui a ação por um plano do cenário, sem tentar reproduzir o conteúdo recusado."""
    locais = {
        "living room": "an empty living room in an apartment",
        "bedroom": "an empty bedroom in an apartment",
        "kitchen": "an empty kitchen in an apartment",
        "hallway": "an empty hallway in an apartment building",
        "corridor": "an empty corridor in a building",
        "bathroom": "an empty bathroom in an apartment",
        "forest": "a quiet forest path",
        "road": "a quiet country road",
        "street": "a quiet city street",
        "office": "an empty office",
        "hotel": "an empty hotel lobby",
        "car": "the interior of a parked car",
    }
    texto = cena.lower()
    candidatos = [(m.start(), descricao) for palavra, descricao in locais.items()
                  if (m := re.search(r"\b" + re.escape(palavra) + r"\b", texto))]
    local = min(candidatos)[1] if candidatos else "a quiet garden path at sunrise"
    return (f"Architectural establishing photograph of {local}, "
            "soft indirect lighting, natural materials, realistic proportions, "
            "neutral everyday setting, unoccupied, cinematic composition, vertical frame")


def gerar_imagem_com_alternativa(cena: str, destino: Path):
    registro = destino.with_suffix(".alternativa.json")
    if registro.exists():
        alternativa = json.loads(registro.read_text(encoding="utf-8"))
        if alternativa.get("original") != cena:
            raise ValueError("O plano mudou desde a tentativa anterior; revise o registro da cena.")
        # Uma retomada explícita utiliza diretamente o plano alternativo já registrado.
        gerar_imagem_stability(alternativa["visual"], destino)
        return
    try:
        gerar_imagem_stability(cena, destino)
    except ImagemModeradaError:
        visual = visual_de_ambiente(cena)
        registro.write_text(json.dumps({"original": cena, "visual": visual,
            "motivo": "content_moderation", "tipo": "plano de ambiente sem personagens"},
            ensure_ascii=False, indent=2), encoding="utf-8")
        print("    Cena recusada por moderação. Tentando uma única alternativa de ambiente, "
              "sem personagens ou ações. Se aceita, a imagem poderá ser cobrada.")
        gerar_imagem_stability(visual, destino)


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
    if not resp.ok:
        # Exibe apenas o diagnóstico do serviço, nunca cabeçalhos de autenticação.
        try:
            corpo = resp.json()
        except ValueError:
            corpo = {}
        nome = str(corpo.get("name", "")) if isinstance(corpo, dict) else ""
        erros = corpo.get("errors", []) if isinstance(corpo, dict) else []
        detalhe = str(erros)[:600]
        # Protege inclusive uma eventual mensagem do serviço que ecoe a chave.
        chave = str(getattr(config, "STABILITY_API_KEY", ""))
        if chave:
            detalhe = detalhe.replace(chave, "[CHAVE OCULTA]")
            nome = nome.replace(chave, "[CHAVE OCULTA]")
        tipo_erro = (ImagemModeradaError if resp.status_code == 403
                     and nome == "content_moderation" else RuntimeError)
        raise tipo_erro(
            f"Stability HTTP {resp.status_code}: {nome or 'sem código de motivo'}. "
            f"Detalhes: {detalhe}. Os arquivos concluídos foram preservados. "
            "Não haverá nova chamada automática para essa imagem.")
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
    frames = max(1, round(duracao * fps))
    passo_zoom = 0.15 / max(frames - 1, 1)
    if zoom_out:
        expressao_zoom = f"if(eq(on,0),1.15,max(zoom-{passo_zoom:.10f},1.0))"
    else:
        expressao_zoom = f"min(1+on*{passo_zoom:.10f},1.15)"
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


def montar_banco_de_imagens(cenas: list, pasta: Path, duracoes: list | None = None) -> list:
    """Equivalente a montar_banco_de_clipes, mas gerando as imagens por IA
    em vez de baixar do Pixabay."""
    if len(cenas) > MAX_IMAGENS:
        raise ValueError("Limite de 6 imagens por vídeo excedido; nenhuma imagem será solicitada.")
    clipes = []
    for i, cena in enumerate(cenas):
        imagem_path = pasta / f"imagem_{i}.png"
        clipe_path = pasta / f"clipe_{i}.mp4"
        resumo = cena[:60] + ("..." if len(cena) > 60 else "")
        print(f"    Gerando imagem IA ({i+1}/{len(cenas)}): '{resumo}'")
        try:
            tempo = duracoes[i] if duracoes else MAX_SEGUNDOS_POR_CLIPE
            if clipe_path.exists():
                try:
                    if abs(obter_duracao_segundos(clipe_path) - tempo) < 0.1:
                        print(f"    Reutilizando clipe_{i}.mp4 (sem chamada à API)")
                        clipes.append(clipe_path)
                        continue
                except (subprocess.CalledProcessError, ValueError):
                    pass  # Arquivo incompleto: reconstruir a partir da imagem salva.
            if imagem_path.exists() and imagem_path.stat().st_size > 0:
                subprocess.run(["ffprobe", "-v", "error", str(imagem_path)],
                               check=True, capture_output=True, timeout=30)
                print(f"    Reutilizando imagem_{i}.png (sem chamada à API)")
            else:
                gerar_imagem_com_alternativa(cena, imagem_path)
            gerar_clipe_com_ken_burns(
                imagem_path, clipe_path, pasta,
                duracao=duracoes[i] if duracoes else MAX_SEGUNDOS_POR_CLIPE,
                zoom_out=(i % 2 == 1)
            )
            clipes.append(clipe_path)
            print(f"    OK: clipe_{i}.mp4 gerado (imagem + Ken Burns)")
        except Exception as e:
            raise RuntimeError(
                f"Falha na cena {i + 1}/{len(cenas)} (imagem_{i}.png): {e}\n"
                f'Para retomar: python gerar_video.py --retomar "{pasta.resolve()}"'
            ) from e
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


def preparar_logo_faixa():
    # Identidade própria ainda não definida: nunca baixa a marca do suspense.
    # Para ativar, salve uma faixa horizontal em assets/logo_faixa.png.
    return


def filtro_mixagem_musica(duracao: float, indice_musica: int) -> str:
    # Normaliza as fontes para reduzir diferenças entre músicas. O sidechain
    # abaixa a trilha durante a voz e a libera gradualmente nas pausas.
    ganho = float(getattr(config, "MUSICA_VOLUME", 0.65))
    if not 0 <= ganho <= 2:
        raise ValueError("MUSICA_VOLUME deve estar entre 0 e 2.")
    return (
        "[1:a]loudnorm=I=-16:TP=-2:LRA=7,aresample=48000,"
        "asplit=2[voz][controle];"
        f"[{indice_musica}:a]atrim=duration={duracao},asetpts=PTS-STARTPTS,"
        f"loudnorm=I=-20:TP=-2:LRA=7,aresample=48000,volume={ganho}[trilha];"
        "[trilha][controle]sidechaincompress=threshold=0.08:ratio=3:"
        "attack=30:release=450:makeup=1:link=average[trilha_baixa];"
        "[voz][trilha_baixa]amix=inputs=2:duration=first:normalize=0:"
        "dropout_transition=0,alimiter=limit=0.95:level=0:latency=1[aout]"
    )


def montar_video(
    clipes: list, audio_path: Path, legenda_path: Path, saida_path: Path,
    musica_path: Path | None = None, segmentos: list | None = None,
):
    pasta = saida_path.parent
    duracao = obter_duracao_segundos(audio_path)

    if not clipes:
        raise ValueError("Nenhuma cena disponível para montagem.")
    if segmentos is not None and len(segmentos) != len(clipes):
        raise ValueError("Quantidade de clipes diferente da quantidade de cenas.")
    duracoes = ([c["duracao"] for c in segmentos] if segmentos is not None
                else [duracao / len(clipes)] * len(clipes))
    if abs(sum(duracoes) - duracao) > 0.1:
        raise ValueError("A duração das cenas não corresponde à narração.")
    comando = ["ffmpeg", "-y", "-filter_complex_threads", "2"]
    partes = []
    for i, (clipe, tempo) in enumerate(zip(clipes, duracoes)):
        comando += ["-stream_loop", "-1", "-i", str(clipe.resolve())]
        filtro = (f"[{i}:v]scale=1080:1920:force_original_aspect_ratio=increase,"
                  "crop=1080:1920,setsar=1,fps=30,format=yuv420p,"
                  f"trim=duration={tempo:.6f},setpts=PTS-STARTPTS")
        if segmentos and segmentos[i].get("corte") == "suave" and i < len(clipes)-1:
            fade = min(0.15, tempo / 4)
            filtro += f",fade=t=out:st={tempo-fade:.6f}:d={fade:.6f}"
        partes.append(filtro + f"[v{i}]")
    entradas = "".join(f"[v{i}]" for i in range(len(clipes)))
    partes.append(f"{entradas}concat=n={len(clipes)}:v=1:a=0[outv]")
    comando += ["-filter_complex", ";".join(partes), "-map", "[outv]",
                "-c:v", "libx264", "-threads", "2", "-preset", "veryfast",
                "-t", str(duracao), "concatenado.mp4"]
    subprocess.run(comando, check=True, cwd=str(pasta), timeout=FFMPEG_TIMEOUT_SEGUNDOS)

    # Verifica se a legenda existe e tem conteúdo real antes de tentar usá-la.
    legenda_ok = legenda_path.exists() and legenda_path.stat().st_size > 10
    if not legenda_ok:
        print("    AVISO: legenda.ass não foi gerada corretamente (arquivo "
              "ausente ou vazio). A montagem será interrompida.")

    tem_musica = musica_path is not None
    if tem_musica:
        print(f"    Trilha sonora: {musica_path.name}")

    preparar_logo_faixa()
    tem_logo = LOGO_FAIXA_PATH.exists()
    if not tem_logo:
        print(f"    (sem faixa de logo — arquivo não encontrado em {LOGO_FAIXA_PATH})")

    def _rodar(com_legenda: bool, com_onda: bool):
        comando = [
            "ffmpeg", "-y", "-filter_complex_threads", "2",
            "-i", "concatenado.mp4",  # input 0: vídeo
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
            # Fonte, contorno e entrada suave são definidos no arquivo ASS.
            filtro_video += f",subtitles={legenda_path.name}"

        if com_onda:
            # Onda amarela encorpada, com o fundo escuro ainda discreto.
            filtro_video += (
                ",drawbox=x=40:y=160:w=1000:h=220:"
                "color=black@0.16:t=fill[base]"
            )
            filtro_onda = (
                "[1:a]aformat=channel_layouts=mono,"
                "acompressor=threshold=0.125:ratio=4:attack=20:release=180:makeup=1,"
                "volume=1.0,showwaves=s=960x180:mode=cline:rate=30:"
                "colors=0xE5C777:scale=sqrt:draw=full,format=rgba,"
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
                f";[{indice_logo}:v]scale=1080:-2,crop=1080:180,setsar=1[marca];"
                f"[{label_atual}][marca]overlay=0:main_h-overlay_h:eof_action=repeat[vout]"
            )
        else:
            filtro_video += f";[{label_atual}]null[vout]"

        if tem_musica:
            filtro_audio = filtro_mixagem_musica(duracao, indice_musica)
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
            "-c:v", "libx264", "-threads", "2", "-preset", "veryfast", "-crf", "23",
            "-c:a", "aac", "-b:a", "128k",
            saida_path.name,
        ]
        subprocess.run(
            comando, check=True, cwd=str(pasta), timeout=FFMPEG_TIMEOUT_SEGUNDOS,
        )

    if not legenda_ok:
        raise RuntimeError("Legenda ausente: vídeo não será enviado sem legenda.")
    # Uma falha de montagem deve ficar visível, sem publicar uma versão degradada.
    _rodar(com_legenda=True, com_onda=True)


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
def ajustar_duracao_narracao(audio: Path, segmentos: list, pasta: Path) -> tuple[Path, list]:
    """Mantém a fala intacta: completa a duração com pausas, nunca com aceleração."""
    import wave
    duracao = obter_duracao_segundos(audio)
    if DURACAO_MINIMA <= duracao <= DURACAO_MAXIMA:
        return audio, segmentos
    if duracao > DURACAO_MAXIMA:
        raise ValueError(
            f"A narração ficou com {duracao:.1f}s. Não será acelerada. "
            "Nenhuma imagem foi solicitada nesta etapa. Encurte os trechos do roteiro.json "
            "salvo e use --roteiro para narrar novamente, sem outra chamada à Anthropic.")
    if not segmentos or abs(sum(c["duracao"] for c in segmentos) - duracao) > 0.1:
        raise ValueError("A linha do tempo não corresponde ao áudio salvo.")
    destino = pasta / "voz_ajustada.wav"
    ajustados = []
    with wave.open(str(audio), "rb") as origem:
        parametros = origem.getparams()
        taxa = origem.getframerate()
        tamanho_frame = origem.getsampwidth() * origem.getnchannels()
        if origem.getsampwidth() != 2:
            raise ValueError("O áudio precisa ser PCM de 16 bits para adicionar pausas.")
        total_frames = origem.getnframes()
        frames_pausa = round(DURACAO_ALVO * taxa) - total_frames
        conteudo = origem.readframes(total_frames)
        posicao = 0
        fim_anterior = 0
        with wave.open(str(destino), "wb") as saida:
            saida.setparams(parametros)
            for i, cena in enumerate(segmentos):
                fim = (round((cena["inicio"] + cena["duracao"]) * taxa)
                       if i < len(segmentos) - 1 else total_frames)
                fala_frames = fim - fim_anterior
                pausa = round(frames_pausa * (i + 1) / len(segmentos)) - round(frames_pausa * i / len(segmentos))
                saida.writeframes(conteudo[fim_anterior*tamanho_frame:fim*tamanho_frame])
                saida.writeframes(b"\x00" * pausa * tamanho_frame)
                ajustados.append({**cena, "inicio": posicao / taxa,
                                  "duracao": (fala_frames + pausa) / taxa,
                                  "duracao_fala": cena.get("duracao_fala", fala_frames / taxa)})
                posicao += fala_frames + pausa
                fim_anterior = fim
    (pasta / "plano_montagem.json").write_text(
        json.dumps(ajustados, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"    Fala preservada em {duracao:.1f}s; pausas de reflexão completam {DURACAO_ALVO:.0f}s.")
    return destino, ajustados


def carregar_execucao(pasta: Path) -> tuple[dict, list, Path]:
    plano = pasta / "plano_cenas.json"
    audio = pasta / "voz.wav"
    if not plano.is_file() or not audio.is_file():
        raise ValueError("A pasta precisa conter plano_cenas.json e voz.wav para retomar.")
    segmentos = json.loads(plano.read_text(encoding="utf-8"))
    if not isinstance(segmentos, list) or not segmentos:
        raise ValueError("Plano de cenas vazio ou inválido.")
    fim = 0.0
    for cena in segmentos:
        if cena["duracao"] <= 0 or abs(cena["inicio"] - fim) > 0.01:
            raise ValueError("Linha de tempo inválida; nenhum serviço foi chamado.")
        fim += cena["duracao"]
    if abs(obter_duracao_segundos(audio) - fim) > 0.1:
        raise ValueError("O áudio salvo não corresponde à duração do plano.")
    roteiro_path = pasta / "roteiro.json"
    # Compatibilidade com a primeira versão, que salvou apenas o plano.
    dados = (json.loads(roteiro_path.read_text(encoding="utf-8")) if roteiro_path.exists()
             else {"tema": "História retomada", "roteiro": " ".join(c["narracao"] for c in segmentos)})
    return dados, segmentos, audio


def main():
    parser = argparse.ArgumentParser(description="Gerar ou retomar um vídeo.")
    parser.add_argument("--retomar", type=Path, help="Pasta da execução interrompida em saida.")
    parser.add_argument("--roteiro", type=Path, help="Usar resposta JSON salva sem chamar a Anthropic.")
    parser.add_argument("--teste-voz", action="store_true", help="Amostra Edge TTS sem Anthropic ou Stability.")
    args = parser.parse_args()
    if args.teste_voz:
        if args.retomar or args.roteiro:
            parser.error("Use --teste-voz sozinho.")
        amostra = BASE_DIR / "teste_voz.mp3"
        texto = ("Que este novo dia seja uma oportunidade de aprender. "
                 "Respire com tranquilidade. Que nossas escolhas expressem bondade, "
                 "paciência e respeito por quem caminha ao nosso lado.")
        asyncio.run(_gerar_voz_edge_tts_async(texto, amostra))
        print(f"Amostra salva em {amostra.resolve()}. Sem Anthropic ou Stability.")
        return
    if args.retomar and args.roteiro:
        parser.error("Use --retomar ou --roteiro, não ambos.")
    print(f"[{datetime.now()}] Iniciando geração de vídeo...")
    if args.retomar:
        pasta_trabalho = args.retomar.resolve()
        dados, segmentos, audio_path = carregar_execucao(pasta_trabalho)
        if dados.get("data_mensagem") != contexto_do_dia()["data"]:
            raise ValueError("A mensagem salva é de outra data. Gere uma mensagem nova para hoje.")
        print("    Retomando roteiro e narração salvos (sem novas chamadas para essas etapas).")
    else:
        pasta_trabalho = SAIDA_DIR / datetime.now().strftime("%Y%m%d_%H%M%S")
        pasta_trabalho.mkdir(parents=True, exist_ok=True)
        print("1/5 Gerando roteiro...")
        if args.roteiro:
            texto = args.roteiro.read_text(encoding="utf-8-sig").strip()
            texto = re.sub(r"^```(?:json)?\s*|\s*```$", "", texto).strip()
            dados = aplicar_data(preparar_roteiro(json.loads(texto)), contexto_do_dia())
            print("    Usando roteiro salvo (sem chamada à Anthropic).")
        else:
            dados = gerar_roteiro(pasta_trabalho)
        (pasta_trabalho / "roteiro.json").write_text(
            json.dumps(dados, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"    Categoria: {escolher_categoria()}")
        print(f"    Tema: {dados['tema']}")
        print("2/5 Gerando voz e legenda...")
        dados, audio_path, segmentos = narrar_com_limite(dados, pasta_trabalho)
    if len(segmentos) > MAX_IMAGENS:
        raise ValueError("Essa execução antiga tem mais de 6 cenas. Para o novo formato econômico, "
                         "execute python gerar_video.py para criar um vídeo novo.")
    audio_path, segmentos = ajustar_duracao_narracao(audio_path, segmentos, pasta_trabalho)
    legenda_path = pasta_trabalho / "legenda.ass"
    duracao_audio = obter_duracao_segundos(audio_path)
    gerar_legenda_por_tempo(dados["roteiro"], duracao_audio, legenda_path, segmentos=segmentos)
    print(f"    (voz com {duracao_audio:.1f}s, legenda.ass gerada com "
          f"{legenda_path.stat().st_size} bytes)")

    usar_ia = getattr(config, "USAR_IMAGENS_IA", False)
    if usar_ia:
        print("3/5 Gerando imagens com IA (Stability AI)...")
        clipes = montar_banco_de_imagens([c["visual"] for c in segmentos], pasta_trabalho,
                                         duracoes=[c["duracao"] for c in segmentos])
    else:
        print("3/5 Baixando clipes...")
        clipes = montar_banco_de_clipes([c["busca"] for c in segmentos], pasta_trabalho)
    if not clipes:
        print("    Nenhum clipe/imagem disponível. Abortando.")
        return

    print("4/5 Montando vídeo final...")
    video_final = pasta_trabalho / "video_final.mp4"
    musica_path = escolher_musica()
    if musica_path is None:
        print("    (nenhuma música encontrada na pasta 'musica/' — "
              "vídeo sai só com a narração)")
    montar_video(clipes, audio_path, legenda_path, video_final, musica_path, segmentos=segmentos)

    print("5/5 Enviando para aprovação no Telegram...")
    enviar_para_telegram(video_final, f"{dados['tema']}\nReflexão autoral inspirada nos princípios espíritas.\n\n{dados['roteiro']}")

    salvar_tema_usado(dados["tema"])
    print(f"[{datetime.now()}] Concluído! Vídeo em: {video_final}")


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, ValueError) as erro:
        print(f"\nERRO: {erro}")
        raise SystemExit(1)
