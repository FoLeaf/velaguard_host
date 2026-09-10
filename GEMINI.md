# GEMINI.md

## Project Overview

VelaGuard Host — Windows PyQt5 upper computer for the openvela VelaGuard
gateway (`contest2026_004_TeamFalcons`). Talks **NSH text** over ST-LINK VCP
(default COM3 @ 115200 8N1). Does **not** speak RS485/Modbus as a master and
does **not** use the retired EB90 binary frame.

**Key Technologies:** Python 3, PyQt5, pyserial

## Building and Running

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe main.py
```

```powershell
.\.venv\Scripts\python.exe -m pytest tests -v
```

## Architecture

- `main.py` — entry
- `velaguard_host/nsh_session.py` — serial line session / prompt wait
- `velaguard_host/protocol.py` — NSH command builders + response parsers
- `velaguard_host/worker.py` — Qt worker thread + controller
- `velaguard_host/app_window.py` — main window (connection / discover / points / monitor / console)
- `docs/PROTOCOL.md` — host↔device protocol spec
- `docs/compose/spec/velaguard-host.md` — feature design + report

Legacy Designer-generated UI (`window.py`, `config.py`, `sourcecard_ui.py`)
and `main1.py` remain as historical baseline only; the live entrypoint does
not import them.

## Development Conventions

- Board CLI output is the contract: if firmware printf text changes, update
  `protocol.py` **and** `docs/PROTOCOL.md` §5 in the same change.
- `vgdiscover apply --confirm` must stay a separate, user-confirmed action.
- Protocol parsers must not import Qt.
