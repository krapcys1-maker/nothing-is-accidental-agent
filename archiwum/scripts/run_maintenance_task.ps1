param(
    [Parameter(Mandatory = $true)]
    [string]$PythonExe,
    [Parameter(Mandatory = $true)]
    [string]$ProjectRoot,
    [ValidateRange(1, 86400)]
    [int]$StaleAfterSeconds = 300
)

$ErrorActionPreference = 'Stop'
try {
    $resolvedPython = (Resolve-Path -LiteralPath $PythonExe).Path
    $resolvedRoot = (Resolve-Path -LiteralPath $ProjectRoot).Path
    $logDir = Join-Path $resolvedRoot 'runtime\logs'
    New-Item -ItemType Directory -Path $logDir -Force | Out-Null
    $stamp = Get-Date -Format 'yyyyMMdd-HHmmss-fffffff'
    $stdoutPath = Join-Path $logDir "maintenance-$stamp.stdout.log"
    $stderrPath = Join-Path $logDir "maintenance-$stamp.stderr.log"
    $process = Start-Process -FilePath $resolvedPython `
        -ArgumentList @(
            '-m', 'app.main', 'maintain', '--once', '--stale-after-seconds',
            [string]$StaleAfterSeconds
        ) `
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
        Add-Content -LiteralPath (Join-Path $fallbackDir 'maintenance-launcher-errors.log') `
            -Value "$(Get-Date -Format o) launcher_error=$safeMessage"
    }
    catch { }
    exit 70
}
