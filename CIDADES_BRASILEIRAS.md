# Cidades brasileiras no canal de suspense

Atualize somente `F:\canal\gerar_video.py`. Preserve o `config.py`, músicas,
logo, vídeos e agendamento existentes. Não altere os geradores dos outros canais.

Nas gerações novas, o programa sorteia uma cidade antes de chamar a Anthropic.
O catálogo inclui as 27 capitais e outras cidades grandes; cobre todos os estados
e o Distrito Federal, mas não é uma relação de todos os municípios brasileiros.
O grupo das capitais tem 55% de chance; o das demais cidades, 45%.
Dentro do grupo, cidades disponíveis têm chances iguais. Não há igualdade de
probabilidade entre estados ou regiões.

As últimas 15 cidades usadas ficam fora do sorteio. O arquivo local
`cidades_usadas.json` é criado automaticamente após um roteiro válido e guarda
até 100 registros. A primeira seleção considera Ribeirão Preto e Belo Horizonte
já usadas, conforme os vídeos anteriores. Um roteiro inválido não reserva cidade.
Se a montagem falhar depois, a cidade continua reservada e o roteiro pode ser retomado.
Não envie históricos ou configurações com credenciais para o GitHub.

O nome da cidade aparece no título narrado ou na primeira frase da história.
Se o modelo esquecer, o programa acrescenta uma abertura curta com o nome e
atualiza a narração completa.
Personagens, imóveis e acontecimentos continuam fictícios. Os prompts orientam
não usar pessoas, endereços ou estabelecimentos identificáveis e não atribuir
fatos históricos inventados à cidade. Imagens são ilustrações geradas, não registros
comprovados de locais. Ainda é necessário revisar o resultado antes de publicar.

A cidade e o aviso de ficção são salvos no `roteiro.json`. O aviso também é
incluído no começo da legenda enviada ao Telegram. Use "História fictícia
ambientada no Brasil" na descrição dos posts manuais.

Não há pesquisa externa ou chamada paga extra para o sorteio. O fluxo de geração
continua usando as APIs configuradas. `--roteiro` e `--retomar` reaproveitam a
localização salva; não sorteiam outra cidade nem modificam vídeos antigos.

Testes locais novos (sem chaves reais ou chamadas pagas):

```sh
python -m unittest discover -s tests -p "test_cidades.py" -v
```
