# Install MetaTrader 5 silently on a fresh Windows machine, for the hosted bot (.github/workflows/host.yml).
# The Exness build lists Exness's servers; the MetaQuotes build is the fallback. Writes terminal=<path of
# terminal64.exe> to $GITHUB_OUTPUT.
$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"          # the progress bar makes Invoke-WebRequest very slow

$builds = @(
    "https://download.mql5.com/cdn/web/exness.technologies.ltd/mt5/exness5setup.exe",
    "https://download.mql5.com/cdn/web/metaquotes.software.corp/mt5/mt5setup.exe"
)

function Find-Terminal {
    Get-ChildItem "C:\Program Files" -Filter terminal64.exe -Recurse -Depth 2 -ErrorAction SilentlyContinue |
        Select-Object -First 1
}

$exe = $null
foreach ($url in $builds) {
    $setup = Join-Path $env:RUNNER_TEMP (Split-Path $url -Leaf)
    try {
        Invoke-WebRequest $url -OutFile $setup
        $p = Start-Process -FilePath $setup -ArgumentList "/auto" -PassThru
        if (-not $p.WaitForExit(600000)) { Write-Warning "$setup still running after 10 minutes" }
        $deadline = (Get-Date).AddMinutes(5)       # the installer may hand over to the terminal before it is done
        while (-not ($exe = Find-Terminal) -and (Get-Date) -lt $deadline) { Start-Sleep -Seconds 5 }
    } catch {
        Write-Warning "installing from $url failed: $_"
    }
    if ($exe) { break }
}
if (-not $exe) { throw "MetaTrader 5 did not install" }

Start-Sleep -Seconds 10
# The installer starts the terminal with no account; the bot starts it again and logs in.
Get-Process terminal64 -ErrorAction SilentlyContinue | Stop-Process -Force
Get-Process metaeditor64 -ErrorAction SilentlyContinue | Stop-Process -Force

Add-Content -Path $env:GITHUB_OUTPUT -Value "terminal=$($exe.FullName)"
Write-Host "MetaTrader 5 installed: $($exe.FullName)"
