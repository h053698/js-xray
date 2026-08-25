---
name: js-xray
description: Reverse-engineer obfuscated or minified JavaScript into a structured JSON explanation. Deobfuscates with WebCrack, inlines per-scope string arrays, unflattens residual control flow, then extracts entry points, call flows, per-function roles with evidence, network contracts and a porting spec into xray.json. Use when given a .js file to understand, explain to a person, or reimplement in another language.
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

Prints the path to `xray.json` and writes `<name>.xrayjs/` next to the input:

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
| `inline.js` | intermediate, after string inlining and before deflattening |
| `deflatten.json` | deflattening results: branches dropped, switch sequences linearised, call wrappers inlined, and the reason for every construct deliberately left alone |
| `xray.toon` | `xray.json`'s content re-encoded as [TOON](https://github.com/toon-format/toon) - what `xq` reads by default, and what to read yourself instead of `xray.json` when re-loading the whole result into an LLM context |
| `toon_stats.json` | the measured char/token reduction of `xray.toon` vs `xray.json` for this run - read this to see the actual savings, not an assumed one |
| `pipeline.json` | run log: what each stage actually did, its command, ok/fail, and its own stdout metadata -- read this after a run to see which stage degraded or failed, instead of scrolling stderr |

Eight stages: **deobfuscate -> inline -> deflatten -> structure -> explain -> anchors -> report -> encode TOON**.
Each writes its own file, so a stage that degrades is visible rather than silent.

### What the deflatten stage does, and what it refuses

WebCrack already unflattens javascript-obfuscator's switch dispatchers and its
always-true/always-false branches - but only when the deciding value is a literal
sitting in the expression. The obfuscator usually routes it through a per-function
control-flow storage object first, and when WebCrack cannot inline that object,
both of its passes silently stop matching. The result is a `clean.js` with every
string decoded and a large share of its lines unreachable, which is where a
reader's tokens go. This stage resolves the deciding value through the storage
object and finishes the job.

It resolves three things:

- a branch whose test is statically decided, because both operands resolve to the
  same literal or the same binding - directly, or through a comparison helper
  whose body is exactly `return a OP b` over its two parameters;
- a `while (true) { switch (seq[i++]) { ... } break; }` dispatcher driven by a
  statically known `"3|1|2".split("|")` sequence, whose case bodies are the
  original statements in shuffled order.
- a pure call forwarder held on the same storage object: `S.DmnGW(fetch, url, opts)`
  where `DmnGW` is `function (a, b, c) { return a(b, c); }` becomes
  `fetch(url, opts)`.

That third one is a visibility fix rather than a control-flow fix, and it is why
this stage has to run before `structure` and `explain`. The role classifier
matches call text against markers - `fetch`, `JSON.stringify`, `crypto.subtle`,
`atob` - so a call sitting behind a forwarder is a function that reports as
"(unclassified)" no matter what it actually does. A wrapper is only inlined when
its body is **exactly** `return p0(p1, p2, ...)` over plain identifier parameters
forwarded in their declared order, and the call site supplies exactly as many
arguments as the wrapper has parameters. Left alone, and counted in
`wrapper_skips`: wrappers that reorder or drop arguments (`return a(c, b)`), that
bind a receiver (`a.call(x, b)`, `a.apply(...)`), that add arguments of their own,
that do anything besides forward, that are async or generators, that take rest,
default or destructured parameters, and any wrapper on a property that is written
somewhere or on a storage object that escapes. A member expression passed as the
forwarded callee is refused too, since `W(obj.m, x)` calls `m` unbound while
`obj.m(x)` does not - with a narrow exception for a short list of documented
`this`-free statics (`JSON.parse`, `JSON.stringify`, `Math.*`, `Date.now`,
`Object.keys`, `String.fromCharCode` and similar), and only when their namespace
is not shadowed by a local binding.

It deliberately leaves alone anything it cannot prove, because a wrong decision
here is invisible: dropping the live branch instead of the dead one, or
reordering case bodies that were not independent, still yields valid JavaScript,
so no syntax check catches it and every later stage would go on to describe code
that never ran. Refused constructs include a sequence computed at runtime, a
dispatcher a case body `break`s out of, a cursor or sequence variable read from
outside the dispatcher, a storage object whose properties are written or read
under a dynamic key, a comparison helper that does anything besides compare, and
a dead branch that hoists a `var` read after it. The same reasoning governs
wrapper inlining, where the cost of being wrong is worse still: a rewritten call
that never happened is a finding this pass manufactured, and a residual
unclassified function is much cheaper than a fabricated `fetch`. Every refusal is
counted by reason in `deflatten.json` (`switch_skips`, `dead_branch_skips`,
`wrapper_skips`), so a partially flattened file reads as partial rather than
clean. A file with no such residue passes through byte-identical.

Once a run exists, `scripts/xq.py` queries these artifacts a question at a time
instead of re-reading `xray.json` for each one - see
[the query CLI](#the-query-cli-xqpy).

### xray.json or xray.toon?

Same data, two encodings, and `xq` reads either one: it prefers `xray.toon` and
falls back to `xray.json`, naming on stderr which it read. Every `xq` answer is
identical whichever it found, so this is not a choice you need to make before
asking a question.

It becomes a choice when you read a file yourself:

- Loading the whole result into context (your own next turn, a sub-agent, a
  summarization pass): `xray.toon`, for the same facts in materially fewer
  tokens. `toon_stats.json` has the measured reduction for that run, so the
  saving is not something you have to assume.
- Parsing field-by-field against the schema: either carries the same values, but
  the schema section below documents the JSON shape, so `xray.json` is the one to
  match against.

Before reading either one whole, check whether `xq` already answers the question
- see [reading order](#reading-order-xq-first-cleanjs-last).

### Answering a question about this run

Most questions are narrower than the whole file. `scripts/xq.py` answers those
from the artifacts already on disk for a few hundred tokens each, so a symbol
lookup does not cost the same as reading everything:

```bash
xq <subcommand> [args] [--json]        # from the directory holding the run
xq <name>.js <subcommand> [args]       # or name the source file
```

The path is optional: run `xq` where the `.xrayjs` directory is and it finds it.
Below, `xq ...` means either form - drop in `python3 skill/scripts/xq.py` if `xq`
is not installed (`sh scripts/install-xq.sh`).

| question | read |
| --- | --- |
| "What does this module do?" / "Explain it to me" | `xray.json` -> `summary`, `flows[]` (see below), or `xq summary` for the short form |
| "What is function `on`?" | `xq show on` - its roles, evidence, calls, network contract **and** its source from `clean.js`, in one answer |
| "Where is the symbol that does X?" | `xq find X` - one line per hit; add `--strings` to search string literals too |
| "Who calls this? What does it call?" | `xq callers on` / `xq callees on`, `--depth N` for more hops |
| "Where does this function sit in the flow?" | `xq flow on` - only the flows it appears in, not all of `flows[]` |
| "How do I reimplement/decrypt this?" | `xq port` for the whole spec, `xq port FNV` for one algorithm with its Python snippet; or `xray.json` -> `porting` |
| "Which function contains this line/string?" | `xq grep <pattern>` - like `grep` over `clean.js`, but each hit names its enclosing function |
| "Where does control enter?" | `xq entries [--traced]` |
| "Which functions hash / fingerprint / send?" | `xq roles hash`, or `xq roles` for the histogram |
| "What did the pipeline actually do on this run? Did anything fail or degrade?" | `pipeline.json` - each stage's `ok`, `meta`, and `cmd` in order, no source reading required |
| "Why does `xray.json` look empty/degraded?" | `pipeline.json` for which stage failed, then that stage's raw stdout/stderr; `confidence_notes[]` in `xray.json` for caveats |
| "Is the string-array deobfuscation trustworthy?" | `webcrack.json` (`"string array"`, `decoders`) and `inline.json` (`unresolved`, `rolled_back`) |
| "Is any of `clean.js` still flattened, or did anything get removed?" | `deflatten.json` - what was dropped, linearised or inlined, and `switch_skips`/`dead_branch_skips`/`wrapper_skips` for what was left alone and why; diff `inline.js` against `clean.js` to see the exact change |
| "Can I trust these findings as the module's real logic at all?" | `xray.json` -> `summary.vm_obfuscation`; anything but `none` means the analysis describes a bytecode interpreter, with the evidence in `vm_signals` |
| "I need the facts but I'm token-constrained" | `xq` for a specific question - always try this first; `xray.toon` (+ `toon_stats.json`) only when you genuinely need all of it. Never slice `clean.js` by hand for this |
| "What exactly ran, and can I reproduce this stage by hand?" | `pipeline.json` -> that stage's `cmd` list, runnable as-is |

### Reading order: xq first, clean.js last

Work outside in, and stop at the first step that answers the question:

1. **`xq summary`** - what the file is, how many functions, which roles, the
   caveats. A few hundred tokens, and it tells you where to look next.
2. **`xq roles X` / `xq flow X` / `xq show X` / `xq find X` / `xq callers X`** -
   narrow to the functions that matter, then read those. `xq show` already
   includes the source of the function it describes, so this usually is the
   answer.
3. **`xray.toon`** - when you genuinely need the entire structured result at
   once, e.g. porting the module end to end.
4. **`clean.js` directly** - last resort, for something no artifact recorded.

Reading `clean.js` in chunks is the expensive mistake to avoid. It has happened:
an agent with `xq` and `xray.toon` available split `clean.js` into eight pieces
and read them all, spent over half its context on it, and afterwards said it had
simply forgotten the tools were there. Slicing the source costs several times
what the same answer costs through `xq`, and the slices arrive without the roles,
evidence, flows and contracts that the analysis already established - so you end
up re-deriving by eye what `xray.json` states outright.

If you do need source, prefer `xq show <fn>` (the function, with its analysis) or
`xq grep <pattern>` (matching lines, each attributed to its enclosing function)
over reading line ranges yourself.

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
  A hoisted endpoint constant is followed back to its literal, so `url` is the
  address; when that required a lookup the original call-site expression is
  kept in `url_expression`.
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

## The query CLI (xq.py)

`xq` answers one question at a time from the artifacts a run already produced.
It adds no stage and repeats no analysis - every value it prints was decided by
`explain.py` and written to a file. Reach for it when the question is narrower
than the file, which is most of reverse engineering: `xray.json` costs the same
~15k tokens whether the answer is one line or all of it, and four questions in,
the context is gone.

**Try `xq` before reading any artifact by hand, and before reading `clean.js` at
all.** Most questions are narrower than the file, and the whole point of the tool
is that a narrow question should cost a narrow amount. See
[reading order](#reading-order-xq-first-cleanjs-last).

It reads `xray.toon` when the run has one and `xray.json` otherwise, and says
which on stderr. The answer is identical either way; `stdout` carries the answer
alone, so `--json` stays parseable and diffing the two forms shows nothing.

### Installing it

```bash
sh scripts/install-xq.sh        # symlinks xq onto the PATH; --dry-run to preview
```

That links `xq` into `~/.local/bin` (or `~/bin`), leaves an unrelated `xq` alone,
and is safe to re-run. Without it, every example below still works as
`python3 skill/scripts/xq.py ...`.

### Naming the run

```bash
xq [TARGET] <subcommand> [args] [--json]
```

`TARGET` is optional, and leaving it out is the point: the path is pure overhead
on a tool whose reason to exist is spending fewer tokens per answer. It resolves
in three steps.

| you write | xq uses |
| --- | --- |
| `xq name.xrayjs show on` | that directory, exactly as before |
| `xq name.js show on` | the `name.xrayjs` beside the source file |
| `xq show on` | the one `.xrayjs` directory in the current directory |

The cwd search looks one level down, no deeper. Two candidates there makes `xq`
list them and exit non-zero rather than choose - a right answer about the wrong
file is indistinguishable from a right answer, so it is never guessed. The run it
settled on goes to stderr; stdout stays the answer alone, `--json` included.

| subcommand | answers |
| --- | --- |
| `summary` | what the file is, the role histogram, endpoints, and the caveats. Start here; it is ~1KB |
| `find PATTERN` | symbol search over display names and raw names. Regex, or substring when the pattern is not valid regex. `--strings` also searches string literals and url/path literals |
| `show NAME\|ID` | the complete answer for one function: its `functions[]` entry **and** its source from `clean.js`. Source truncates at 40 lines; `--full` or `--lines N` overrides |
| `callers NAME` / `callees NAME` | call relationships from `structure.json`'s `call_graph.edges`, `--depth N` for more hops. Every answer repeats that the edges are name-resolved |
| `flow NAME` | only the flows that function appears in, with its own step marked `>` |
| `port [NAME]` | the porting spec. No argument gives algorithms, network contracts, inputs and pitfalls; an algorithm name, id or family gives just that one, with the Python snippet `report.md` would emit |
| `grep PATTERN` | search `clean.js` and name the enclosing function for every hit - the part plain `grep` cannot tell you |
| `entries [--traced]` | entry points, with `why` and which ones were traced |
| `roles [ROLE]` | functions carrying a role, or the histogram when no role is named |

Functions are addressable by id (`fn197`) or name (`on`). An ambiguous name lists
the candidates and asks for an id instead of picking one. Text output is the
default because it is the compact form; `--json` gives the same values for
scripting.

A worked sequence, which is how the tool is meant to be used - each step a few
hundred tokens, no full-file read anywhere in it:

```bash
cd wherever/sentinel_sdk.xrayjs/..   # no path in any command after this
xq summary              # 220 functions, one fetch, FNV+murmur3
xq roles hash           # -> fn49, fn48 carry hash/digest
xq show fn49            # the iife, its constants, its source
xq flow fn49            # where it sits in the traced path
xq callers fn48         # who reaches its enclosing method
xq port FNV             # constants, multiply style, snippet
xq grep "Math.imul"     # confirm the multiply in the source
```

`callers` is asked about `fn48` rather than `fn49` there for a reason: `fn49` is
an anonymous iife, and the call graph resolves by name, so nothing points at it.
Use `flow` for anonymous functions and `callers` on the nearest named ancestor -
`xq` reports the empty result rather than inventing an edge.

`show on` on that sample:

```
fn197  on  L1102-1126
async on(t, n)   importance 80   reached from an entry point

role: network transport (high)
      performs fetch
      target Zt + "req"

calls: fetch, rn, Date.now

network: fetch POST Zt + "req"
      body: rn({ p: n }, t)
      credentials: include

clean.js L1102-1126:
1102    async function on(t, n) {
...
```

### What xq will not do

It never re-derives a finding. Roles, confidences, importances, algorithm
families and flow steps are all served as written, so an answer from `xq` and an
answer from `xray.json` cannot disagree - a query tool that made its own
judgements would be worse than no query tool, because the caller who skipped
`xray.json` has nothing to check it against. Two consequences worth knowing:

- `xray.json` details only its top `--top` functions (25 by default). `find` and
  `show` still answer for the rest, marked `~`, but with a name, a line range and
  source only - there is no role or importance to report, and `xq` does not invent
  one. Raise `--top` and re-run the pipeline if you need them classified.
- An unknown `schema` value, a run with neither `xray.toon` nor `xray.json`, or a
  missing `structure.json` under `callers` is an error naming the file, not a
  quiet empty answer. An `xray.toon` that no longer parses is reported with the
  line that broke, rather than silently answered from `xray.json` instead - the
  two are meant to hold the same value, and one that stopped parsing means they
  might not.
- It will not pick between two runs. With the path omitted and several `.xrayjs`
  directories in reach, it lists them and exits - the one wrong answer a caller
  cannot detect is a correct one about the wrong file.

When `summary.vm_obfuscation` is `vm-obfuscated` or `suspected`, `show`, `flow`,
`port` and `summary` lead with a one-line warning. On a VM-obfuscated file every
function is an interpreter part, and an agent querying one function at a time
would otherwise never see the verdict.


## xray.json schema

```
schema           "js-xray/explanation/1"
source_file      path analyzed (clean.js, unless deobfuscation was skipped)
size             {lines, bytes}
summary          {functions, classes, entry_points, roles{name:count}, endpoints[]}
                 plus vm_obfuscation: "vm-obfuscated" | "suspected" | "none" |
                 "unknown" -- check this first; when it is not "none" the rest of
                 the file describes a bytecode interpreter, not the module
entry_points[]   {id, name, line, why, traced, shares_flow_with?}
flows[]          {entry, steps[], also_entered_by[]}
  steps[]        {depth, id, name, line, reached_by, does[], network?, algorithms?}
functions[]      {id, name, raw_name, kind, lines[2], params[], async,
                  roles[]{role, confidence, evidence[], inherited_from?},
                  calls[], reads[], network[], algorithms[], returns[],
                  reachable_from_entry, importance}
classes[]        {name, superClass, start_line, end_line, methods[], getters[],
                  setters[], fields[], static[]}
module           {exports[], imports[], global_assignments[]}
literals         {urls[]{url, line}, paths[]}
porting          {algorithms[], network_contracts[], inputs[], pitfalls[]}
  algorithms[]   {function, id, lines[2], families[], constants[], operators[],
                  returns[], loops, multiply_style, multiply_note}
  network_...[]  {kind, url, url_expression?, method, headers[], body,
                  credentials, function, id, line}
  inputs[]       {property, read_by[]}
  pitfalls[]     {issue, detail}
vm_signals       {verdict, score, signals[]} -- the evidence behind
                 summary.vm_obfuscation. verdict repeats the summary field;
                 score is 0-100 weighted by which signals matched (the two core
                 ones alone reach 70); signals[] is {kind, detail, line} per
                 matched signal, so the dispatch loop can be found by hand
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
| another VM-obfuscation signal | `detectVmSignals()` and its `VM_*` thresholds | `scripts/structure.mjs` |
| another capability from calls | `CALL_MARKERS` | `scripts/explain.py` |
| another role | the `add()` calls in `classify()` | `scripts/explain.py` |
| another porting snippet | `PORT_SNIPPETS` | `scripts/report.py` |

`PORT_SNIPPETS` is keyed by `(family, multiply_style)`. Use `None` for the style
when the algorithm has no 32-bit multiply, as with `SHA-256`.

A new `PORT_SNIPPETS` entry reaches `xq port` as well as `report.md`: `xq`
imports `report.port_snippet` rather than keeping its own table.

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
  network-fetched code. An `anti-analysis` hit in `analysis.json` (the anchor
  pass, not a role in `xray.json`) is a hint that static reading will be
  incomplete.
- **Very large bundles**: extract the relevant module first, or raise `--top`.
- **VM-obfuscated files cannot be read statically.** JSVMP-style protection
  compiles the original logic into a bytecode array and ships an interpreter for
  it, so the only functions left to extract are the interpreter's own parts. The
  pipeline detects this and says so -- `summary.vm_obfuscation`, the first entry
  of `confidence_notes[]`, and a banner at the top of `report.md` -- but it does
  **not** recover the bytecode. When the verdict is `vm-obfuscated`, stop: the
  flows, roles and porting spec describe the virtual machine, and reporting them
  as the module's behaviour would be confidently wrong. `suspected` means part of
  the fingerprint matched; check `vm_signals[].line` against `clean.js` before
  trusting a flow that runs through the dispatch loop. Detection is tuned against
  false positives -- `vm-obfuscated` requires both a bitmasked dispatch switch
  and constant jump addresses written back into its register -- so ordinary
  minified bundles and hand-written state machines come back `none`.
