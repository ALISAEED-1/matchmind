# Headless screenshot of the built web app (served on :8090), for docs and visual checks.
# Usage: powershell -File tool/screenshot.ps1 -Query "match=mm-0004-comeback&seek=59&audience=analyst" -Out shot.png
param(
  [string]$Query = "",
  [string]$Out = "screenshot.png",
  [int]$Width = 1440,
  [int]$Height = 900,
  [int]$WaitMs = 9000
)
$chrome = "$env:ProgramFiles\Google\Chrome\Application\chrome.exe"
$url = "http://localhost:8090/" + $(if ($Query) { "?$Query" } else { "" })
$outPath = [IO.Path]::GetFullPath($Out)
& $chrome --headless=new --disable-gpu --hide-scrollbars --window-size="$Width,$Height" `
  --virtual-time-budget=$WaitMs --screenshot="$outPath" $url 2>$null | Out-Null
Write-Output $outPath
