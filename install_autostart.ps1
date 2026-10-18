<#
Start the Gotobi bot automatically every time you log on to Windows.

  powershell -ExecutionPolicy Bypass -File install_autostart.ps1            create or update the task
  powershell -ExecutionPolicy Bypass -File install_autostart.ps1 -DryRun    show what it would create
  powershell -ExecutionPolicy Bypass -File install_autostart.ps1 -Remove    delete the task

It creates a Task Scheduler task "Gotobi bot" that runs run_bot.bat in a console window at log-on.
- It runs in your own desktop session, because the MetaTrader 5 terminal is a desktop program and the bot talks
  to it.
- There is NO time limit. Tasks made with the Task Scheduler wizard, schtasks or PowerShell defaults are
  stopped after 3 days, which would silently stop the bot.
- It runs on battery too, and starts 1 minute after log-on so the network and MT5 are up.
- After a reboot it only starts once Windows has logged you on (see BOT_README.md: automatic sign-in).
#>
param([switch]$Remove, [switch]$DryRun)
$ErrorActionPreference = "Stop"
$name = "Gotobi bot"
$dir = Split-Path -Parent $MyInvocation.MyCommand.Path
$bat = Join-Path $dir "run_bot.bat"

if ($Remove) {
    Unregister-ScheduledTask -TaskName $name -Confirm:$false
    Write-Host "Removed the '$name' task."
    exit 0
}
if (-not (Test-Path $bat)) { throw "run_bot.bat not found next to this script ($dir)" }

$user = "$env:USERDOMAIN\$env:USERNAME"
$action = New-ScheduledTaskAction -Execute "cmd.exe" -Argument "/c `"$bat`"" -WorkingDirectory $dir
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $user
$trigger.Delay = "PT1M"
$settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit ([TimeSpan]::Zero) -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries -StartWhenAvailable -MultipleInstances IgnoreNew -DontStopOnIdleEnd
$principal = New-ScheduledTaskPrincipal -UserId $user -LogonType Interactive -RunLevel Limited
$task = New-ScheduledTask -Action $action -Trigger $trigger -Settings $settings -Principal $principal `
    -Description "Gotobi USD/JPY bot (run_bot.bat restarts it if it stops). Close its window to stop it."

if ($DryRun) {
    Write-Host "Would register '$name' for $user"
    Write-Host "  runs:        cmd.exe /c `"$bat`"  (in $dir)"
    Write-Host "  trigger:     at log-on, after $($trigger.Delay)"
    Write-Host "  time limit:  $($settings.ExecutionTimeLimit)  (PT0S = none)"
    Write-Host "  on battery:  start $(-not $settings.DisallowStartIfOnBatteries), keep running $(-not $settings.StopIfGoingOnBatteries)"
    exit 0
}
Register-ScheduledTask -TaskName $name -InputObject $task -Force | Out-Null
$t = Get-ScheduledTask -TaskName $name
Write-Host "Registered '$name': starts run_bot.bat 1 minute after you log on (time limit: $($t.Settings.ExecutionTimeLimit))."
Write-Host "Start it now without logging off:  Start-ScheduledTask -TaskName '$name'"
