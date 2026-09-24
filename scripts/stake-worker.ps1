param([ValidateSet('Start', 'Serve', 'Run', 'Stop', 'Status')][string]$Action = 'Start')
$ErrorActionPreference = 'Stop'
$projectRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
Set-Location -LiteralPath $projectRoot
$stateDir = Join-Path $projectRoot '.cache/stake-worker'
New-Item -ItemType Directory -Force -Path $stateDir | Out-Null
$processFile = Join-Path $stateDir 'process.json'
$stopFile = Join-Path $stateDir 'stop-requested'
$heartbeatFile = Join-Path $projectRoot '.cache/backend/worker.heartbeat'
$activeProcess = $null
if (Test-Path -LiteralPath $processFile) {
    $saved = Get-Content -LiteralPath $processFile -Raw | ConvertFrom-Json
    $candidate = Get-Process -Id $saved.pid -ErrorAction SilentlyContinue
    if ($candidate -and $candidate.StartTime.ToUniversalTime() -eq ([datetime]$saved.startedAt).ToUniversalTime()) {
        $activeProcess = $candidate
    }
}
if ($Action -eq 'Status') {
    $heartbeat = Get-Item -LiteralPath $heartbeatFile -ErrorAction SilentlyContinue
    $ready = [bool]$activeProcess -and $heartbeat -and ((Get-Date).ToUniversalTime() - $heartbeat.LastWriteTimeUtc).TotalSeconds -lt 90
    [pscustomobject]@{ Running = [bool]$activeProcess; Ready = [bool]$ready; Pid = $activeProcess.Id; Logs = $stateDir } | Format-List | Out-String | Write-Output
    exit
}
if ($Action -eq 'Stop') {
    if ($activeProcess) {
        New-Item -ItemType File -Path $stopFile -Force | Out-Null
        if (-not $activeProcess.WaitForExit(75000)) {
            throw "Arrêt Stake encore en cours (PID $($activeProcess.Id)). Réessayez après la collecte active."
        }
        Write-Output 'Worker Stake arrêté ; les données déjà validées restent conservées.'
    } else { Write-Output 'Le worker Stake est arrêté.' }
    exit
}
if ($Action -eq 'Start') {
    if ($activeProcess) {
        $heartbeat = Get-Item -LiteralPath $heartbeatFile -ErrorAction SilentlyContinue
        if (-not $heartbeat -or ((Get-Date).ToUniversalTime() - $heartbeat.LastWriteTimeUtc).TotalSeconds -ge 90) {
            throw "Le processus Stake tourne sans heartbeat récent (PID $($activeProcess.Id)). Journaux : $stateDir"
        }
        Write-Output "Worker Stake déjà prêt (PID $($activeProcess.Id))."
        exit
    }
    if (Test-Path -LiteralPath $stopFile) { Remove-Item -LiteralPath $stopFile }
    $stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
    $started = Start-Process -FilePath 'powershell.exe' -WindowStyle Hidden -PassThru -WorkingDirectory $projectRoot `
        -ArgumentList @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', ('"{0}"' -f $PSCommandPath), '-Action', 'Serve') `
        -RedirectStandardOutput (Join-Path $stateDir "$stamp.out.log") `
        -RedirectStandardError (Join-Path $stateDir "$stamp.err.log")
    @{ pid = $started.Id; startedAt = $started.StartTime.ToUniversalTime().ToString('o') } |
        ConvertTo-Json | Set-Content -LiteralPath $processFile -Encoding utf8
    $deadline = (Get-Date).AddSeconds(60)
    do {
        if (-not (Get-Process -Id $started.Id -ErrorAction SilentlyContinue)) {
            throw "Le worker Stake s'est arrêté avant son premier heartbeat. Journaux : $stateDir"
        }
        $heartbeat = Get-Item -LiteralPath $heartbeatFile -ErrorAction SilentlyContinue
        if ($heartbeat -and $heartbeat.LastWriteTimeUtc -ge $started.StartTime.ToUniversalTime()) {
            Write-Output "Worker Stake prêt (PID $($started.Id)). Journaux : $stateDir"
            exit
        }
        Start-Sleep -Milliseconds 500
    } while ((Get-Date) -lt $deadline)
    throw "Le worker Stake n'a pas annoncé de heartbeat dans les 60 secondes. Journaux : $stateDir"
}
if ($Action -eq 'Run' -and $activeProcess) { throw 'Arrêtez le worker Stake avant un passage CLI isolé.' }
if ($Action -eq 'Run' -and (Test-Path -LiteralPath $stopFile)) { Remove-Item -LiteralPath $stopFile }
$environmentFile = Join-Path $projectRoot '.env.docker'
if (-not (Test-Path -LiteralPath $environmentFile)) { throw 'Créez .env.docker avec npm run docker:init.' }
$values = @{}
foreach ($line in Get-Content -LiteralPath $environmentFile) {
    if ($line -match '^([A-Z0-9_]+)=(.*)$') { $values[$Matches[1]] = $Matches[2] }
}
if (-not $values['METIQUO_WORKER_PASSWORD']) { throw 'Mot de passe SQL worker absent de .env.docker.' }
$port = if ($values['DB_DEV_PORT']) { $values['DB_DEV_PORT'] } else { '54329' }
$env:METIQUO_DATABASE_URL = 'postgresql+psycopg://metiquo_worker:' +
    [Uri]::EscapeDataString($values['METIQUO_WORKER_PASSWORD']) + "@127.0.0.1:$port/metiquo"
$env:METIQUO_STAKE_ENABLED = 'true'
$env:METIQUO_WORKER_STATUS_ID = '2'
$env:METIQUO_WORKER_STOP_FILE = $stopFile
$env:METIQUO_STAKE_PROFILE_DIR = Join-Path $projectRoot '.cache/stake-audit/chrome-profile'
$env:PYTHONUTF8 = '1'
foreach ($key in $values.Keys) {
    if ($key -like 'METIQUO_STAKE_*' -and $key -ne 'METIQUO_STAKE_ENABLED') {
        [Environment]::SetEnvironmentVariable($key, $values[$key], 'Process')
    }
}
if ($Action -eq 'Run') { uv run --frozen metiquo-worker sync-stake-markets }
else { uv run --frozen metiquo-worker serve --only stake }
exit $LASTEXITCODE
