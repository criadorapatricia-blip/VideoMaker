"""
Copie este arquivo para "config.py" e preencha com suas chaves reais.
NUNCA compartilhe o config.py publicamente (não suba pro GitHub, não envie pra ninguém).
"""

# Chave da API da Anthropic (console.anthropic.com -> API Keys)
ANTHROPIC_API_KEY = "sua_chave_aqui"

# Chave da API do Pixabay (pixabay.com/api/docs -> aparece a chave na página)
PIXABAY_API_KEY = "sua_chave_aqui"

# Chave da API da Stability AI (platform.stability.ai -> API Keys)
# Só é necessária se USAR_IMAGENS_IA estiver True.
STABILITY_API_KEY = "sua_chave_aqui"

# True = gera o visual com imagens de IA (Stability) + efeito Ken Burns
# False = usa o banco de vídeos gratuito do Pixabay (padrão)
USAR_IMAGENS_IA = False

# ----------------------------------------------------------------
# Narração (voz)
# ----------------------------------------------------------------
# Vozes em português do Brasil disponíveis no edge-tts:
#   pt-BR-AntonioNeural   -> masculina (padrão atual)
#   pt-BR-FranciscaNeural -> feminina
# Pra ver a lista completa e atualizada de vozes (inclusive de Portugal e
# outros idiomas), rode no terminal: python -m edge_tts --list-voices
VOZ = "pt-BR-AntonioNeural"

# Velocidade da fala. "+0%" é normal. Negativo = mais devagar (bom pra
# suspense/mistério, dá mais peso à narração). Positivo = mais rápido.
# Exemplos: "-15%", "-10%", "+10%"
VOZ_RATE = "-10%"

# Tom da voz. "+0Hz" é normal. Negativo = mais grave (também combina bem
# com suspense). Positivo = mais aguda.
# Exemplos: "-10Hz", "-5Hz", "+5Hz"
VOZ_PITCH = "-5Hz"

# ----------------------------------------------------------------
# ElevenLabs (opcional, PAGO — deixado pronto mas desligado por padrão)
# ----------------------------------------------------------------
# Narração com qualidade bem superior ao edge-tts, mas cobrada por
# caractere. Só vale a pena ativar depois de validar que o canal engaja.
# Guia rápido pra ativar quando chegar a hora:
#   1. Crie conta em elevenlabs.io e assine um plano pago (o gratuito não
#      dá direito de uso comercial)
#   2. Pegue sua chave em Settings -> API Keys
#   3. Escolha uma voz em elevenlabs.io/app/voice-library e copie o Voice ID
#   4. Preencha as 3 linhas abaixo e troque USAR_ELEVENLABS para True

USAR_ELEVENLABS = False

ELEVENLABS_API_KEY = "sua_chave_aqui"

# ID de uma voz da biblioteca da ElevenLabs. O valor abaixo é a voz
# "Rachel" (padrão, multilíngue) só como exemplo — troque pela que você
# escolher.
ELEVENLABS_VOICE_ID = "21m00Tcm4TlvDq8ikWAM"

# "eleven_flash_v2_5" = mais barato (US$ 0,05/1000 caracteres)
# "eleven_multilingual_v2" = melhor qualidade (US$ 0,10/1000 caracteres)
ELEVENLABS_MODEL = "eleven_flash_v2_5"

# Token do seu bot no Telegram (fale com @BotFather no Telegram)
TELEGRAM_BOT_TOKEN = "seu_token_aqui"

# ID do chat para onde o bot deve enviar os vídeos.
# Forma mais fácil de descobrir: mande uma mensagem pro seu bot,
# depois acesse no navegador:
# https://api.telegram.org/bot<SEU_TOKEN>/getUpdates
# e procure o número em "chat": {"id": ...}
TELEGRAM_CHAT_ID = "seu_chat_id_aqui"
