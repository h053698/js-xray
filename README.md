# js-xray

**English** | [한국어](README.ko.md)

js-xray is a static-analysis toolkit that turns obfuscated or minified JavaScript into structured evidence an agent can inspect quickly and use to port the behavior to another language.

It combines WebCrack with conservative Babel AST passes to resolve string arrays, undo residual control-flow flattening, and inline pure call forwarders. It then extracts function roles, call flows, network contracts, algorithm leads, and a porting specification. Instead of repeatedly loading a large source file, an agent can use the `xq` CLI to retrieve only the relevant function or flow.

## Why use it?

We benchmarked the same Python porting task with Claude Sonnet 5 on the same obfuscated JavaScript file.

### What was analyzed

- **Input:** a synthetic 28 KB JavaScript file compressed into one line and heavily obfuscated with an RC4-encoded string array, control-flow flattening, and self-defending code.
- **Hidden behavior:** a bespoke, non-standard `sign(input, salt)` function that combines two 32-bit state variables, UTF-16 `charCodeAt` input, salt mixing, XOR/shift operations, and both `Math.imul` and ordinary JavaScript multiplication before returning an eight-character lowercase hexadecimal signature.
- **Agent task:** reverse engineer that behavior, explain the state and loop structure, and implement equivalent local Python functions `sign(input, salt)` and `digest(input)` without calling the original JavaScript at runtime.
- **Correctness check:** compare the Python output with the original JavaScript on 13 cases covering empty input, ASCII, Korean text, emoji, surrogate boundaries, U+10FFFF, and a 200-character input. Both arms passed all 13 cases.

The benchmark compares investigation methods, not different models or prompts: the raw arm received only the obfuscated file, while the js-xray arm received the same file plus its precomputed `.xrayjs` artifacts and permission to query them with `xq`.

| Metric | Raw JavaScript only | js-xray + xq | Improvement |
| --- | ---: | ---: | ---: |
| Correctness | 13/13 | 13/13 | Same |
| Wall time | 16m 5s | 6m 50s | 2.4× faster |
| Total tokens | 8,920,677 | 2,273,771 | 74.5% fewer |
| API cost | $18.18 | $4.70 | $13.48 saved |
| Tool calls | 89 | 44 | 50.6% fewer |
| Port implementation started | call #76 | call #9 | Much earlier |

The cost calculation uses the Claude Sonnet 5 rates applied for this benchmark: $2/MTok input and $10/MTok output. See [BENCHMARK.md](BENCHMARK.md) for the complete setup, token-accounting method, and the third arm that also loaded the skill. See [BENCHMARK.drawio](BENCHMARK.drawio) for an editable pipeline and benchmark diagram.

> This is one controlled benchmark. Absolute results vary with file complexity, model, caching, and the tool environment.

## Requirements

- Python 3
- Bun

WebCrack's native `isolated-vm` dependency requires Node `>=22 <23` or `>=24 <25`. The recommended installer reuses a compatible Node, installs Node 24 through fnm/Volta when available, or downloads a verified portable Node 24 runtime. You do not need to configure Node manually.

The automatic portable-runtime path supports macOS and Linux on arm64 or x64. Other platforms can use the installer when `JSXRAY_NODE` points to a compatible Node.

## Installation

### One-command install (recommended)

```bash
bun create h053698/js-xray "$HOME/.local/share/js-xray" --no-install --no-git && bun run --cwd "$HOME/.local/share/js-xray" setup
```

That single copy-paste command downloads js-xray, installs its pinned dependencies, prepares a compatible Node 24 runtime when needed, installs the `js-xray` and `xq` commands, and registers the Codex skill. `--no-install` deliberately lets js-xray prepare Node 24 before installing WebCrack's native dependency.

After it finishes, restart Codex and run:

```bash
js-xray path/to/target.js
xq path/to/target.xrayjs summary
```

If `~/.local/bin` is not already on PATH, the installer prints the exact line to add to your shell profile.

Already cloned the repository? Run the same setup without downloading it again:

```bash
bun run setup
```

Preview every action without writing anything:

```bash
bun run setup --dry-run
```

### Manual installation

#### 1. Clone and install dependencies

```bash
git clone https://github.com/h053698/js-xray.git
cd js-xray

fnm install 24
bun install
```

Volta and nvm also work:

```bash
volta install node@24
# or
nvm install 24
```

Run `npm install` if you prefer npm. Dev dependencies are required to run the complete test suite, including the TOON reference-implementation checks.

#### 2. Install the xq command

```bash
sh scripts/install-xq.sh --dry-run
sh scripts/install-xq.sh
```

The installer creates a symlink from `skill/scripts/xq.py` into a user-owned PATH directory, normally `~/.local/bin/xq`. It:

- never uses sudo or a system directory;
- is safe to run repeatedly;
- refuses to overwrite an unrelated `xq`;
- keeps following the checkout, so `git pull` updates the installed command.

You can also run the script directly without installing it:

```bash
python3 skill/scripts/xq.py summary
```

#### 3. Register the Codex skill

To make Codex discover `$js-xray`, link the repository's `skill/` directory into your Codex skills directory:

```bash
mkdir -p ~/.codex/skills
ln -s "$(pwd)/skill" ~/.codex/skills/js-xray
```

If that destination already exists, inspect it before deciding whether to replace it. Copying the directory also works, but a symlink picks up repository updates automatically.

Restart Codex or refresh its skill list, then invoke:

```text
$js-xray path/to/target.js
```

The CLI remains fully usable without registering the skill.

#### 4. Improve token-stat accuracy (optional)

```bash
pip install tiktoken
```

Without `tiktoken`, the TOON savings report falls back to character counts. Analysis behavior is unchanged.

## Quick start

```bash
js-xray path/to/target.js
```

By default, this creates `target.xrayjs/` next to the input file.

Without the command installer, use `python3 skill/scripts/xray.py path/to/target.js`.

```bash
xq path/to/target.xrayjs summary
xq path/to/target.xrayjs entries
xq path/to/target.xrayjs find sign
xq path/to/target.xrayjs show signData
xq path/to/target.xrayjs port --all
```

If the current directory contains exactly one analysis run, omit the path:

```bash
cd path/to
xq summary
xq show signData
```

## Analysis pipeline

```text
input.js
  │
  ├─ 1. WebCrack deobfuscate
  │      Decode RC4/base64 string arrays and known obfuscation patterns
  │
  ├─ 2. residual string inline
  │      Inline per-scope string arrays and decoders with Babel AST
  │
  ├─ 3. deflatten + wrapper inline
  │      Drop dead branches, linearize switch dispatchers,
  │      and rewrite OBJ.forward(fetch, url) → fetch(url)
  │
  ├─ 4. structure
  │      Extract facts: functions, classes, call edges, and URLs
  │
  ├─ 5. explain
  │      Derive entry points, roles, flows, algorithm leads, and porting data
  │
  ├─ 6. anchor scan
  │      Collect keyword evidence for crypto, network, fingerprinting, storage
  │
  ├─ 7. report
  │      Render a human-readable Markdown report
  │
  └─ 8. TOON
         Encode the same analysis data in a token-efficient representation
```

Every source-rewriting stage verifies that its output parses and passes `node --check`. The deflatten pass leaves a construct unchanged unless semantic preservation can be proven statically, and the wrapper rolls back on failure.

## Output layout

```text
target.xrayjs/
├── pipeline.json       Commands, success state, duration, and metadata per stage
├── webcrack.js         WebCrack output
├── webcrack.json       WebCrack transformation statistics
├── webcrack.log        WebCrack log
├── inline.js           Source after residual string inlining
├── inline.json         String-inlining statistics
├── clean.js            Final rewritten source
├── deflatten.json      Dead-branch, switch, and wrapper statistics
├── structure.json      Complete AST facts and call graph
├── xray.json           Canonical analysis data
├── xray.toon           Token-efficient analysis data
├── toon_stats.json     JSON-versus-TOON size and token statistics
├── analysis.json       Keyword-anchor results
└── report.md           Human-readable report
```

`xray.json` remains the canonical schema and compatibility artifact. `xray.toon` is a derived, lower-token representation for agent re-reads. `xq` can read either artifact and returns the same query results.

## xq commands

Use `xq` to narrow the investigation before loading the complete analysis.

| Command | Purpose |
| --- | --- |
| `xq summary` | File size, entry points, flows, and algorithm overview |
| `xq entries` | Externally reachable entry points |
| `xq find <pattern>` | Search function names and analysis data |
| `xq show <name-or-id>` | Function analysis plus its `clean.js` source slice |
| `xq callers <name>` | Trace callers |
| `xq callees <name>` | Trace callees |
| `xq flow [symbol]` | Show all flows or flows touching a symbol |
| `xq roles [role]` | Query functions by role |
| `xq port [algorithm|--all]` | Retrieve porting data for another language |
| `xq grep <pattern>` | Search `clean.js` with function attribution |

Recommended investigation order:

1. Run `xq summary` to classify the module at a glance.
2. Use `xq entries` and `xq flow` to narrow the path from external input.
3. Find relevant functions with `xq find` and `xq roles`.
4. Read only the selected area with `xq show`, `xq callers`, and `xq callees`.
5. For a language port, inspect `xq port --all` and only the necessary `clean.js` slices.
6. Read the complete source only when the static evidence is insufficient or runtime behavior must be verified.

## Pipeline options

```bash
python3 skill/scripts/xray.py input.js \
  --top 50 \
  -o output.xrayjs
```

| Option | Description |
| --- | --- |
| `-o, --outdir PATH` | Select the output directory |
| `--top N` | Number of functions detailed in `xray.json` |
| `--anchors FILE` | Use a custom anchor file |
| `--skip-deobfuscate` | Skip WebCrack |
| `--skip-inline` | Skip residual string inlining |
| `--skip-deflatten` | Skip control-flow deflattening |
| `--skip-anchors` | Skip the keyword-anchor scan |
| `--mangle` | Enable WebCrack mangling |

## Safety and limitations

- This is static analysis. Runtime-generated code, network responses, and browser-state-dependent behavior require separate validation.
- JSVMP-like code is detected and flagged, but custom bytecode is not fully recovered.
- A single matching constant is reported as a lead, not asserted to identify a standard hash.
- Ports of `charCodeAt`-based algorithms preserve JavaScript UTF-16 code-unit semantics.
- Deflattening and wrapper inlining refuse shapes whose behavior cannot be proven safe.
- The pipeline does not execute the analyzed program, but WebCrack and Node dependencies should still be managed as trusted, pinned tooling.

## Tests

```bash
python3 tests/test_xray.py
python3 skill/tests/test_toon_encoder.py
```

The suites cover scoped string inlining, execution-equivalence checks for deflattening, ambiguous structures that must be refused, call wrappers, xq/TOON parity, the installer, and the complete pipeline.

## Repository layout

| Path | Purpose |
| --- | --- |
| `skill/SKILL.md` | Codex skill instructions and agent investigation workflow |
| `skill/scripts/xray.py` | Pipeline orchestrator |
| `skill/scripts/xq.py` | Query CLI for analysis artifacts |
| `skill/scripts/run_webcrack.py` | WebCrack wrapper |
| `skill/scripts/inline_strings.py/.mjs` | Scope-safe string inlining |
| `skill/scripts/deflatten.py/.mjs` | Control-flow and call-wrapper rewriting |
| `skill/scripts/structure.py/.mjs` | AST fact extraction |
| `skill/scripts/explain.py` | Role, flow, and porting-data generation |
| `skill/scripts/toon_encoder.py` | JSON-model TOON encoder and decoder |
| `scripts/install-xq.sh` | Install xq on the user PATH |
| `fixtures/` | Regression fixtures for obfuscation patterns |
| `tests/` | Main integration suite |
| `BENCHMARK.md` | Detailed benchmark report |
| `BENCHMARK.drawio` | Editable pipeline and benchmark diagram |
