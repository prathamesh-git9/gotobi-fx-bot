@echo off
rem Start the Gotobi bot. MetaTrader 5 must be running and logged in (demo account unless unlocked).
rem Set PYTHON to the interpreter that has requirements-bot.txt installed.
set PYTHON=python
cd /d "%~dp0"
if not exist bot_config.toml copy bot_config.example.toml bot_config.toml >nul
:loop
%PYTHON% -m bot.main --config bot_config.toml %*
rem exit code 2 = refused (real account / bad config), 3 = startup failure: do not restart blindly on 2
if %ERRORLEVEL%==2 goto end
echo bot stopped (code %ERRORLEVEL%), restarting in 30 s... close this window to stop
timeout /t 30 /nobreak >nul
goto loop
:end
pause
