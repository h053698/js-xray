---
name: js-xray
description: Reverse-engineer obfuscated or minified JavaScript. Deobfuscates with WebCrack (inlines encoded string arrays), extracts the key logic blocks (hashing, fetch payloads, token assembly, fingerprinting), and writes a Markdown report with readable code and a Python porting guide. Use when given a .js file to understand, or when porting client-side logic to Python.
---

# js-xray

Static X-ray of a JavaScript file. Four stages: **deobfuscate -> inline -> analyze -> report**. Nothing is executed except inside WebCrack's sandboxed isolate.

## Quick start

```bash
python3 scripts/xray.py <input.js>
```

Writes `xray_<name>/` next to the input:

| file | contents |
| --- | --- |
| `report.md` | the deliverable: summary, endpoints, key code, porting guide |
| `clean.js` | final readable source - read this one |
| `analysis.json` | machine-readable anchors and extracted blocks |
| `webcrack.js` | intermediate output after WebCrack, before the second pass |
| `webcrack.json` | what WebCrack detected (string array, rotation, decoders) |
| `inline.json` | second-pass results: scoped arrays, decoders, replacement count |
| `webcrack.log` | raw transform log |

Read `report.md` first, then open `clean.js` at the line numbers it cites.

Useful flags:

- `-o DIR` choose the output directory
- `--anchors FILE` search for target-specific patterns (see below)
- `--skip-deobfuscate` analyze the file as-is
- `--skip-inline` skip the second-pass string inlining
- `--mangle` let WebCrack rename variables (sometimes more readable)
- `--max-blocks N` how many functions to include (default 12)

## Requirements

WebCrack needs Node in the range `>=22 <23` or `>=24 <25` because its `isolated-vm` dependency ships per-ABI native binaries. **Newer Node (25, 26+) will not work.**

```bash
fnm install 24          # or: volta install node@24
bun install             # installs webcrack@2.16.0 (pinned)
```

`scripts/node_env.py` finds a compatible Node automatically by scanning fnm, volta and nvm directories, so no shell activation is needed. Override with `JSXRAY_NODE=/path/to/node`.

Verify the toolchain:

```bash
python3 scripts/node_env.py --json
python3 tests/test_xray.py
```

If no compatible Node is found the pipeline still runs: it analyzes the raw source and marks the failure in the report, so results are degraded but never silently wrong.

## Two inlining passes

WebCrack resolves the one string array it identifies as *the* array for the file. Many real SDKs declare a **separate array per IIFE scope**, so after WebCrack finishes, calls like `O(40)` or `i(47)` are still there and identifiers still read as `(anonymous)`.

The second pass handles those. The shape it recognizes:

```javascript
function U() { const t = ["_getAnswer", "width", ...]; return (U = function () { return t; })(); }
function O(t, n) { const e = U(); return (O = function (t, n) { return e[t -= 0]; })(t, n); }
const C = O;   // alias
```

This runs on Babel's AST rather than by text substitution, because short alias names (`t`, `e`, `i`, `C`) are reused across scopes for **different** arrays. Resolving those by regex silently produces wrong strings - the kind of bug that looks like a successful deobfuscation. Real scope bindings resolve each call against the array actually in scope.

Two safety properties:

- Decoders that do more than an index lookup (base64, RC4, char math) are left alone rather than mis-resolved.
- The rewritten file must re-parse, and is checked again with `node --check`. If either gate fails the pass rolls back to the WebCrack output and says so in the report. A degraded result, never a corrupted one.

`inline.json` records what happened; the report summarizes it in one line.

## What the analysis looks for

Anchors are grouped into behaviour categories, and each match is traced back to its **enclosing function** by brace matching (strings, comments and template interpolations are skipped). Functions are ranked by how many distinct anchors they contain, which reliably surfaces the interesting code first.

| category | detects |
| --- | --- |
| hashing/crypto | FNV / MD5 / SHA / CRC constants, XOR mixing, `>>> 0` uint32 coercion, base64, WebCrypto |
| network | `fetch`, XHR, WebSocket, URLs, API paths, auth headers |
| fingerprinting | navigator/screen probes, canvas, WebGL, timing |
| storage/identity | cookies, localStorage, versioned token prefixes |
| anti-analysis | `eval`, `new Function`, `debugger` traps |
| serialization | `JSON.stringify` / `JSON.parse` |

The report only includes porting notes for anchors actually present, so it stays specific to the file.

## Custom anchors

The defaults are generic. To chase target-specific identifiers, pass a JSON list:

```json
[
  {"label": "enforcement_token", "pattern": "getEnforcementToken", "regex": false},
  {"label": "pow_flow", "pattern": "proofofwork|difficulty", "regex": true}
]
```

```bash
python3 scripts/xray.py sdk.js --anchors my_anchors.json
```

A custom list **replaces** the defaults rather than adding to them, so re-include any built-ins you still want. Set `"regex": true` to use Python `re` syntax, or `false` for a literal match.

## Interpreting results

For a walkthrough of common obfuscation shapes, what each signal implies, and how to validate a Python port, read [references/analysis-guide.md](references/analysis-guide.md).

## Limitations

- **String array not detected** (`"string array": "no"` in `webcrack.json`): the file may be plain-minified, use a custom scheme, or be a webpack bundle. The analysis still runs; identifiers just stay short.
- Variable names cannot be recovered - obfuscation discards them. Expect short names like `t` or `Ht` even after a successful run; the *strings, constants, method names and control flow* are what become readable. Method names often do come back, because they were stored in the string array.
- Anonymous helpers are reported as `outerName > (anonymous)`. Hot logic frequently lives in an unnamed closure inside a named method, so the qualifier is the useful part.
- Purely dynamic behaviour (runtime-computed property access, network-fetched code) is invisible to static analysis.
- Very large bundles: extract the relevant module first, or raise `--max-blocks`.
