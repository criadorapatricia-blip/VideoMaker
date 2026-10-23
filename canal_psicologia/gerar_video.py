"""Psicologia do cotidiano: explicações educativas, sem diagnóstico ou terapia.
Pasta independente, até seis imagens, 62–65 segundos. Configure config.py localmente.
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
    import config
except ModuleNotFoundError as erro:
    if erro.name != "config":
        raise
    raise SystemExit("Copie config_exemplo.py para config.py nesta pasta e configure suas chaves no computador.")

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
# Referências editoriais locais: o modelo não inventa fontes nem consulta a web.
def carregar_bases() -> list:
    return json.loads((BASE_DIR / "bases_psicologia.json").read_text(encoding="utf-8"))


def escolher_base() -> dict:
    bases = carregar_bases()
    return bases[len(carregar_temas_usados()) % len(bases)]


def escolher_categoria() -> str:
    return escolher_base()["tema"]


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


def preparar_psicologia(dados: dict, base: dict | None = None) -> dict:
    pronto = preparar_roteiro(dados)
    # Barreira simples para formulações diagnósticas diretas, não um verificador clínico.
    if re.search(r"\b(?:voc[eê]|seu parceiro|sua parceira)\s+(?:tem|[eé]|sofre de)\s+"
                 r"(?:um |uma )?(?:depress[aã]o|transtorno|narcisista|psicopata|tdah|autismo)\b",
                 pronto["roteiro"], re.IGNORECASE):
        raise ValueError("O texto contém uma formulação diagnóstica direta. Revise o roteiro salvo.")
    catalogo = {item["id"]: item for item in carregar_bases()}
    if base is None:
        identificador = dados.get("base_id")
        if identificador not in catalogo:
            raise ValueError("O roteiro precisa de um base_id válido de bases_psicologia.json.")
        base = catalogo[identificador]
    # Atribuições e fontes vêm do catálogo local, nunca de referências inventadas pela IA.
    pronto["base_id"] = base["id"]
    pronto["base_conceitual"] = base["base_conceitual"]
    pronto["fontes"] = base["fontes"]
    pronto["natureza"] = "Conteúdo educativo geral; não é diagnóstico ou orientação individual."
    return pronto


def salvar_revisao(dados: dict, pasta: Path):
    linhas = [f"# {dados['tema']}", "", dados["roteiro"], "",
              "## Base conceitual", dados["base_conceitual"], "", "## Referências para conferência"]
    linhas += [f"- {f['referencia']} — {f['url']}" for f in dados["fontes"]]
    linhas += ["", "As fontes são referências editoriais, não foram consultadas pela IA em tempo real.",
               "Confira se o texto respeita a base. Uma referência válida não verifica automaticamente cada frase.",
               "Imagens são ilustrações geradas por IA. Revise o vídeo antes de publicar."]
    (pasta / "revisao_roteiro.md").write_text("\n".join(linhas), encoding="utf-8")


def gerar_roteiro(pasta: Path) -> dict:
    client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
    base = escolher_base()
    prompt = f"""Crie um roteiro educativo sobre psicologia do cotidiano em português brasileiro.
Tema: {base['tema']}. Base permitida: {base['base_conceitual']}
Referências editoriais para o humano conferir: {json.dumps(base['fontes'], ensure_ascii=False)}
Use somente as ideias da base. Não invente estudos, citações, estatísticas,
nomes de pesquisadores, porcentagens, mecanismos cerebrais ou fontes adicionais.
Não afirme que leu os artigos. Não diagnostique o espectador nem terceiros,
não rotule pessoas como narcisistas, psicopatas ou portadoras de transtornos.
Não prescreva tratamento ou medicamentos. Não atribua causas únicas a comportamentos.
Não prometa resultados. Evite 'sempre', 'nunca', 'isso prova' ou 'a ciência garante'.
Apresente possibilidades com contexto e respeite diferenças individuais.

Escreva 115 a 140 palavras de narração NO TOTAL, distribuídas em exatamente
SEIS cenas: situação cotidiana reconhecível, explicação acessível com nuances,
uma sugestão prática simples da base e uma pergunta final para reflexão.
Acolhedor, curioso e claro, sem tom clínico, suspense, religiosidade ou julgamento.
Não peça que o público exponha diagnósticos ou experiências traumáticas.
Não repita estes títulos/abordagens recentes: {carregar_temas_usados()[-30:]}

Responda apenas JSON com tema e plano_cenas:
{{"tema": "Título", "plano_cenas": [
 {{"narracao": "Trecho narrado.", "visual": "English visual description",
   "busca": "English search terms", "corte": "suave"}}
]}}
Complete seis cenas. Não duplique a narração numa chave roteiro.
Imagens realistas de pessoas adultas e situações comuns: casa, trabalho, estudo,
conversa, descanso. Uma ação por cena, exatamente ligada ao trecho narrado.
Mantenha características de personagens consistentes. Luz natural, sem textos,
logotipos, cérebros luminosos, diagnósticos em tela ou estetização de sofrimento.
Use cortes suaves e secos conforme a mudança de ideia, sem efeitos de suspense.
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
        return preparar_psicologia(dados, base)
    except (ValueError, TypeError, KeyError, AttributeError) as erro:
        raise ValueError(
            f"Roteiro não aceito: {erro}\nResposta preservada em: {resposta_path.resolve()}\n"
            "Nenhum segundo roteiro foi solicitado e nenhuma imagem foi gerada.") from erro


# ----------------------------------------------------------------
# 3. Gerar voz — edge-tts (grátis, padrão atual) ou ElevenLabs (pago,
# melhor qualidade, desligado por padrão até você decidir ativar)
# ----------------------------------------------------------------
async def _gerar_voz_edge_tts_async(texto: str, audio_path: Path):
    voz = getattr(config, "VOZ", VOZ)
    # rate: velocidade da fala (ex: "-10%" fala mais devagar, "+15%" mais rápido)
    # pitch: tom da voz (ex: "-5Hz" fica mais grave, "+5Hz" mais aguda)
    rate = getattr(config, "VOZ_RATE", "-3%")
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
            fim = acumulado + cena["duracao"] * peso / total
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
    local = min(candidatos)[1] if candidatos else "a quiet room with natural daylight"
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
    # Marca própria ainda não definida; nunca usa a logo do suspense.
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
                "color=black@0.22:t=fill[base]"
            )
            filtro_onda = (
                "[1:a]aformat=channel_layouts=mono,"
                "acompressor=threshold=0.125:ratio=4:attack=20:release=180:makeup=1,"
                "volume=1.0,showwaves=s=960x180:mode=cline:rate=30:"
                "colors=0x78C8E8:scale=sqrt:draw=full,format=rgba,"
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
    """Ajusta o ritmo sem cortar a história nem alterar o tom da voz."""
    duracao = obter_duracao_segundos(audio)
    if DURACAO_MINIMA <= duracao <= DURACAO_MAXIMA:
        return audio, segmentos
    fator = duracao / DURACAO_ALVO
    # atempo aceita entre 0.5 e 2 por estágio, inclusive para retomadas antigas.
    fatores = []
    restante = fator
    while restante > 2:
        fatores.append(2.0)
        restante /= 2
    while restante < 0.5:
        fatores.append(0.5)
        restante /= 0.5
    fatores.append(restante)
    destino = pasta / "voz_ajustada.wav"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(audio), "-af",
                    ",".join(f"atempo={f:.10f}" for f in fatores) +
                    f",apad,atrim=duration={DURACAO_ALVO}",
                    "-ar", "24000", "-ac", "1", "-c:a", "pcm_s16le", str(destino)],
                   check=True, timeout=FFMPEG_TIMEOUT_SEGUNDOS)
    tempo_final = obter_duracao_segundos(destino)
    if not DURACAO_MINIMA <= tempo_final <= DURACAO_MAXIMA:
        raise RuntimeError("Não foi possível ajustar a duração; nenhuma imagem foi solicitada.")
    escala = tempo_final / duracao
    ajustados = [{**c, "inicio": c["inicio"] * escala, "duracao": c["duracao"] * escala}
                 for c in segmentos]
    (pasta / "plano_montagem.json").write_text(
        json.dumps(ajustados, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"    Narração ajustada de {duracao:.1f}s para {tempo_final:.1f}s, sem cortar o texto.")
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
    parser.add_argument("--somente-roteiro", action="store_true", help="Gera texto para revisar, sem voz nem imagens.")
    args = parser.parse_args()
    if args.retomar and args.somente_roteiro:
        parser.error("--somente-roteiro não pode ser usado com --retomar.")
    if args.retomar and args.roteiro:
        parser.error("Use --retomar ou --roteiro, não ambos.")
    print(f"[{datetime.now()}] Iniciando geração de vídeo...")
    if args.retomar:
        pasta_trabalho = args.retomar.resolve()
        dados, segmentos, audio_path = carregar_execucao(pasta_trabalho)
        print("    Retomando roteiro e narração salvos (sem novas chamadas para essas etapas).")
    else:
        pasta_trabalho = SAIDA_DIR / datetime.now().strftime("%Y%m%d_%H%M%S")
        pasta_trabalho.mkdir(parents=True, exist_ok=True)
        print("1/5 Gerando roteiro...")
        if args.roteiro:
            texto = args.roteiro.read_text(encoding="utf-8-sig").strip()
            texto = re.sub(r"^```(?:json)?\s*|\s*```$", "", texto).strip()
            dados = preparar_psicologia(json.loads(texto))
            print("    Usando roteiro salvo (sem chamada à Anthropic).")
        else:
            dados = gerar_roteiro(pasta_trabalho)
        (pasta_trabalho / "roteiro.json").write_text(
            json.dumps(dados, ensure_ascii=False, indent=2), encoding="utf-8")
        salvar_revisao(dados, pasta_trabalho)
        if args.somente_roteiro:
            print(f"    Texto salvo em {pasta_trabalho.resolve()}. Nenhuma imagem ou voz foi solicitada.")
            return
        print(f"    Categoria: {escolher_categoria()}")
        print(f"    Tema: {dados['tema']}")
        print("2/5 Gerando voz e legenda...")
        audio_path, segmentos = gerar_narracao_cenas(dados["plano_cenas"], pasta_trabalho)
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
    enviar_para_telegram(video_final, f"{dados['tema']}\nConteúdo educativo; imagens ilustrativas geradas por IA.\n\n{dados['roteiro']}")

    salvar_tema_usado(dados["tema"])
    print(f"[{datetime.now()}] Concluído! Vídeo em: {video_final}")


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, ValueError) as erro:
        print(f"\nERRO: {erro}")
        raise SystemExit(1)
