# Geracao diaria as 11:50

Baixe `configurar_agendamento.ps1` e `executar_video_diario.ps1` para `F:\canal`,
ao lado de `gerar_video.py` e do seu `config.py` original. Nao coloque credenciais
nos scripts ou no GitHub.

No Prompt de Comando:

```bat
cd /d F:\canal
powershell -NoProfile -ExecutionPolicy Bypass -File ".\configurar_agendamento.ps1"
```

O comando registra/atualiza a tarefa `VideoMaker-GeracaoDiaria` para as 11:50
**do relogio do Windows**, sem executar o gerador nem usar APIs pagas agora.
A primeira execucao sera no proximo horario indicado pelo instalador.
Cada geracao agendada chama as APIs configuradas e pode consumir creditos.

Deixe o computador ligado, com internet, unidade F: acessivel e sua conta
conectada. A tela pode ficar bloqueada; sair da conta impede a execucao.
Acordar da suspensao depende do hardware e das configuracoes de energia;
um computador desligado nao sera ligado pela tarefa. Se perder o horario,
a tarefa tenta executar quando estiver disponivel (com sua sessao conectada).

Videos: `F:\canal\saida`. Logs: `F:\canal\logs`.
O resultado do Agendador reflete o codigo de saida do gerador; o gerador atual
pode terminar sem erro mesmo quando o envio ao Telegram falha. Verifique o log.
A tarefa nao reinicia automaticamente em falhas, evitando repetir gastos nas APIs.
Duas instancias agendadas nao executam simultaneamente. Evite iniciar manualmente
outra geracao durante o horario da tarefa.

Para conferir, abra `taskschd.msc` e localize a tarefa na Biblioteca.
O botao Executar inicia uma geracao real e pode consumir creditos.
Para pausar: clique com o botao direito na tarefa e escolha Desabilitar.

Os scripts foram revisados em Linux; o registro e a execucao da tarefa precisam
ser confirmados no seu Windows. Se houver erro, envie a mensagem, sem credenciais.
