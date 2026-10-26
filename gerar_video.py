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

import config  # suas chaves ficam em config.py (veja config_exemplo.py)

# ----------------------------------------------------------------
# Pastas de trabalho
# ----------------------------------------------------------------
BASE_DIR = Path(__file__).parent
SAIDA_DIR = BASE_DIR / "saida"
MUSICA_DIR = BASE_DIR / "musica"
TEMAS_USADOS_PATH = BASE_DIR / "temas_usados.json"
CIDADES_USADAS_PATH = BASE_DIR / "cidades_usadas.json"
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
LOGO_FAIXA_URL = "https://raw.githubusercontent.com/criadorapatricia-blip/VideoMaker/main/assets/logo_faixa.png"
LOGO_FAIXA_SHA256 = "0c9624ce35c688530f75e4036db676b76113dbaf5bc11782c812810bbbb35207"



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
# "creepypasta"). Cidades brasileiras reais servem apenas de ambientação;
# personagens, imóveis e acontecimentos continuam inventados.
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


CAPITAIS_BRASILEIRAS = [
    "Rio Branco/AC", "Maceió/AL", "Macapá/AP", "Manaus/AM",
    "Salvador/BA", "Fortaleza/CE", "Brasília/DF", "Vitória/ES",
    "Goiânia/GO", "São Luís/MA", "Cuiabá/MT", "Campo Grande/MS",
    "Belo Horizonte/MG", "Belém/PA", "João Pessoa/PB", "Curitiba/PR",
    "Recife/PE", "Teresina/PI", "Rio de Janeiro/RJ", "Natal/RN",
    "Porto Alegre/RS", "Porto Velho/RO", "Boa Vista/RR",
    "Florianópolis/SC", "São Paulo/SP", "Aracaju/SE", "Palmas/TO",
]
CIDADES_GRANDES_BRASILEIRAS = [
    "Campinas/SP", "Guarulhos/SP", "São Bernardo do Campo/SP",
    "Santo André/SP", "Osasco/SP", "Sorocaba/SP", "Ribeirão Preto/SP",
    "São José dos Campos/SP", "São José do Rio Preto/SP", "Santos/SP",
    "Piracicaba/SP", "Jundiaí/SP", "Bauru/SP",
    "Uberlândia/MG", "Contagem/MG", "Juiz de Fora/MG",
    "Betim/MG", "Montes Claros/MG", "Uberaba/MG",
    "Joinville/SC", "Blumenau/SC", "Chapecó/SC", "Itajaí/SC",
    "Londrina/PR", "Maringá/PR", "Cascavel/PR",
    "Ponta Grossa/PR", "Foz do Iguaçu/PR",
    "Caxias do Sul/RS", "Pelotas/RS", "Canoas/RS", "Santa Maria/RS",
    "Feira de Santana/BA", "Vitória da Conquista/BA",
    "Caruaru/PE", "Petrolina/PE", "Jaboatão dos Guararapes/PE",
    "Olinda/PE", "Ananindeua/PA", "Santarém/PA",
    "Aparecida de Goiânia/GO", "Anápolis/GO",
    "Serra/ES", "Vila Velha/ES", "Cariacica/ES",
    "Duque de Caxias/RJ", "Niterói/RJ", "Nova Iguaçu/RJ",
    "São Gonçalo/RJ", "Campina Grande/PB", "Mossoró/RN",
    "Juazeiro do Norte/CE", "Maracanaú/CE", "Imperatriz/MA",
    "Dourados/MS", "Rondonópolis/MT", "Várzea Grande/MT",
    "Arapiraca/AL", "Parnaíba/PI",
]


def carregar_cidades_usadas() -> list:
    if not CIDADES_USADAS_PATH.exists():
        # Já apareceram em vídeos anteriores informados pelo usuário.
        return ["Ribeirão Preto/SP", "Belo Horizonte/MG"]
    try:
        historico = json.loads(CIDADES_USADAS_PATH.read_text(encoding="utf-8-sig"))
    except (ValueError, OSError) as erro:
        raise ValueError("Não foi possível ler cidades_usadas.json; revise o arquivo antes de gerar.") from erro
    if not isinstance(historico, list) or not all(isinstance(c, str) for c in historico):
        raise ValueError("cidades_usadas.json deve conter uma lista de cidades em texto.")
    return historico


def escolher_cidade_brasileira() -> dict:
    recentes = set(carregar_cidades_usadas()[-15:])
    capitais = [c for c in CAPITAIS_BRASILEIRAS if c not in recentes]
    grandes = [c for c in CIDADES_GRANDES_BRASILEIRAS if c not in recentes]
    grupo = random.choices([capitais, grandes], weights=[55, 45], k=1)[0]
    nome, uf = random.choice(grupo).rsplit("/", 1)
    return {"nome": nome, "uf": uf}


def registrar_cidade_usada(cidade: dict):
    historico = carregar_cidades_usadas()
    historico.append(f"{cidade['nome']}/{cidade['uf']}")
    temporario = CIDADES_USADAS_PATH.with_name(CIDADES_USADAS_PATH.name + ".tmp")
    try:
        temporario.write_text(json.dumps(historico[-100:], ensure_ascii=False, indent=2), encoding="utf-8")
        temporario.replace(CIDADES_USADAS_PATH)
    except OSError as erro:
        raise RuntimeError("O roteiro foi recebido, mas não foi possível salvar cidades_usadas.json.") from erro


def aplicar_cidade_ao_roteiro(dados: dict, cidade: dict) -> dict:
    pronto = preparar_roteiro(dados)
    primeira = pronto["plano_cenas"][0]["narracao"]
    primeira_frase = re.split(r"(?<=[.!?])\s+", primeira)[0]
    if not re.search(r"\b" + re.escape(cidade["nome"]) + r"\b", primeira_frase, re.IGNORECASE):
        pronto["plano_cenas"][0]["narracao"] = f"Em {cidade['nome']}, tudo começou assim. {primeira}"
        pronto["roteiro"] = " ".join(c["narracao"] for c in pronto["plano_cenas"])
    pronto["cidade"] = cidade
    pronto["aviso_ficcao"] = "História fictícia ambientada no Brasil."
    validar_plano_cenas(pronto)
    return pronto


def gerar_roteiro(pasta: Path) -> dict:
    cidade = escolher_cidade_brasileira()
    print(f"    Cidade sorteada: {cidade['nome']} ({cidade['uf']})")
    client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
    prompt = f"""Escreva uma história curta de suspense psicológico FICTÍCIA, em primeira
pessoa, em português brasileiro. Categoria: {escolher_categoria()}.
AMBIENTAÇÃO OBRIGATÓRIA: {cidade['nome']}, {cidade['uf']}, Brasil.
Mencione o nome exato "{cidade['nome']}" na PRIMEIRA FRASE do gancho, naturalmente.
A cidade é real, mas personagens, imóveis e acontecimentos são inventados.
Não use nomes de pessoas reais, endereços ou estabelecimentos identificáveis.
Não apresente o relato como caso real, notícia ou lenda documentada.
Não invente fatos históricos nem características locais específicas.
Não transfira a história para outra cidade. A localização deve fazer parte da
situação, sem transformar o roteiro numa apresentação turística.
Use 115 a 140 palavras de narração NO TOTAL, divididas em exatamente SEIS cenas.
Comece com um gancho, desenvolva contexto e sinais estranhos, aumente a tensão
e termine com uma reviravolta. Use personagens e imóveis inventados, sem violência
gráfica. Cada cena deve conter uma ação visual principal e terminar em pausa natural.
Não repita ideias recentes: {carregar_temas_usados()[-30:]}

Responda APENAS com um objeto JSON contendo tema e plano_cenas.
Exemplo de estrutura (repita o objeto de cena até completar seis cenas):
{{"tema": "Título", "plano_cenas": [
  {{"narracao": "Trecho narrado em português.",
    "visual": "Description in English of the exact location and action being narrated",
    "busca": "concrete English search terms", "corte": "seco"}}
]}}
Os seis trechos narracao, juntos, formam a história inteira. NÃO inclua outra chave
roteiro nem listas paralelas de cenas ou palavras-chave: escreva o texto uma única vez.
Descrições visuais: ambientes brasileiros plausíveis e objetos cotidianos,
sem afirmar que as imagens mostram um imóvel real ou depender de monumentos.
Adequados ao público geral,
sem ferimentos, violência ou figuras ameaçadoras. Mantenha aparência do personagem
e cenário consistentes. Não inclua placas ou texto legível nas imagens.
Use corte seco no gancho e nas revelações; suave em passagens de tempo.
A imagem deve acompanhar a ação narrada sem antecipar a próxima cena."""
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
        pronto = aplicar_cidade_ao_roteiro(dados, cidade)
    except (ValueError, TypeError, KeyError, AttributeError) as erro:
        raise ValueError(
            f"Roteiro não aceito: {erro}\nResposta preservada em: {resposta_path.resolve()}\n"
            "Nenhum segundo roteiro foi solicitado e nenhuma imagem foi gerada.") from erro
    # Reserva a cidade após validar o roteiro, inclusive se a montagem precisar
    # ser retomada depois. Roteiros inválidos não entram no histórico.
    registrar_cidade_usada(cidade)
    return pronto


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
    local = min(candidatos)[1] if candidatos else "an empty room in an apartment"
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
    """Baixa a identidade visual uma única vez, sem APIs pagas ou credenciais."""
    if LOGO_FAIXA_PATH.exists():
        return
    print("    Baixando faixa do canal do GitHub (sem API paga)...")
    resposta = requests.get(LOGO_FAIXA_URL, timeout=30)
    resposta.raise_for_status()
    if hashlib.sha256(resposta.content).hexdigest() != LOGO_FAIXA_SHA256:
        raise RuntimeError("A faixa baixada não passou na verificação de integridade.")
    LOGO_FAIXA_PATH.parent.mkdir(parents=True, exist_ok=True)
    temporario = LOGO_FAIXA_PATH.with_suffix(".tmp")
    temporario.write_bytes(resposta.content)
    temporario.replace(LOGO_FAIXA_PATH)


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
                "colors=0xFFD400:scale=sqrt:draw=full,format=rgba,"
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
    args = parser.parse_args()
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
            dados = preparar_roteiro(json.loads(texto))
            print("    Usando roteiro salvo (sem chamada à Anthropic).")
        else:
            dados = gerar_roteiro(pasta_trabalho)
        (pasta_trabalho / "roteiro.json").write_text(
            json.dumps(dados, ensure_ascii=False, indent=2), encoding="utf-8")
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
    aviso = dados.get("aviso_ficcao", "História fictícia.")
    enviar_para_telegram(video_final, f"Tema: {dados['tema']}\n{aviso}\n\n{dados['roteiro']}")

    salvar_tema_usado(dados["tema"])
    print(f"[{datetime.now()}] Concluído! Vídeo em: {video_final}")


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, ValueError) as erro:
        print(f"\nERRO: {erro}")
        raise SystemExit(1)
