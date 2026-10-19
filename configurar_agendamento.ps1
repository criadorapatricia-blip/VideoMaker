param(
    [string]$PythonExecutavel = ''
)

$ErrorActionPreference = 'Stop'
$pastaProjeto = $PSScriptRoot
$gerador = Join-Path $pastaProjeto 'gerar_video.py'
$executor = Join-Path $pastaProjeto 'executar_video_diario.ps1'
if (-not (Test-Path -LiteralPath $gerador -PathType Leaf) -or
    -not (Test-Path -LiteralPath $executor -PathType Leaf) -or
    -not (Test-Path -LiteralPath (Join-Path $pastaProjeto 'config.py') -PathType Leaf)) {
    throw 'Coloque os dois arquivos .ps1 na mesma pasta de gerar_video.py e config.py.'
}

# Descobre o mesmo interpretador usado no terminal, sem executar o gerador.
# Nao ha chamadas a Anthropic, Stability ou Telegram nesta configuracao.
if ([string]::IsNullOrWhiteSpace($PythonExecutavel)) {
    $comandoPython = Get-Command python -ErrorAction Stop
    $resultado = & $comandoPython.Source -c 'import sys; print(sys.executable)'
    if ($LASTEXITCODE -ne 0 -or -not $resultado) {
        throw 'Nao foi possivel localizar Python. Informe -PythonExecutavel com o caminho completo.'
    }
    $PythonExecutavel = ([string]($resultado | Select-Object -Last 1)).Trim()
}
if (-not (Test-Path -LiteralPath $PythonExecutavel -PathType Leaf)) {
    throw "Interpretador Python inexistente: $PythonExecutavel"
}
# Verifica dependencias sem importar config.py nem executar gerar_video.py.
& $PythonExecutavel -c "import anthropic, edge_tts, requests; import shutil,sys; sys.exit(0 if shutil.which('ffmpeg') and shutil.which('ffprobe') else 1)"
if ($LASTEXITCODE -ne 0) {
    throw 'Faltam dependencias Python, ffmpeg ou ffprobe nesse interpretador.'
}

$nomeTarefa = 'VideoMaker-GeracaoDiaria'
$usuario = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
$powershell = Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
$argumentos = '-NoProfile -NonInteractive -ExecutionPolicy Bypass -File "' + $executor +
    '" -PythonExecutavel "' + $PythonExecutavel + '"'
$acao = New-ScheduledTaskAction -Execute $powershell -Argument $argumentos -WorkingDirectory $pastaProjeto
$horario = [DateTime]::Today.AddHours(11).AddMinutes(50)
$gatilho = New-ScheduledTaskTrigger -Daily -At $horario
$configuracao = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -StartWhenAvailable `
    -WakeToRun -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Hours 2)
# Usa a sessao atual, sem pedir ou armazenar a senha do Windows.
$principal = New-ScheduledTaskPrincipal -UserId $usuario -LogonType Interactive -RunLevel Limited
$tarefa = New-ScheduledTask -Action $acao -Trigger $gatilho -Settings $configuracao -Principal $principal `
    -Description 'Gera um video diariamente as 11:50. Postagem nas redes continua manual.'
Register-ScheduledTask -TaskName $nomeTarefa -InputObject $tarefa -Force | Out-Null
$salva = Get-ScheduledTask -TaskName $nomeTarefa -ErrorAction Stop
$info = Get-ScheduledTaskInfo -TaskName $nomeTarefa -ErrorAction Stop
Write-Host ''
Write-Host 'Agendamento salvo: todos os dias as 11:50, no horario configurado neste Windows.'
Write-Host ('Pasta: ' + $pastaProjeto)
Write-Host ('Python: ' + $PythonExecutavel)
Write-Host ('Estado: ' + $salva.State + '; proxima execucao: ' + $info.NextRunTime)
Write-Host ('Registros em: ' + (Join-Path $pastaProjeto 'logs'))
Write-Host 'O computador precisa estar ligado, com internet e com sua conta conectada.'
Write-Host 'A tela pode ficar bloqueada. Se perder o horario, tenta executar quando estiver disponivel.'
Write-Host 'Nenhum video foi gerado agora. Cada execucao diaria pode consumir creditos das APIs.'
