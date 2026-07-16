param(
    [Parameter(Mandatory = $true)]
    [string]$PythonExe,
    [Parameter(Mandatory = $true)]
    [string]$ProjectRoot
)

$ErrorActionPreference = 'Stop'
try {
    $resolvedPython = (Resolve-Path -LiteralPath $PythonExe).Path
    $resolvedRoot = (Resolve-Path -LiteralPath $ProjectRoot).Path
    $logDir = Join-Path $resolvedRoot 'runtime\logs'
    New-Item -ItemType Directory -Path $logDir -Force | Out-Null
    $stamp = Get-Date -Format 'yyyyMMdd-HHmmss-fffffff'
    $stdoutPath = Join-Path $logDir "worker-$stamp.stdout.log"
    $stderrPath = Join-Path $logDir "worker-$stamp.stderr.log"
    $process = Start-Process -FilePath $resolvedPython `
        -ArgumentList @('-m', 'app.main', 'worker', '--once', '--offline-only') `
        -WorkingDirectory $resolvedRoot -WindowStyle Hidden -Wait -PassThru `
        -RedirectStandardOutput $stdoutPath -RedirectStandardError $stderrPath
    if ($null -eq $process.ExitCode) { exit 70 }
    exit [int]$process.ExitCode
}
catch {
    try {
        $fallbackRoot = (Resolve-Path -LiteralPath $ProjectRoot).Path
        $fallbackDir = Join-Path $fallbackRoot 'runtime\logs'
        New-Item -ItemType Directory -Path $fallbackDir -Force | Out-Null
        $safeMessage = ($_.Exception.Message -replace '[\r\n]+', ' ')
        Add-Content -LiteralPath (Join-Path $fallbackDir 'worker-launcher-errors.log') `
            -Value "$(Get-Date -Format o) launcher_error=$safeMessage"
    }
    catch { }
    exit 70
}
