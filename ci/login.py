"""Log the freshly installed MetaTrader 5 terminal in to the account in MT5_LOGIN / MT5_PASSWORD / MT5_SERVER, for
the hosted bot (.github/workflows/host.yml). The bot then attaches to the logged-in terminal.

A terminal on its first start is busy (it updates and recompiles its MQL5 folder), and may not know a numbered
server such as Exness-MT5Trial11 yet. So: try the Python API's login a few times; failing that, start the terminal
with a startup file that logs in (MT5's own command-line login, which also switches Algo Trading on).

  python ci/login.py "C:/Program Files/MetaTrader 5 EXNESS/terminal64.exe"
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import MetaTrader5 as mt5


def logged_in(login: int) -> bool:
    acct = mt5.account_info()
    return acct is not None and acct.login == login


def known_servers(server: str) -> str:
    """Whether the terminal's server list mentions the server (servers.dat stores names as UTF-16)."""
    root = Path(os.environ.get("APPDATA", "")) / "MetaQuotes" / "Terminal"
    found = []
    for f in root.glob("*/config/servers.dat"):
        data = f.read_bytes()
        found.append(f"{f}: {'lists' if server.encode('utf-16-le') in data or server.encode() in data else 'does not list'}"
                     f" {server}")
    return "; ".join(found) or "no servers.dat yet"


def startup_file(login: int, password: str, server: str) -> Path:
    text = (f"[Common]\nLogin={login}\nPassword={password}\nServer={server}\nKeepPrivate=1\nNewsEnable=0\n"
            "[Experts]\nAllowLiveTrading=1\nAllowDllImport=0\nEnabled=1\nAccount=0\nProfile=0\n")
    path = Path(tempfile.gettempdir()) / "mt5_start.ini"
    path.write_text(text, encoding="utf-16")
    return path


def main() -> int:
    path = sys.argv[1]
    login, password, server = int(os.environ["MT5_LOGIN"]), os.environ["MT5_PASSWORD"], os.environ["MT5_SERVER"]
    ok = False
    for attempt in range(1, 5):
        if mt5.initialize(path, login=login, password=password, server=server, timeout=120_000) and logged_in(login):
            ok = True
            break
        print(f"login through the Python API, attempt {attempt}: {mt5.last_error()}", flush=True)
        mt5.shutdown()
        time.sleep(15)
    if not ok:
        print(f"server list: {known_servers(server)}", flush=True)
        print("starting the terminal with a startup login file instead", flush=True)
        subprocess.run(["taskkill", "/F", "/IM", "terminal64.exe"], capture_output=True)
        time.sleep(3)
        ini = startup_file(login, password, server)
        subprocess.Popen([path, f"/config:{ini}"])
        try:
            deadline = time.monotonic() + 180
            while time.monotonic() < deadline:
                time.sleep(10)
                if mt5.initialize(path, timeout=60_000) and logged_in(login):
                    ok = True
                    break
                print(f"  waiting for the startup login: {mt5.last_error()}", flush=True)
                mt5.shutdown()
        finally:
            time.sleep(5)
            ini.unlink(missing_ok=True)       # it holds the password
    if not ok:
        print(f"server list: {known_servers(server)}", flush=True)
        print("could not log in: check MT5_LOGIN, MT5_PASSWORD and MT5_SERVER (the MT5 journal below says more)")
        return 1
    acct, term = mt5.account_info(), mt5.terminal_info()
    kind = {mt5.ACCOUNT_TRADE_MODE_DEMO: "demo", mt5.ACCOUNT_TRADE_MODE_CONTEST: "contest"}.get(acct.trade_mode, "REAL")
    print(f"logged in: {kind} account on {acct.server}, {acct.balance:,.2f} {acct.currency}, leverage 1:{acct.leverage}, "
          f"expert trading {'allowed' if acct.trade_expert else 'NOT allowed'}; terminal build {mt5.version()[1]}, "
          f"Algo Trading {'on' if term.trade_allowed else 'OFF'}, Python API trading "
          f"{'disabled' if term.tradeapi_disabled else 'allowed'}", flush=True)
    mt5.shutdown()
    return 0


if __name__ == "__main__":
    sys.exit(main())
