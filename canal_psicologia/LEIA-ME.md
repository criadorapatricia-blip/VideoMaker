# Psicologia do cotidiano — pasta independente

Extraia para `F:\canal_psicologia`. Não usa nem altera arquivos dos canais de
suspense ou espírita. Python, FFmpeg e bibliotecas instalados podem ser reutilizados.

1. Copie `config_exemplo.py` para `config.py` nesta pasta e preencha suas chaves
   Anthropic, Stability e dados do Telegram somente no seu computador.
2. Coloque músicas instrumentais próprias e com licença adequada em `musica`
   (MP3 ou WAV). Sem músicas, funciona só com voz.
3. No Prompt de Comando:

```bat
cd /d F:\canal_psicologia
python gerar_video.py
```

Essa execução completa usa as APIs e pode consumir créditos.

## Revisar antes de gastar com imagens

```bat
python gerar_video.py --somente-roteiro
```

Usa uma chamada Anthropic, sem voz ou imagens Stability. Abra os arquivos
`saida\NOME_DA_PASTA\roteiro.json` e `revisao_roteiro.md`. O segundo reúne o texto,
a base conceitual e as referências para sua conferência. Para gerar o vídeo a partir
do texto revisado, sem solicitar outro roteiro à Anthropic:

```bat
python gerar_video.py --roteiro "saida\NOME_DA_PASTA\roteiro.json"
```

Isso gera voz e imagens e pode consumir os créditos do serviço configurado.
Se editar o texto, preserve o JSON válido e mantenha `roteiro` idêntico à união
dos trechos `narracao`, ou remova a chave `roteiro` para reconstruí-la das cenas.
Não altere o `base_id` para um assunto diferente sem revisar também o conteúdo.

## Conteúdo e referências

Temas iniciais: procrastinação, ruminação, comparação social, planos de ação,
regulação emocional e recuperação após o trabalho. Cada tópico tem uma base
editorial curta e uma referência bibliográfica em `bases_psicologia.json`.
As referências foram registradas para conferência; o programa NÃO acessa os
artigos nem pesquisa na web e não verifica automaticamente cada afirmação.

O modelo recebe instruções para se limitar à base, não criar estudos, estatísticas,
citações ou diagnósticos, não recomendar medicamentos nem prometer resultados.
Um filtro simples rejeita algumas formulações diagnósticas diretas, mas não é
uma revisão clínica completa. Revise o texto antes de publicar.

Fontes são selecionadas pelo catálogo local, não aceitas de uma lista inventada
pela IA. Consulte as referências e adapte a base editorial quando necessário.
Imagens são ilustrações geradas por IA, não registros de casos reais.

## Identidade e operação

- Até seis imagens, duração ajustada a 62–65 segundos.
- Voz inicial masculina Antonio, velocidade `-3%`, tom `+0Hz`, configurável.
- Música própria; volume reduzido automaticamente durante a fala.
- Onda azul suave. Sem logo definida; a do suspense não é baixada.
- Para ativar sua marca depois, salve faixa horizontal 6:1 em `assets/logo_faixa.png`.
- Histórico próprio em `temas_usados.json`, resultados em `saida`.
- Um roteiro é solicitado uma única vez. Erros preservam a resposta para revisão.
- Imagem recusada por moderação pode ter uma única alternativa de ambiente.
- Interrupções podem ser retomadas com `--retomar "saida\NOME_DA_PASTA"`.
- Nenhum agendamento ou publicação automática foi configurado neste pacote.

Testes sem APIs: `python -m unittest discover -s . -p "test_*.py" -v`.
Voz real e geração completa nas APIs ficam para o seu teste no Windows.
