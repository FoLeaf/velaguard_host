# GEMINI.md

## Project Overview

VelaGuard Host — Windows PyQt5 upper computer for the openvela VelaGuard
gateway (`contest2026_004_TeamFalcons`).

**UI is the original Designer shell** (`window.py`, `config.py`,
`sourcecard_ui.py`) with PNG resources (`res.qrc`, `sourcecard_src.qrc`).
Host transport is **NSH text** over ST-LINK VCP (default COM3 @ 115200 8N1).
It does **not** speak RS485 as a master and does **not** use the retired
EB90 binary frame.

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

- `main.py` — wires original UI to NSH (`velaguard_host.*`)
- `window.py` / `res_rc.py` / `*.png` — main window + icons (do not rewrite as pure widgets)
- `config.py` — add-source dialog
- `sourcecard_ui.py` / `sourcecard_src_rc.py` — sensor cards
- `velaguard_host/nsh_session.py` — serial line session
- `velaguard_host/protocol.py` — NSH builders/parsers
- `velaguard_host/worker.py` — Qt worker thread
- `docs/PROTOCOL.md` — host↔device protocol spec

## Development Conventions

- **Never replace the Designer UI with a pure-widget rewrite**; edit logic in
  `main.py` and keep `.ui` / generated files / PNG resources.
- Board CLI output is the contract: firmware printf changes require updating
  `protocol.py` **and** `docs/PROTOCOL.md` §5 together.
- `vgdiscover apply --confirm` stays a separate manual console action.
- Protocol parsers must not import Qt.
