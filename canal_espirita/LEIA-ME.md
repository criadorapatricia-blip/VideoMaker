# Canal espírita — pasta independente

Extraia esta pasta para `F:\canal_espirita`. Ela não usa nem altera os arquivos
de `F:\canal` (suspense). Python, FFmpeg e dependências já instalados podem ser
reutilizados. Não precisa criar outra instalação do Python.

1. Copie `config_exemplo.py` para `config.py` nesta pasta.
2. No seu computador, preencha as chaves Anthropic e Stability e os dados do Telegram.
   Pode reutilizar Anthropic e Telegram; a chave Stability pode ser própria deste canal.
   Não envie o arquivo preenchido para o GitHub ou chat.
3. Coloque músicas instrumentais com licença adequada em `musica` (MP3 ou WAV).
   Sem músicas, o vídeo sai só com narração. As músicas do suspense não são usadas.
4. No Prompt de Comando:

```bat
cd /d F:\canal_espirita
python gerar_video.py
```

Isso faz chamadas reais e pode consumir créditos. O pacote não inclui chaves,
músicas ou vídeos gerados. Não há agendamento novo; o do suspense continua intacto.

## Padrão inicial

- Voz masculina `pt-BR-AntonioNeural`, velocidade `-8%` e tom `-2Hz`.
  É a mesma voz-base disponível no Edge TTS, com ajuste de tom e velocidade
  próprio; a naturalidade precisa ser avaliada ouvindo seu primeiro teste.
- Até seis imagens Stability, vídeo de 62–65 segundos, legenda e movimento suave.
- Música própria, normalizada, com redução automática durante a fala.
- Onda em dourado suave. Nenhuma logo do suspense é baixada ou usada.
- Para acrescentar a identidade futura, salve uma faixa horizontal 6:1 em
  `assets/logo_faixa.png`. A marca e o nome deste canal ainda não foram definidos.
- Textos autorais, não citações ou mensagens atribuídas a Kardec/espíritos.
- Dia e data calculados pelo relógio do seu Windows, em português.
  Confira o relógio e o fuso antes de gerar.
- Histórico separado em `temas_usados.json`, saídas em `saida`, criados na primeira execução.

O texto aborda caridade, reforma íntima, perdão, responsabilidade e prece, com
referências de estudo à codificação. Isso orienta o modelo, mas não substitui
sua revisão doutrinária. As referências são salvas em `roteiro.json`; não são
apresentadas como fonte literal da reflexão nem narradas como citações.

Se um roteiro falhar, a resposta é preservada, sem segunda chamada automática.
Execução interrompida no mesmo dia pode ser retomada:

```bat
python gerar_video.py --retomar "saida\NOME_DA_PASTA"
```

Uma mensagem com data antiga não é retomada em outro dia. Não reutilize pastas
ou roteiros do canal de suspense. Uma imagem recusada por moderação pode provocar
uma única tentativa de plano alternativo de ambiente; imagens aceitas podem ser cobradas.

## Validação

Testes locais foram feitos com respostas e mídia sintéticas, sem chamadas pagas.
Geração completa nas APIs, voz real e avaliação doutrinária ficam para seu teste
no Windows. Mantenha revisão e postagem manuais nesta fase.
