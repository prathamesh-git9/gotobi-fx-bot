# Run the bot until a UTC time, restarting it 30 s after a failure the way run_bot.bat does, for the hosted bot
# (.github/workflows/host.yml). The bot stops by itself at the time (--until) once no trade action is due.
param([Parameter(Mandatory = $true)][string]$Until)
$ErrorActionPreference = "Continue"
$PSNativeCommandUseErrorActionPreference = $false   # a non-zero exit must reach the restart logic, not throw

$end = [DateTimeOffset]::Parse($Until, [Globalization.CultureInfo]::InvariantCulture).UtcDateTime
while ($true) {
    python -m bot.main --config bot_config.toml --until $Until
    $rc = $LASTEXITCODE
    # 0 = stopped at --until; 2 = refused (a real account without both keys, bad settings): never restart those
    if ($rc -eq 0 -or $rc -eq 2) { exit $rc }
    if ([DateTime]::UtcNow -ge $end) { exit $rc }
    Write-Host "bot stopped (code $rc); restarting in 30 s"
    Start-Sleep -Seconds 30
}
