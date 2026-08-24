# Analysis guide

How to turn js-xray output into an explanation or a working port.

## 1. Confirm the deobfuscation actually worked

Check `webcrack.json` first:

- `"deobfuscated": true` with a `string_array` name means encoded strings were inlined. Trust `clean.js`.
- `"deobfuscated": false` means no string array was found. Either the file was only minified (fine - analysis still works), or it uses a scheme WebCrack does not recognise.
- An `error` field means WebCrack did not run at all. Fix Node before drawing conclusions, because identifiers are still encoded.

Then check `inline.json` for the second pass:

- `replaced` > 0 means the file declared string arrays per scope and they were resolved on the AST. `decoders` lists each one with its array size and offset.
- `rolled_back: true` means the rewrite would not have parsed, so `clean.js` is the WebCrack output only. Residual `X(42)`-style calls are expected; resolve the ones you care about by hand, using the holder function that is in scope at the call site.
- `replaced: 0` with arrays found means the decoders were impure (base64, RC4) and deliberately skipped.

A useful sanity check: grep `clean.js` for a readable domain word. If you see plaintext method names, inlining succeeded. Then grep for leftover decoder calls - a short name followed by a bare integer, like `i(47)`. None left means the file is fully resolved.

## 2. Read xray.json, not the source

`xray.json` is the deliverable. Start at `summary` for the shape of the file,
then walk `flows[]` - each is an ordered path from an entry point, with `does`,
`network` and `algorithms` on each step. That is enough to describe the module
without opening `clean.js`.

For a specific function, look it up in `functions[]` (sorted by `importance`) and
work outward:

1. **Inputs** - `params`, `reads` (the browser surface it touches)
2. **Transform** - `algorithms`, and the `roles` with their `evidence`
3. **Output** - `returns`, `network`

Only open `clean.js` at the cited `lines` when you need to confirm something, or
when a role's `confidence` is `low`. Roles marked `inherited_from` came from an
inline closure - that is where obfuscated code usually keeps the real work, so
the closure is what to read, not the wrapper.

The anchor pass (`analysis.json`) is a keyword grep and independent of all this.
It is useful for chasing an identifier you already know.
## 3. Common obfuscation shapes

**String array + decoder.** A big array of strings plus a lookup function, often base64-encoded and rotated at load time. WebCrack handles this; it is what `inline-decoded-strings` reports.

**One string array per scope.** The same scheme, but repeated inside each IIFE, each with its own holder and decoder. WebCrack picks one and leaves the rest, which is what the second pass exists for. The tell is a report that shows a successful deobfuscation while key functions are still named `(anonymous)`.

When resolving these by hand, note that the decoder is usually plaintext by this point and can be read directly:

    function U() { const t = ["_getAnswer", ...]; return (U = function () { return t; })(); }
    function O(t, n) { const e = U(); return (O = function (t, n) { return e[t -= 0]; })(t, n); }

So `O(n)` is `U()[n - offset]`. Watch the offset, and watch which array is in scope - short alias names get reused across scopes for different arrays, so the same `i(4)` means different things in different functions.

**Control-flow flattening.** Logic hidden behind a `switch` inside a `while` loop with a state variable. WebCrack's `control-flow-switch` pass undoes common cases. If the code still looks like a state machine, trace the state variable by hand.

**Proxy/wrapper functions.** Every call goes through `_0xabc(a, b)` which just forwards. `inline-decoder-wrappers` removes these.

**Self-defending / debugger traps.** Code that breaks when beautified, or infinite `debugger` loops. Static analysis is unaffected; only dynamic debugging is.

## 4. Porting to Python: the traps

`porting.pitfalls[]` lists the ones that apply to your file. The mechanics:

**The 32-bit multiply is two different operations.** This is the trap that costs
the most time, because both versions look identical after masking. Check
`multiply_style` on the algorithm entry:

| JS source | `multiply_style` | Python |
| --- | --- | --- |
| `Math.imul(h, k)` | `imul` | `(h * k) & 0xFFFFFFFF` |
| `h * k >>> 0` | `truncated-float` | `int(float(to_int32(h)) * k) & 0xFFFFFFFF` |

`Math.imul` is an exact 32-bit product. `h * k >>> 0` is not: the product is
computed in float64 and only then truncated. With `h` a signed int32 from the
preceding `^`, `h * 16777619` passes 2^53, so the low bits are already gone -
the rounding is part of the algorithm. Both the float step and the sign step
matter; masking to unsigned first still gives a different digest.

```python
def to_int32(h):
    h &= 0xFFFFFFFF
    return h - 0x100000000 if h >= 0x80000000 else h

# JS: h = h * 16777619 >>> 0
h = (h ^ ord(ch)) & 0xFFFFFFFF
h = int(float(to_int32(h)) * 16777619) & 0xFFFFFFFF
```

**uint32 wrapping everywhere else.** Python ints are unbounded, so mask after
every shift and xor too, not just the multiply. Forgetting this gives
correct-looking output that diverges after a few characters.

**Signed vs unsigned.** JS `|0` produces a *signed* 32-bit int, `>>>0` an
unsigned one. Use `to_int32` above where the source relies on the signed form.

**charCodeAt is UTF-16.** `ord(ch)` matches for the BMP, but characters above
U+FFFF are two JS code units. If the input can contain emoji, iterate over
`s.encode("utf-16-le")` pairs instead.

**JSON.stringify formatting.** JS emits no spaces and preserves insertion order.
Python's default adds spaces after separators, which changes any hash computed
over the string:

```python
json.dumps(body, separators=(",", ":"))
```

**Timestamps.** `Date.now()` is integer milliseconds; `performance.now()` is a
float relative to page load. Mixing them up shifts the hash input. Check
`porting.inputs[]` for which one the file reads.
## 5. Validating the port

Do not compare end-to-end output first - it usually depends on time and
randomness. Instead:

1. Pin every variable input (fixed timestamp, fixed UA, fixed seed).
2. Extract the algorithm from `clean.js` into a standalone `.mjs` and run it
   under Node with those same inputs.
3. Compare the intermediate hash, not the final token.
4. Only then re-enable real timestamps.

Step 2 is not optional. A port that agrees on `"abc"` and disagrees on a real
user-agent has a 32-bit arithmetic bug, and the only way to see it is to run
both. `tests/test_xray.py::test_multiply_style` does exactly this round trip for
the snippets the guide emits.

If step 3 matches but the server still rejects the result, the problem is the
request contract, not the maths. Compare against `porting.network_contracts[]`:
header set, `credentials` mode, and the exact body shape.
## 6. Fingerprint values

Anything read from `navigator`, `screen`, canvas or WebGL is an environment claim. Two rules:

- **Consistency beats realism.** A slightly unusual but stable fingerprint attracts less attention than a plausible one that changes every request.
- **Match the claimed UA.** Do not report a macOS user-agent alongside Windows-specific WebGL renderer strings.

## 7. When the report finds nothing

- No anchors matched: try `--anchors` with identifiers you already know, or check whether the file is a loader that fetches the real payload.
- Every function is `unclassified` and the roles histogram is flat: the file is
  probably a bundle of unrelated modules. Locate the relevant one in `clean.js`
  and re-run js-xray on just that slice.
- `flows[]` is empty: no entry point was identified. Check `module.exports` and
  `module.global_assignments` in `structure.json` - a pure library with no
  side effects and no exports has nothing for the tracer to start from.
