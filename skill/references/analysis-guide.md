# Analysis guide

How to turn a js-xray report into working code.

## 1. Confirm the deobfuscation actually worked

Check `webcrack.json` first:

- `"deobfuscated": true` with a `string_array` name means encoded strings were inlined. Trust `clean.js`.
- `"deobfuscated": false` means no string array was found. Either the file was only minified (fine - analysis still works), or it uses a scheme WebCrack does not recognise.
- An `error` field means WebCrack did not run at all. Fix Node before drawing conclusions, because identifiers are still encoded.

A useful sanity check: grep `clean.js` for a readable domain word. If you see plaintext method names, inlining succeeded.

## 2. Read the key blocks in order

The report ranks functions by distinct anchor count. The top block is almost always the entry point that collects inputs, hashes them, and sends the result. Work outward from it:

1. What are the function's **inputs**? (parameters, globals, environment probes)
2. What **transform** is applied? (the hashing/crypto anchors)
3. What is the **output shape**? (the JSON body or token string)

## 3. Common obfuscation shapes

**String array + decoder.** A big array of strings plus a lookup function, often base64-encoded and rotated at load time. WebCrack handles this; it is what `inline-decoded-strings` reports.

**Control-flow flattening.** Logic hidden behind a `switch` inside a `while` loop with a state variable. WebCrack's `control-flow-switch` pass undoes common cases. If the code still looks like a state machine, trace the state variable by hand.

**Proxy/wrapper functions.** Every call goes through `_0xabc(a, b)` which just forwards. `inline-decoder-wrappers` removes these.

**Self-defending / debugger traps.** Code that breaks when beautified, or infinite `debugger` loops. Static analysis is unaffected; only dynamic debugging is.

## 4. Porting to Python: the traps

**uint32 wrapping.** JS `(h * PRIME) >>> 0` truncates to 32 bits. Python ints are unbounded, so mask every step:

```python
h = (h * 16777619) & 0xFFFFFFFF
```

Forgetting this gives correct-looking output that diverges after a few characters.

**Signed vs unsigned.** JS `|0` produces a *signed* 32-bit int, `>>>0` an unsigned one. To emulate signed:

```python
v &= 0xFFFFFFFF
if v >= 0x80000000:
    v -= 0x100000000
```

**charCodeAt is UTF-16.** `ord(ch)` matches for the BMP, but characters above U+FFFF are two JS code units. If the input can contain emoji, iterate over `s.encode("utf-16-le")` pairs instead.

**JSON.stringify formatting.** JS emits no spaces and preserves insertion order. Python's default adds spaces after separators, which changes any hash computed over the string:

```python
json.dumps(body, separators=(",", ":"))
```

**Timestamps.** `Date.now()` is integer milliseconds; `performance.now()` is a float relative to page load. Mixing them up shifts the hash input.

## 5. Validating the port

Do not compare end-to-end output first - it usually depends on time and randomness. Instead:

1. Pin every variable input (fixed timestamp, fixed UA, fixed seed).
2. Run the JS in a browser console or Node with those same fixed inputs.
3. Compare the intermediate hash, not the final token.
4. Only then re-enable real timestamps.

If step 3 matches but the server still rejects the result, the problem is the request contract (headers, cookies, ordering), not the maths.

## 6. Fingerprint values

Anything read from `navigator`, `screen`, canvas or WebGL is an environment claim. Two rules:

- **Consistency beats realism.** A slightly unusual but stable fingerprint attracts less attention than a plausible one that changes every request.
- **Match the claimed UA.** Do not report a macOS user-agent alongside Windows-specific WebGL renderer strings.

## 7. When the report finds nothing

- No anchors matched: try `--anchors` with identifiers you already know, or check whether the file is a loader that fetches the real payload.
- Key blocks are huge and generic: the file is probably a bundle. Locate the relevant module in `clean.js` and re-run js-xray on just that slice.
