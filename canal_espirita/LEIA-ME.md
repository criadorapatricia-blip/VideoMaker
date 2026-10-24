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

- Voz masculina `pt-BR-AntonioNeural`, velocidade `-20%` e tom `-12Hz`.
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

## Revisão da voz: fala lenta e texto curto

O roteiro agora pede 65 a 80 palavras antes da abertura com dia e data.
A duração não é mais ajustada acelerando a voz: se faltar tempo, o programa
acrescenta pausas entre as cenas e após a prece. As legendas desaparecem nas
pausas. Se a fala passar de 65 segundos, a execução para antes das imagens,
sem encurtar ou acelerar o áudio; revise o texto salvo e use `--roteiro`.

Para atualizar uma instalação existente, mantenha seu config.py e suas músicas.
Substitua gerar_video.py e altere SOMENTE estas linhas no config.py:

```python
VOZ_RATE = "-20%"
VOZ_PITCH = "-12Hz"
```

Os valores do seu config.py têm prioridade sobre os padrões do programa.
Não substitua config.py pelo modelo, pois isso apagaria as suas configurações.

Antes de gerar outro vídeo, pode ouvir uma amostra do Edge TTS:

```bat
python gerar_video.py --teste-voz
```

Cria `teste_voz.mp3` nesta pasta, sem Anthropic, Stability ou ElevenLabs.
Requer internet para o Edge TTS. A amostra permite avaliar o timbre no seu PC;
testes locais com áudio sintético não avaliam a naturalidade da voz real.
Use uma geração nova para avaliar a nova voz: `--retomar` reutiliza o áudio salvo.
