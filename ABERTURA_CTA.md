# Teste de abertura no canal de suspense

As novas gerações narram título curto, a frase "Já segue o canal para ver mais
histórias como essa" e então a história. A abertura também aparece nas legendas.
Ela ocupa a primeira cena; o limite continua sendo seis imagens. O prompt pede
100–115 palavras de história, reservando espaço para título e CTA dentro da
mesma duração final de 62–65 segundos. A configuração de voz permanece no config.py.

O título pedido tem 4–7 palavras. Se vier longo, o código aproveita a parte curta
antes do subtítulo ou usa uma alternativa curta; o original fica em titulo_original.
O programa evita acrescentar a cidade novamente ao gancho se ela estiver no título.
A localização continua sendo brasileira e os acontecimentos fictícios.

Atualize somente F:\canal\gerar_video.py, preservando seu config.py.
Execute python gerar_video.py para testar um vídeo novo; usa suas APIs normalmente.
Não use --retomar para avaliar a nova abertura: ele reaproveita a narração antiga.
--roteiro também pode acrescentar a abertura a um texto salvo; isso gera novamente
voz e montagem. Se o roteiro já contém os metadados da abertura, não a duplica.
Para esse modo, imagens ausentes podem ser geradas e cobradas pelo serviço.

Não há promessa de melhoria de retenção: compare o abandono nos primeiros segundos,
a conclusão e os seguidores obtidos com os vídeos sem chamada inicial.
Os testes automatizados não avaliam a naturalidade da voz real.
