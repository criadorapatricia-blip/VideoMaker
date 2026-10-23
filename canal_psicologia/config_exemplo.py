"""Copie para config.py nesta pasta e configure somente no seu computador.
Nao envie config.py, chaves ou tokens para o GitHub ou para o chat.
"""
import os

# Pode reutilizar a chave Anthropic. Stability pode usar a conta escolhida para este canal.
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "sua_chave_aqui")
STABILITY_API_KEY = os.environ.get("STABILITY_API_KEY", "sua_chave_aqui")
USAR_IMAGENS_IA = True
PIXABAY_API_KEY = ""  # nao e necessario com Stability

# Voz inicial masculina, neutra e explicativa; ajuste livremente neste canal.
VOZ = "pt-BR-AntonioNeural"
VOZ_RATE = "-3%"
VOZ_PITCH = "+0Hz"
USAR_ELEVENLABS = False
MUSICA_VOLUME = 0.55

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "seu_token_aqui")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "seu_chat_id_aqui")
