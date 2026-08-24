# js-xray

Toolkit behind the [js-xray](skill/SKILL.md) Codex skill: static reverse engineering of obfuscated JavaScript.

Deobfuscates a `.js` file with WebCrack (inlining encoded string arrays), extracts the functions that carry the interesting behaviour, and writes a Markdown report with readable code plus a Python porting guide.

## Setup

WebCrack's `isolated-vm` dependency ships native binaries per Node ABI, so Node must be in the range `>=22 <23` or `>=24 <25`. Node 25/26+ will not work.

```bash
fnm install 24
bun install
```

No shell activation is needed - `skill/scripts/node_env.py` locates a compatible Node under fnm, volta or nvm at runtime.

## Usage

```bash
python3 skill/scripts/xray.py path/to/input.js
```

Results land in `xray_<name>/`: `report.md`, `clean.js`, `analysis.json`, `webcrack.json`, `webcrack.log`.

## Tests

```bash
python3 tests/test_xray.py
```

Covers brace matching against strings, comments and template interpolations, function-vs-keyword detection, and an end-to-end run over `fixtures/sample_obfuscated.js` (generated with javascript-obfuscator: base64-encoded, rotated string array).

## Layout

| path | purpose |
| --- | --- |
| `skill/SKILL.md` | skill instructions |
| `skill/scripts/xray.py` | orchestrator |
| `skill/scripts/run_webcrack.py` | WebCrack wrapper, degrades gracefully |
| `skill/scripts/analyze.py` | anchors, brace matching, block ranking |
| `skill/scripts/report.py` | Markdown report + porting hints |
| `skill/scripts/node_env.py` | compatible-Node resolution |
| `skill/references/` | interpretation guide |
| `fixtures/` | obfuscated test input |
