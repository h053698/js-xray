---
name: js-xray
description: Reverse-engineer obfuscated or minified JavaScript into a structured JSON explanation. Deobfuscates with WebCrack, inlines per-scope string arrays, then extracts entry points, call flows, per-function roles with evidence, network contracts and a porting spec into xray.json. Use when given a .js file to understand, explain to a person, or reimplement in another language.
---

# js-xray

Turns an obfuscated JavaScript file into facts you can act on. The deliverable is
`xray.json`: entry points, the flows control takes through them, what each
function does and why we think so, and everything a reimplementation has to get
right. `report.md` is the same content for a human reader.

Nothing from the input is executed except inside WebCrack's sandboxed isolate.

## Quick start

```bash
python3 scripts/xray.py <input.js>
```

Prints the path to `xray.json` and writes `xray_<name>/` next to the input:

| file | contents |
| --- | --- |
| `xray.json` | **the deliverable** - read this first, schema below |
| `report.md` | the same findings as prose, for a human |
| `clean.js` | readable source; open it at the line numbers cited |
| `structure.json` | raw AST facts, no interpretation |
| `analysis.json` | keyword anchor hits (skipped with `--skip-anchors`) |
| `webcrack.js` | intermediate, before the second inlining pass |
| `webcrack.json` | what WebCrack detected (string array, rotation, decoders) |
| `inline.json` | second-pass results: scoped arrays, decoders, replacements |

Six stages: **deobfuscate -> inline -> structure -> explain -> anchors -> report**.
Each writes its own file, so a stage that degrades is visible rather than silent.

Useful flags:

- `-o DIR` output directory
- `--top N` how many functions to detail in `xray.json` (default 25)
- `--skip-anchors` skip the keyword pass; faster, and `xray.json` is unaffected
- `--skip-deobfuscate` analyze the file as-is (already-readable source)
- `--skip-inline` skip the second-pass string inlining
- `--mangle` let WebCrack rename variables
- `--anchors FILE` custom keyword anchors (see below)

## Using xray.json

### To explain the module to someone

Read in this order:

1. `summary` - function and class counts, the `roles` histogram, and `endpoints`.
   One sentence comes straight out of this: what the module is made of and who it
   talks to.
2. `flows[]` - each is a narrative. `entry` is where control comes in, `steps[]`
   is the path in order with `depth` for nesting. Every step carries `does`
   (its roles), plus `network` and `algorithms` when present. Walk the steps and
   you have described the module's behaviour without opening the source.
3. `flows[].also_entered_by` - other public methods that converge on the same
   path. Mention them together instead of repeating the flow.
4. `functions[]` - detail for the highest-`importance` functions, when someone
   asks about a specific one.

`entry_points[]` lists more entries than there are flows; only the top ones are
traced (`traced: true`). `why` says what made it an entry point, and entries that
collapsed into another flow carry `shares_flow_with`.

### To reimplement or decrypt

Everything needed is under `porting`:

- `algorithms[]` - the recognised family, its constants, the line range, and
  `multiply_style` with a `multiply_note` explaining how to reproduce it.
- `network_contracts[]` - url, method, headers, body shape, credentials mode.
- `inputs[]` - the environment properties that feed the algorithm. A port has to
  supply these; they are inputs, not constants.
- `pitfalls[]` - the specific ways this file breaks a naive port.

Then verify: run the original in Node against your port on the same inputs and
compare outputs. Do not skip this. The failure mode of a bad 32-bit port is
agreement on short inputs and divergence on long ones.

### Two 32-bit multiplies, two different answers

JavaScript has two, and they do not produce the same result:

| source | `multiply_style` | correct Python |
| --- | --- | --- |
| `Math.imul(h, k)` | `imul` | `(h * k) & 0xFFFFFFFF` |
| `h * k >>> 0` | `truncated-float` | `int(float(to_int32(h)) * k) & 0xFFFFFFFF` |
| both in one function | `mixed` | read the source; no single rule works |

`h * k >>> 0` computes the product in float64 first. Since `^` leaves a signed
int32, `k * h` can exceed 2^53 and the low bits are gone before the truncation
happens - so the rounding is part of the algorithm, and the sign matters too.
`report.md` emits the matching snippet; for `mixed` it deliberately emits none,
because a confident wrong snippet costs more than an absent one.

## xray.json schema

```
schema           "js-xray/explanation/1"
source_file      path analyzed (clean.js, unless deobfuscation was skipped)
size             {lines, bytes}
summary          {functions, classes, entry_points, roles{name:count}, endpoints[]}
entry_points[]   {id, name, line, why, traced, shares_flow_with?}
flows[]          {entry, steps[], also_entered_by[]}
  steps[]        {depth, id, name, line, reached_by, does[], network?, algorithms?}
functions[]      {id, name, raw_name, kind, lines[2], params[], async,
                  roles[]{role, confidence, evidence[], inherited_from?},
                  calls[], reads[], network[], algorithms[], returns[],
                  reachable_from_entry, importance}
classes[]        {name, line, methods[], getters[], setters[], fields[], static[]}
module           {exports[], imports[], global_assignments[]}
literals         {urls[]{url, line}, paths[]}
porting          {algorithms[], network_contracts[], inputs[], pitfalls[]}
  algorithms[]   {function, id, lines[2], families[], constants[], operators[],
                  returns[], loops, multiply_style, multiply_note}
  network_...[]  {kind, url, method, headers[], body, credentials, function, line}
  inputs[]       {property, read_by[]}
  pitfalls[]     {issue, detail}
deobfuscation    {strings_inlined, unresolved, arrays, decoders, rolled_back}
confidence_notes[]  caveats that apply to the whole file
```

`name` is a display label (`_.getConfig`, or `_.getConfig > <callback@L318c173>`
for an anonymous child); `raw_name` is the identifier as it appears, or null.
## Trusting the output

`structure.json` holds only AST facts. Every interpretation in `xray.json` is
`explain.py`'s, and carries its evidence:

```json
{"role": "network transport", "confidence": "high",
 "evidence": ["performs fetch", "target Zt + \"req\""]}
```

| confidence | how to treat it |
| --- | --- |
| `high` | state it as a finding |
| `medium` | state it, and cite the evidence with it |
| `low` / `none` | a lead to check against `clean.js`, not a finding |

`inherited_from` means the role came from an inline closure inside the function,
which is where obfuscated code usually keeps the real work.

Two limits worth repeating to whoever reads your explanation:

- Call edges resolve **by name**, so a shadowed or reassigned identifier can
  point at the wrong function. Check a flow against the source before relying on
  it. `structure.json` marks this under `call_graph.resolution`.
- `reachable_from_entry: false` means no call path was found, including through
  the bundle wrapper. It is evidence of dead code, not proof.

`confidence_notes[]` carries these caveats in the file itself.

## Requirements

WebCrack needs Node `>=22 <23` or `>=24 <25`; its `isolated-vm` dependency ships
per-ABI native binaries, so **Node 25/26+ will not build it**.

```bash
fnm install 24          # or: volta install node@24
bun install             # webcrack@2.16.0, pinned
```

`scripts/node_env.py` finds a compatible Node by scanning fnm, volta and nvm, so
no shell activation is needed. Override with `JSXRAY_NODE=/path/to/node`.

```bash
python3 scripts/node_env.py --json
python3 tests/test_xray.py      # no pytest needed
```

Without a compatible Node the pipeline still runs: it analyzes the raw source,
`structure` and `explain` degrade to empty, and the report says so. Degraded,
never silently wrong.

## Two inlining passes

WebCrack resolves the one string array it identifies as *the* array for the file.
Many real SDKs declare a **separate array per IIFE scope**, so calls like `O(40)`
survive it and identifiers still read as `(anonymous)`.

The second pass handles those. The shape it recognizes:

```javascript
function U() { const t = ["_getAnswer", "width"]; return (U = function () { return t; })(); }
function O(t, n) { const e = U(); return (O = function (t, n) { return e[t -= 0]; })(t, n); }
const C = O;   // alias
```

It runs on Babel's AST, not by text substitution, because short alias names
(`t`, `e`, `C`) are reused across scopes for **different** arrays. Resolving
those by regex silently yields wrong strings - a bug that looks like a successful
deobfuscation. Scope bindings resolve each call against the array actually in
scope.

Two safety properties:

- Decoders doing more than an index lookup (base64, RC4, char math) are left
  alone rather than mis-resolved.
- The result must re-parse and pass `node --check`. If either gate fails the pass
  rolls back to the WebCrack output and says so. `xray.json` records this under
  `deobfuscation.rolled_back`.

## Custom anchors

The anchor pass is a keyword grep, independent of `xray.json`. Useful for chasing
a specific identifier:

```json
[
  {"label": "enforcement_token", "pattern": "getEnforcementToken", "regex": false},
  {"label": "pow_flow", "pattern": "proofofwork|difficulty", "regex": true}
]
```

```bash
python3 scripts/xray.py sdk.js --anchors my_anchors.json
```

A custom list **replaces** the defaults, so re-include any built-ins you want.

## Extending detection

| to recognise | edit | in |
| --- | --- | --- |
| another algorithm constant | `ALGO_CONSTANTS` | `scripts/structure.mjs` |
| another global object | `TRACKED_ROOTS` | `scripts/structure.mjs` |
| another capability from calls | `CALL_MARKERS` | `scripts/explain.py` |
| another role | the `add()` calls in `classify()` | `scripts/explain.py` |
| another porting snippet | `PORT_SNIPPETS` | `scripts/report.py` |

`PORT_SNIPPETS` is keyed by `(family, multiply_style)`. Use `None` for the style
when the algorithm has no 32-bit multiply, as with `SHA-256`.

For a walkthrough of common obfuscation shapes and how to validate a port, see
[references/analysis-guide.md](references/analysis-guide.md).

## Limitations

- **Variable names are gone.** Obfuscation discards them; expect `t` or `Ht`
  even after a clean run. Strings, constants, method names and control flow are
  what come back. Method names often do, having lived in the string array.
- **String array not detected** (`"string array": "no"` in `webcrack.json`): the
  file may be plain-minified, use a custom scheme, or be a webpack bundle. The
  analysis still runs.
- **Anonymous functions** appear as `nearestNamedAncestor > <kind@Lstart-Lend>`.
  The line span identifies them exactly.
- **Dynamic behaviour is invisible**: runtime-computed property access, `eval`,
  network-fetched code. An `anti-analysis` role is a hint that static reading
  will be incomplete.
- **Very large bundles**: extract the relevant module first, or raise `--top`.
