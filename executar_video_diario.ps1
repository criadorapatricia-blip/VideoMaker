param(
    [Parameter(Mandatory = $true)]
    [string]$PythonExecutavel
)

$ErrorActionPreference = 'Stop'
$pastaProjeto = $PSScriptRoot
$pastaLogs = Join-Path $pastaProjeto 'logs'
New-Item -ItemType Directory -Path $pastaLogs -Force | Out-Null
$arquivoLog = Join-Path $pastaLogs ('geracao_' + (Get-Date -Format 'yyyyMMdd_HHmmss') + '.log')
$codigo = 1
try {
    Set-Location -LiteralPath $pastaProjeto
    if (-not (Test-Path -LiteralPath $PythonExecutavel -PathType Leaf)) {
        throw 'Python nao encontrado. Execute novamente configurar_agendamento.ps1.'
    }
    ('Inicio: ' + (Get-Date -Format 'yyyy-MM-dd HH:mm:ss')) | Out-File -LiteralPath $arquivoLog -Encoding utf8
    $env:PYTHONUNBUFFERED = '1'
    $env:PYTHONIOENCODING = 'utf-8'
    [Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
    # PowerShell 5 trata stderr de comandos nativos como ErrorRecord.
    # FFmpeg escreve progresso em stderr mesmo em execucoes bem-sucedidas.
    $ErrorActionPreference = 'Continue'
    & $PythonExecutavel -u (Join-Path $pastaProjeto 'gerar_video.py') 2>&1 |
        Out-File -LiteralPath $arquivoLog -Append -Encoding utf8
    $codigo = $LASTEXITCODE
    $ErrorActionPreference = 'Stop'
    if ($null -eq $codigo) { $codigo = 1 }
} catch {
    ($_ | Out-String) | Out-File -LiteralPath $arquivoLog -Append -Encoding utf8
    $codigo = 1
}
('Fim: ' + (Get-Date -Format 'yyyy-MM-dd HH:mm:ss') + '; codigo de saida: ' + $codigo) |
    Out-File -LiteralPath $arquivoLog -Append -Encoding utf8
exit $codigo
