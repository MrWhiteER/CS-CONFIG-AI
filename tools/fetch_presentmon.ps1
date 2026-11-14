# Run explicitly before a source probe or release build. No app startup download.
$ErrorActionPreference = 'Stop'
$taskFolder = Join-Path $PSScriptRoot 'presentmon'
$taskName = 'PresentMon-2.6.0-x64.exe'
$taskExpectedHash = 'b2a706bc6ad475749e3b7e3409263aa1e6906d45bdcf993f6dbc0f660188f1af'
$taskTarget = Join-Path $taskFolder $taskName
$taskDownload = Join-Path $taskFolder ($taskName + '.download')
New-Item -ItemType Directory -Force -Path $taskFolder | Out-Null
Invoke-WebRequest -Uri ('https://github.com/GameTechDev/PresentMon/releases/download/v2.6.0/' + $taskName) -OutFile $taskDownload
if ((Get-FileHash -Algorithm SHA256 -LiteralPath $taskDownload).Hash.ToLowerInvariant() -ne $taskExpectedHash) {
    throw 'PresentMon SHA256 mismatch. Download was not installed.'
}
Move-Item -LiteralPath $taskDownload -Destination $taskTarget -Force
Write-Output ('Verified PresentMon: ' + $taskTarget)
