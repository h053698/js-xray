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

To get the `xq` query command on your PATH:

```bash
sh scripts/install-xq.sh          # or: npm run install-xq
```

It symlinks `skill/scripts/xq.py` into `~/.local/bin` (falling back to `~/bin`,
then any writable non-system directory already on your PATH), warns if that
directory is not on the PATH, and refuses to overwrite an `xq` it did not create.
`--dry-run` prints the plan without touching anything, and re-running is a no-op.
Because it is a symlink, a `git pull` updates the installed command too. Optional:
everything below works as `python3 skill/scripts/xq.py ...` without it.

Token counts in the TOON-savings report use tiktoken (o200k_base) when it is
installed. It is optional: `pip install tiktoken` if you want token counts
instead of the character-count fallback; the pipeline runs fine without it.

## Usage

```bash
python3 skill/scripts/xray.py path/to/input.js
```

Prints the path to `xray.json`. Results land in `<name>.xrayjs/`: `xray.json`,
`xray.toon`, `toon_stats.json`, `report.md`, `clean.js`, `structure.json`,
`analysis.json`, `pipeline.json`, `webcrack.js`, `webcrack.json`, `inline.js`,
`inline.json`, `deflatten.json`, `webcrack.log`.

Eight stages, each writing its own artifact so a degraded stage stays visible:

1. **deobfuscate** - WebCrack (`webcrack.js`)
2. **inline** - second AST pass for string arrays declared per IIFE scope, which
   WebCrack does not handle; verifies its output parses and rolls back if not
   (`inline.js`, `inline.json`)
3. **deflatten** - unflattens the control-flow residue WebCrack leaves when the
   deciding value reaches a branch or a switch dispatcher through a control-flow
   storage object instead of as a literal, and resolves the pure call forwarders
   held on that same object, so `S.DmnGW(fetch, url, opts)` becomes
   `fetch(url, opts)` before anything downstream tries to classify it; refuses
   anything it cannot prove and records why (`clean.js`, `deflatten.json`)
4. **structure** - AST facts only, no interpretation (`structure.json`)
5. **explain** - entry points, flows, roles with evidence, porting spec
   (`xray.json`)
6. **anchors** - keyword grep, optional (`analysis.json`)
7. **report** - the same findings as prose (`report.md`)
8. **encode TOON** - `xray.json` re-encoded as TOON for lower token cost, plus a
   char/token reduction report; always runs (`xray.toon`, `toon_stats.json`)

`clean.js` is the output of the last source-rewriting stage, so it is the
deflattened file; `inline.js` is kept as the intermediate, which makes the
deflattening a diff you can read.

Wrapper inlining sits in the deflatten stage rather than in a stage of its own
because it needs the same scope-correct storage-object resolution and the same
rollback gate, and because it is only worth anything ahead of `structure` and
`explain`: those assign roles by matching call text, so a call behind a forwarder
is invisible to them. Only provable pass-throughs are rewritten - body exactly
`return p0(p1, ...)` over plain identifiers in declared order - and anything that
reorders arguments, binds a receiver, or does more than forward is left in place
and counted in `wrapper_skips`. Inventing a call that never ran would be a worse
outcome than leaving a function unclassified.

Every run also writes `pipeline.json`: each stage in order with the command that
ran, whether it succeeded, and the stage's own metadata. A run that dies partway
still writes it, with the failing stage recorded as `ok: false` - so a failure is
a fact in a file rather than something to reconstruct from scrolled-past stderr.

## Querying a finished run

```bash
cd path/to && xq show on          # or: xq name.js show on
```

`xray.json` costs the same ~15k tokens to read whether the answer is one line or
the whole file, and reverse engineering is iterative - find a symbol, trace its
callers, read its source, move on. `xq` answers one question at a time from the
artifacts already on disk, at a few hundred tokens each: `summary`, `find`,
`show`, `callers`/`callees`, `flow`, `port`, `grep`, `entries`, `roles`. On the
sample, `show` of one function is 54x smaller than `xray.json`, and `grep` over
600x.

`show` is the one worth knowing: it prints the function's `xray.json` entry *and*
its source from `clean.js`, so "what is this function" is a single command. Text
by default, `--json` for scripting.

The directory argument is optional, because typing it is the overhead the tool
exists to remove: an explicit `.xrayjs` path still works, a `.js` path resolves to
the run beside it, and omitting it uses the single `.xrayjs` directory in the
current one. When there is more than one, `xq` lists them and exits instead of
choosing - a correct answer about the wrong file is the one mistake a caller has
no way to notice. Which run answered goes to stderr, so stdout stays parseable.

It adds no stage and re-derives nothing - every value comes from an artifact, so
`xq` and `xray.json` cannot give different answers. A test asserts exactly that:
`show --json` returns each of the canonical `functions[]` objects unchanged.

## Tests

```bash
python3 tests/test_xray.py
```

364 checks, no pytest required. Brace matching against strings, comments and
template interpolations; function-vs-keyword detection; cross-scope string-array
resolution; the syntax-validity gate; an end-to-end run over
`fixtures/sample_obfuscated.js` (javascript-obfuscator output: base64-encoded,
rotated string array).

Four of them close the loop rather than checking a field. `test_multiply_style`
runs the Python snippet the porting guide emits against the original JS and
compares digests, for both `Math.imul` and `h * k >>> 0` sources - the two are not
interchangeable, and the guide used to hand out one snippet for both.
`test_deflatten_execution_equivalence` runs `fixtures/flattened.js` under node
before and after the deflattening pass and requires identical stdout. That
comparison is the whole safety story for that stage: a deflattening bug produces
valid JavaScript, so `node --check` and every later stage would accept a file
describing code that never ran. Its counterpart,
`test_deflatten_leaves_undecidable_alone`, requires
`fixtures/flattened_ambiguous.js` to come back byte-identical, with each refusal
recorded by reason.
`fixtures/wrapped_calls.js` carries the same contract for wrapper inlining, and is
checked three ways: stdout identical before and after, every look-alike wrapper
(swapped arguments, `this` binding, side effect, reassigned property, arity
mismatch, member callee, injected argument, escaping store, shadowed namespace)
surviving byte-identical, and - the actual point of the pass - the unclassified
rate measured before and after rather than assumed. On that fixture it moves from
24/25 to 21/25 of the functions `explain` details; measured over all 40 functions
it finds, 97.5% -> 90.0%. The ceiling is low there by construction, since most of
the fixture is deliberately-unsound wrappers that must not be touched.
`test_reachability_ignores_flow_budget` pins that a function reachable only
through anonymous closures is not reported as dead code.
`test_xq_is_a_view_not_an_analysis` runs `xq show --json` over every function in
the sample and requires the object back unchanged, so the query CLI cannot drift
into answering from its own derivation of the facts.

The TOON encoder has its own suite:

```bash
python3 skill/tests/test_toon_encoder.py
```

57 checks covering all four TOON forms and the quoting rules. Thirteen of them
round-trip the encoder's output through the real `@toon-format/toon` reference
decoder and compare the decoded value to the original - including the full
`xray.json` of a real sample, so conformance is verified against the spec's own
implementation rather than against our reading of the spec. The reference decoder
is a devDependency; without `npm install` those checks fail loudly instead of
skipping quietly.

## Layout

| path | purpose |
| --- | --- |
| `skill/SKILL.md` | skill instructions, `xray.json` schema |
| `skill/scripts/xray.py` | orchestrator |
| `skill/scripts/xq.py` | query CLI over a finished `.xrayjs` run |
| `skill/scripts/run_webcrack.py` | WebCrack wrapper, degrades gracefully |
| `skill/scripts/inline_strings.py` | second-pass wrapper + `node --check` gate |
| `skill/scripts/inline_strings.mjs` | Babel transform for per-scope string arrays |
| `skill/scripts/deflatten.py` | deflatten wrapper + `node --check` gate |
| `skill/scripts/deflatten.mjs` | Babel transform for control-flow residue: decidable branches, split-sequence switch dispatchers, pure call-forwarder inlining |
| `skill/scripts/structure.mjs` | AST fact extraction |
| `skill/scripts/structure.py` | Node resolution + graceful degrade |
| `skill/scripts/explain.py` | flows, roles, porting spec |
| `skill/scripts/analyze.py` | anchors, brace matching, block ranking |
| `skill/scripts/report.py` | Markdown report from `xray.json` |
| `skill/scripts/toon_encoder.py` | pure-stdlib JSON-to-TOON encoder |
| `skill/scripts/toon_stats.py` | TOON encode stage + char/token savings report |
| `skill/scripts/node_env.py` | compatible-Node resolution |
| `scripts/install-xq.sh` | puts `xq` on the PATH; idempotent, `--dry-run` |
| `skill/references/` | interpretation guide |
| `skill/tests/` | TOON encoder suite + the Node reference-decoder shim |
| `fixtures/` | obfuscated test inputs, incl. a cross-scope alias case and a pair of control-flow-flattening cases (one flattenable, one deliberately undecidable) |
| `tests/samples/` | real-world sample used for manual verification |
