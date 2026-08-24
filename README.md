# js-xray

Toolkit behind the [js-xray](skill/SKILL.md) Codex skill: static reverse
engineering of obfuscated JavaScript.

Deobfuscates a `.js` file with WebCrack, resolves any remaining per-scope string
arrays on Babel's AST, then extracts structure and turns it into `xray.json` - a
structured explanation an agent can read to describe the module's flows and
functions, or to reimplement its logic in another language. `report.md` carries
the same findings for a human.

## Setup

WebCrack's `isolated-vm` dependency ships native binaries per Node ABI, so Node
must be in the range `>=22 <23` or `>=24 <25`. Node 25/26+ will not work.

```bash
fnm install 24
bun install
```

No shell activation is needed - `skill/scripts/node_env.py` locates a compatible
Node under fnm, volta or nvm at runtime.

## Usage

```bash
python3 skill/scripts/xray.py path/to/input.js
```

Prints the path to `xray.json`. Results land in `xray_<name>/`: `xray.json`,
`report.md`, `clean.js`, `structure.json`, `analysis.json`, `webcrack.js`,
`webcrack.json`, `inline.json`, `webcrack.log`.

Six stages, each writing its own artifact so a degraded stage stays visible:

1. **deobfuscate** - WebCrack (`webcrack.js`)
2. **inline** - second AST pass for string arrays declared per IIFE scope, which
   WebCrack does not handle; verifies its output parses and rolls back if not
   (`clean.js`, `inline.json`)
3. **structure** - AST facts only, no interpretation (`structure.json`)
4. **explain** - entry points, flows, roles with evidence, porting spec
   (`xray.json`)
5. **anchors** - keyword grep, optional (`analysis.json`)
6. **report** - the same findings as prose (`report.md`)

## Tests

```bash
python3 tests/test_xray.py
```

57 checks, no pytest required. Brace matching against strings, comments and
template interpolations; function-vs-keyword detection; cross-scope string-array
resolution; the syntax-validity gate; an end-to-end run over
`fixtures/sample_obfuscated.js` (javascript-obfuscator output: base64-encoded,
rotated string array).

Two of them close the loop rather than checking a field. `test_multiply_style`
runs the Python snippet the porting guide emits against the original JS and
compares digests, for both `Math.imul` and `h * k >>> 0` sources - the two are not
interchangeable, and the guide used to hand out one snippet for both.
`test_reachability_ignores_flow_budget` pins that a function reachable only
through anonymous closures is not reported as dead code.

## Layout

| path | purpose |
| --- | --- |
| `skill/SKILL.md` | skill instructions, `xray.json` schema |
| `skill/scripts/xray.py` | orchestrator |
| `skill/scripts/run_webcrack.py` | WebCrack wrapper, degrades gracefully |
| `skill/scripts/inline_strings.py` | second-pass wrapper + `node --check` gate |
| `skill/scripts/inline_strings.mjs` | Babel transform for per-scope string arrays |
| `skill/scripts/structure.mjs` | AST fact extraction |
| `skill/scripts/structure.py` | Node resolution + graceful degrade |
| `skill/scripts/explain.py` | flows, roles, porting spec |
| `skill/scripts/analyze.py` | anchors, brace matching, block ranking |
| `skill/scripts/report.py` | Markdown report from `xray.json` |
| `skill/scripts/node_env.py` | compatible-Node resolution |
| `skill/references/` | interpretation guide |
| `fixtures/` | obfuscated test inputs, incl. a cross-scope alias case |
| `tests/samples/` | real-world sample used for manual verification |
