# GEMINI.md

## Project Overview

VelaGuard Host — Windows PyQt5 upper computer for openvela VelaGuard
(`contest2026_004_TeamFalcons`).

**UI is the original Designer shell** (`window.py`, `config.py`,
`sourcecard_ui.py`) with PNG resources. Transport is **vgpoint NSH text**
over ST-LINK VCP (COM3 @ 115200). Authoritative protocol:
`contest2026_004_TeamFalcons/docs/velaguard-host-nsh-protocol.md`.

## Building and Running

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe main.py
.\.venv\Scripts\python.exe -m pytest tests -v
```

## Conventions

- Never replace Designer UI with a pure-widget rewrite; keep PNG resources.
- `protocol.py` must track the board protocol doc; update tests when it changes.
- `vgpoint apply --confirm` is a separate human-confirmed action after `test`.
- Tag: `[A-Za-z0-9_]{1,23}`; command ≤ 120 bytes.
