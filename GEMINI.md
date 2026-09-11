# GEMINI.md

## Project Overview

VelaGuard Host — Windows PyQt5 upper computer for openvela VelaGuard
(`contest2026_004_TeamFalcons`).

**Shell is the original Designer chrome** (`window.py` + PNG in `res.qrc`):
sidebar, header, bottom NSH log. Middle pages, point cards and the add-point
dialog are rebuilt in `widgets/` with a VelaGuard industrial QSS theme
(`theme/`). Transport is **vgpoint NSH text** over ST-LINK VCP
(COM3 @ 115200). Authoritative protocol:
`contest2026_004_TeamFalcons/docs/velaguard-host-nsh-protocol.md`.

## Building and Running

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe main.py
.\.venv\Scripts\python.exe -m pytest tests -v
```

## Conventions

- Keep the Designer shell and PNG resources; middle pages may be Python widgets.
- `protocol.py` must track the board protocol doc; update tests when it changes.
- `vgpoint apply --confirm` is a separate human-confirmed action after `test`.
- Point identity is `id` (`[A-Za-z0-9_]{1,23}`); `name` is display-only (UTF-8, ≤47 bytes).
- Commands use `vgpoint add -i` / `-N`; do not send `-t`. Command ≤ 120 UTF-8 bytes.
