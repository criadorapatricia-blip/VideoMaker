# Canal Automático de Curiosidades/História — Guia de Início

## O que este projeto faz
Gera um vídeo vertical (Shorts/TikTok/Reels) por execução:
roteiro de IA → voz narrada → legenda → clipes de banco → vídeo montado →
envia pra você aprovar no Telegram.

Depois de aprovado, você posta manualmente no YouTube, TikTok e Instagram
(leva ~1 minuto por plataforma). A automação do upload fica para uma fase
posterior, quando as contas de API estiverem auditadas pelas plataformas.

---

## Passo 1 — Instalar o Python
Baixe em https://python.org (marque a opção "Add Python to PATH" na instalação).

Verifique no terminal (cmd ou PowerShell):
```
python --version
```

## Passo 2 — Instalar o FFmpeg
No PowerShell (como administrador):
```
winget install ffmpeg
```
Feche e reabra o terminal depois. Verifique com:
```
ffmpeg -version
```

## Passo 3 — Instalar as bibliotecas Python
Dentro da pasta do projeto (`canal/`):
```
pip install -r requirements.txt
```

## Passo 4 — Criar suas contas e pegar as chaves

1. **Anthropic** (roteiros): https://console.anthropic.com → API Keys → Create Key
2. **Pixabay** (clipes de vídeo, gratuito):
   - Acesse https://pixabay.com/api/docs/ e crie uma conta (botão "Join")
   - Depois de logado, a própria página de documentação mostra sua chave
     em uma caixa verde perto do topo — não precisa pedir aprovação
3. **Telegram bot:**
   - Abra o Telegram, procure por **@BotFather**
   - Mande `/newbot`, escolha um nome e um username
   - Ele te dará um **token** — guarde
   - Mande qualquer mensagem pro seu bot novo (ex: "oi")
   - No navegador, acesse:
     `https://api.telegram.org/bot<SEU_TOKEN>/getUpdates`
   - Procure `"chat":{"id": ...}` — esse número é o seu `TELEGRAM_CHAT_ID`

## Passo 5 — Configurar
1. Copie `config_exemplo.py` e renomeie a cópia para `config.py`
2. Abra o `config.py` e cole suas 4 chaves/tokens

## Passo 6 — Testar
```
python gerar_video.py
```
Acompanhe o terminal. Se tudo der certo, o vídeo chega no seu Telegram em
1 a 3 minutos.

## Passo 7 — Automatizar a execução diária (Windows)
1. Abra o **Agendador de Tarefas** (pesquise no menu Iniciar)
2. Criar Tarefa Básica → nome "Gerar Video Canal"
3. Disparador: Diariamente, no horário que preferir (ex: 8h)
4. Ação: Iniciar um programa
   - Programa: `python`
   - Argumentos: `gerar_video.py`
   - Iniciar em: o caminho completo da pasta `canal` (ex: `C:\Users\SeuUsuario\canal`)
5. Salvar

Pronto — o PC precisa estar ligado no horário, mas a geração roda sozinha.

---

## Problemas comuns

**Erro "ffmpeg não é reconhecido"**
→ Reinicie o terminal/PC depois de instalar o FFmpeg.

**Erro de JSON ao gerar roteiro**
→ A IA ocasionalmente foge do formato pedido. Rode de novo. Se persistir,
me avise.

**Nenhum clipe encontrado**
→ A palavra-chave em inglês pode ser rara demais. Isso é raro e geralmente
some ao rodar de novo (a IA escolhe outro tema).

**Vídeo sem legenda aparecendo**
→ Confirme que o FFmpeg foi compilado com suporte a `libass`/subtitles
(a versão instalada via winget já vem com isso).

---

## Trilha sonora (opcional)
1. Baixe algumas músicas livres de direitos (sugestões gratuitas: YouTube
   Audio Library, Pixabay Music, Chosic — busque por "lofi", "ambient" ou
   "suspense" pro clima do canal)
2. Salve os arquivos `.mp3` dentro da pasta `canal/musica/`
3. Pronto — o script escolhe uma aleatória a cada vídeo e mixa
   automaticamente, bem mais baixa que a voz. Se a pasta estiver vazia, o
   vídeo sai só com a narração, sem travar.

## Próximos passos depois que estiver rodando bem
- Migrar para uma VPS (Ubuntu) para rodar 24h sem depender do seu PC
- Trocar o aviso manual por botões de Aprovar/Descartar reais no Telegram
- Testar o upload automático via API do YouTube quando a conta for auditada
- Adicionar música de fundo de banco livre de direitos
