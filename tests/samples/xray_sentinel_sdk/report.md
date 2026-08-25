# js-xray report

| | |
|---|---|
| source | `clean.js` |
| deobfuscated | `clean.js` |
| size | 1352 lines, 38348 bytes |
| functions | 220 (25 detailed below, 195 omitted by --top) |
| classes | 1 |
| entry points | 29 |
| strings inlined | 497 total: webcrack 10, inline_strings 487 |

## What this module does

Roles found across 220 functions:

- lookup/decoder shim - 29 function(s)
- encode/decode - 11 function(s)
- serialization - 10 function(s)
- environment fingerprinting - 4 function(s)
- validation/error path - 3 function(s)
- bit mixing (unrecognised algorithm) - 2 function(s)
- cryptography (platform) - 2 function(s)
- hash/digest - 2 function(s)
- persistence - 2 function(s)
- network transport - 1 function(s)
- scheduling/retry - 1 function(s)
- 165 function(s) had no distinguishing facts, typically obfuscation scaffolding and small helpers

Endpoints referenced:

- `https://github.com/uuidjs/uuid#getrandomvalues-not-supported`
- `https://chatgpt.com/backend-api/sentinel/`

## Flows

### _.getEnforcementTokenSync

Entry at line 172 - public method of class _.

The same path is entered by `_.initializeAndGatherData` (L166), `_.startEnforcement` (L169).

- `_.getEnforcementTokenSync` (L172)
  - `_._getAnswer` (L195)
    - `_._generateAnswerSync` (L258)
      - `_.getConfig` (L316) - environment fingerprinting
        - `j` (L321) - lookup/decoder shim
        - `T` (L325)
        - `_.getConfig > <callback@L318c173>` (L318)
        - `_.getConfig > <callback@L318c193>` (L318)
        - `_.getConfig > <callback@L318c243>` (L318)
        - `_.getConfig > <callback@L318c283>` (L318)
      - `_._runCheck` (L230) - hash/digest
        - `_._runCheck > <iife@L235-248>` (L235) - hash/digest; algorithms: FNV-1a 32-bit, murmur3 fmix32
          - `t` (L655)
        - `E` (L334) - encode/decode, serialization
        - `s` (L8)
        - `s` (L10)
      - `_.buildGenerateFailMessage` (L255)
    - `_._generateAnswerAsync` (L274)
      - `_._generateAnswerAsync > <callback@L282-290>` (L282)
        - `_._generateAnswerAsync > <callback@L285-287>` (L285)
    - `_._getAnswer > <callback@L221-224>` (L221)
    - `_._getAnswer > <callback@L224-228>` (L224)

### _.getRequirementsTokenBlocking

Entry at line 192 - public method of class _.

- `_.getRequirementsTokenBlocking` (L192)
  - `_._generateRequirementsTokenAnswerBlocking` (L302)
    - `E` (L334) - encode/decode, serialization
    - `_.getConfig` (L316) - environment fingerprinting
      - `j` (L321) - lookup/decoder shim
      - `T` (L325)
      - `_.getConfig > <callback@L318c173>` (L318)
      - `_.getConfig > <callback@L318c193>` (L318)
      - `_.getConfig > <callback@L318c243>` (L318)
      - `_.getConfig > <callback@L318c283>` (L318)

### t.setCookie

Entry at line 959 - function with no in-file caller.

- `t.setCookie` (L959) - persistence, lookup/decoder shim
  - `a` (L904) - serialization
  - `c` (L1149)
  - `u` (L901)
  - `t.setCookie > <callback@L995-998>` (L995) - lookup/decoder shim
    - `t` (L655)

### gn

Entry at line 1193 - function with no in-file caller.

- `gn` (L1193) - scheduling/retry
  - `jt` (L528) - serialization, encode/decode, lookup/decoder shim
    - `jt > <callback@L529-628>` (L529) - serialization, encode/decode, lookup/decoder shim
      - `jt > <iife@L531-624>` (L531) - serialization, encode/decode, lookup/decoder shim
        - `jt > <callback@L594c19>` (L594) - encode/decode
        - `jt > <callback@L595c19>` (L595) - encode/decode
        - `jt > <callback@L592c19>` (L592) - serialization
        - `jt > <callback@L593c19>` (L593) - serialization
        - `jt > <callback@L611-620>` (L611) - lookup/decoder shim
          - `Ct` (L458)
          - `jt > <callback@L615-617>` (L615)
          - `jt > <callback@L617-619>` (L617)
        - `jt > <callback@L535c18>` (L535)
          - `Tt` (L630) - bit mixing (unrecognised algorithm)
            - `t` (L655)
        - `jt > <callback@L536c18>` (L536)
        - `jt > <callback@L537-545>` (L537)
        - `jt > <callback@L546-554>` (L546)
        - `jt > <callback@L555c19>` (L555)
        - `jt > <callback@L556-561>` (L556)
        - `jt > <callback@L562c18>` (L562)
        - `jt > <callback@L563c18>` (L563)
        - `jt > <callback@L563c50>` (L563)
        - `jt > <callback@L564-579>` (L564)
          - `r` (L846)
            - `r > <anonymous@L847-853>` (L847)
          - `jt > <callback@L567c41>` (L567)
          - `jt > <callback@L569-571>` (L569)
          - `jt > <callback@L571-573>` (L571)
        - `jt > <callback@L580-587>` (L580)
        - `jt > <callback@L588c18>` (L588)
        - `jt > <callback@L590c18>` (L590)
        - `jt > <callback@L590c78>` (L590)
        - `jt > <callback@L590c116>` (L590)
        - `jt > <callback@L591c18>` (L591)
        - `jt > <callback@L596c19>` (L596)
        - `jt > <callback@L597c19>` (L597)
        - `jt > <callback@L598c19>` (L598)
        - `jt > <callback@L599c18>` (L599)
        - `jt > <callback@L600-610>` (L600)

### t.getCookies

Entry at line 920 - function with no in-file caller.

- `t.getCookies` (L920) - persistence
  - `f` (L32) - lookup/decoder shim
    - `s` (L8)
    - `s` (L10)
  - `f` (L34) - lookup/decoder shim
  - `u` (L901)

### Pt.serialize

Entry at line 748 - function with no in-file caller.

- `Pt.serialize` (L748) - validation/error path

## Key functions

The 15 most important of 220 functions, ranked by importance. xray.json details 25 of them; this report prints 15. The rest are in `structure.json` and answerable with `xq find` / `xq show`.

### on

Lines 1102-1126, `async on(t, n)`

- **network transport** (high)
  - performs fetch
  - target Zt + "req"

Reads: `Date.now`

Calls: `fetch`, `rn`, `Date.now`

### _.getConfig

Lines 316-319, `getConfig()`

- **environment fingerprinting** (high)
  - reads 10 browser properties: navigator.userAgent, document.scripts, document.documentElement.getAttribute, document.documentElement, navigator.language, navigator.languages, performance.now, location.search

Reads: `navigator.userAgent`, `Array.from`, `document.scripts`, `document.documentElement.getAttribute`, `document.documentElement`, `navigator.language`, `navigator.languages`, `Object.keys`, `performance.now`, `location.search`

Calls: `new Date`, `j`, `Array.from`, `document.documentElement.getAttribute`, `T`, `Object.keys`, `performance.now`, `new URLSearchParams`

### jt

Lines 528-629, `jt(t)`

- **serialization** (low) - inherited from `jt > <callback@L529-628>`
  - uses JSON.parse
- **encode/decode** (high) - inherited from `jt > <callback@L529-628>`
  - base64 primitives: atob, base64-decode
- **lookup/decoder shim** (low) - inherited from `jt > <callback@L529-628>`
  - small indexed lookup: returns Ct()["catch"](t => { vt.set(n, "" + t); })["finally"](() => { vt.set(K, o); })

Calls: `At`

### _._runCheck > <iife@L235-248>

Lines 235-248, `iife(t)`

- **hash/digest** (high)
  - magic constants match FNV-1a 32-bit, murmur3 fmix32
  - loop over input

Reads: `Math.imul`

Calls: `t.charCodeAt`, `Math.imul`

### E

Lines 334-342, `E(t)`

- **encode/decode** (high)
  - base64 primitives: base64-encode, btoa
- **serialization** (low)
  - uses JSON.stringify

Reads: `JSON.stringify`, `TextEncoder`, `String.fromCharCode`

Calls: `JSON.stringify`, `btoa`, `String.fromCharCode`, `new TextEncoder`, `unescape`, `encodeURIComponent`

### jt > <callback@L529-628>

Lines 529-628, `async callback()`

- **serialization** (low) - inherited from `jt > <iife@L531-624>`
  - uses JSON.parse
- **encode/decode** (high) - inherited from `jt > <iife@L531-624>`
  - base64 primitives: atob, base64-decode
- **lookup/decoder shim** (low) - inherited from `jt > <iife@L531-624>`
  - small indexed lookup: returns Ct()["catch"](t => { vt.set(n, "" + t); })["finally"](() => { vt.set(K, o); })

Calls: `vt.set`

### jt > <iife@L531-624>

Lines 531-624, `iife()`

- **serialization** (low) - inherited from `jt > <callback@L592c19>`
  - uses JSON.parse
- **encode/decode** (high) - inherited from `jt > <callback@L594c19>`
  - base64 primitives: atob, base64-decode
- **lookup/decoder shim** (low) - inherited from `jt > <callback@L611-620>`
  - small indexed lookup: returns Ct()["catch"](t => { vt.set(n, "" + t); })["finally"](() => { vt.set(K, o); })

Calls: `vt.clear`, `vt.set`

### A

Lines 106-129, `A(t, n, e)`

- **bit mixing (unrecognised algorithm)** (low)
  - 32-bit operators & |
- **cryptography (platform)** (high) - inherited from `A > <iife@L111-120>`
  - calls crypto.getRandomValues
- **lookup/decoder shim** (low) - inherited from `A > <iife@L126-128>`
  - small indexed lookup: returns (i[t[n + 0]] + i[t[n + 1]] + i[t[n + 2]] + i[t[n + 3]] + "-" + i[t[n + 4]] + i[t

Calls: `y.randomUUID`, `new Error`

### t.setCookie

Lines 959-1001, `t.setCookie(t, n, r)`

- **persistence** (high)
  - storage ops: document.cookie
- **lookup/decoder shim** (low) - inherited from `t.setCookie > <callback@L995-998>`
  - small indexed lookup: returns t.concat("".concat(n[0], "=").concat(n[1], ";"))

Reads: `document.cookie`, `Array.isArray`, `Object.entries`

Calls: `c`, `a`, `i`, `u`, `l.getHeader`, `Array.isArray`, `String`, `l.setHeader`, `h.concat`, `Object.entries`

### Ot

Lines 469-521, `Ot(t)`

- **encode/decode** (high) - inherited from `Ot > <callback@L470-520>`
  - base64 primitives: atob, base64-decode, base64-encode, btoa
- **serialization** (low) - inherited from `Ot > <callback@L470-520>`
  - uses JSON.parse

Calls: `At`

### Ot > <callback@L470-520>

Lines 470-520, `callback(n, e)`

- **encode/decode** (high)
  - base64 primitives: atob, base64-decode, base64-encode, btoa
- **serialization** (low)
  - uses JSON.parse

Reads: `JSON.parse`

Calls: `setTimeout`, `vt.set`, `JSON.parse`, `Tt`, `atob`, `vt.get`, `Ct`, `n`, `btoa`

### _._runCheck

Lines 230-254, `_runCheck(t, n, e, r, o)`

- **hash/digest** (high) - inherited from `_._runCheck > <iife@L235-248>`
  - magic constants match FNV-1a 32-bit, murmur3 fmix32
  - loop over input

Reads: `Math.round`, `performance.now`

Calls: `Math.round`, `performance.now`, `E`, `s.substring`

### t.getCookies

Lines 920-943, `t.getCookies(t)`

- **persistence** (high)
  - storage ops: document.cookie

Reads: `document.cookie`, `document.cookie.split`

Calls: `u`, `document.cookie.split`, `i.[computed].split`, `f.slice`

### A > <iife@L111-120>

Lines 111-120, `iife()`

- **cryptography (platform)** (high)
  - calls crypto.getRandomValues

Reads: `crypto.getRandomValues`, `crypto.getRandomValues.bind`

Calls: `new Error`, `crypto.getRandomValues.bind`, `l`

### Ot > <callback@L477-482>

Lines 477-482, `callback(t)`

- **encode/decode** (high)
  - base64 primitives: base64-encode, btoa

Calls: `n`, `btoa`

## Reimplementation notes

### Algorithms

**_._runCheck > <iife@L235-248>** at lines 235-248: FNV-1a 32-bit, murmur3 fmix32

32-bit multiply style: **imul** - Math.imul(a, b) -- an exact 32-bit product. Port as (a * b) & 0xFFFFFFFF in Python, or uint32 multiply in Go/Rust.

Constants: 2166136261, 16777619, 2246822507, 3266489909

Returns `(e >>> 0).toString(16).padStart(8, "0")`

FNV-1a 32-bit in Python:

```python
h = 2166136261
for ch in data:
    h ^= ord(ch)
    h = (h * 16777619) & 0xFFFFFFFF
```

murmur3 fmix32 in Python:

```python
def fmix32(h):
    h ^= h >> 16
    h = (h * 2246822507) & 0xFFFFFFFF
    h ^= h >> 13
    h = (h * 3266489909) & 0xFFFFFFFF
    h ^= h >> 16
    return h
```

### Network contracts

- **fetch** in `on` (L1102)
  - url: `Zt + "req"`
  - method: POST
  - body: `rn({ p: n }, t)`
  - credentials: include

### Input surface

Environment values the module reads. A port has to supply these:

- `document.body` - read by ln
- `document.body.appendChild` - read by ln
- `document.cookie` - read by t.getCookies, t.setCookie
- `document.cookie.split` - read by t.getCookies
- `document.createElement` - read by ln
- `document.currentScript` - read by <iife@L1036-1069>
- `document.documentElement` - read by _.getConfig
- `document.documentElement.getAttribute` - read by _.getConfig
- `document.scripts` - read by _.getConfig, jt > <callback@L590c18>
- `location` - read by <iife@L1071-1082>, _.getConfig
- `location.href` - read by <iife@L1071-1082>
- `location.search` - read by _.getConfig
- `navigator.[computed]` - read by T
- `navigator.[computed].toString` - read by T
- `navigator.language` - read by _.getConfig
- `navigator.languages` - read by _.getConfig
- `navigator.userAgent` - read by _.getConfig
- `performance.now` - read by _._generateAnswerAsync, _._generateAnswerSync, _._generateRequirementsTokenAnswerBlocking, _._runCheck
- `performance.timeOrigin` - read by _.getConfig
- `window.__sentinel_init_pending` - read by <iife@L1328-1348>
- `window.__sentinel_token_pending` - read by <iife@L1328-1348>
- `window.addEventListener` - read by <iife@L1-1352>, <iife@L1295-1326>
- `window.requestIdleCallback` - read by _._generateAnswerAsync > <callback@L282-290>
- `window.top` - read by <iife@L1071-1082>

### Pitfalls

- **32-bit integer semantics** - JavaScript bitwise operators truncate to int32 and >>> yields uint32. In Python mask with & 0xFFFFFFFF after every step; in Go/Rust use uint32 types.
- **32-bit multiply style: imul** - Math.imul(a, b) -- an exact 32-bit product. Port as (a * b) & 0xFFFFFFFF in Python, or uint32 multiply in Go/Rust.
- **request shape is part of the contract** - Header order, credentials mode and exact body encoding are often validated server-side. Copy them from the contract rather than assuming defaults.
- **environment values are inputs, not constants** - The listed browser properties feed the algorithm. A port must supply plausible values with matching types and formatting, since they change the output.

## Keyword anchors

Textual matches from the anchor pass, useful as a cross-check on the AST findings above.

- **fingerprinting**: navigator_probe, timing_probe
- **hashing/crypto**: btoa_atob, charcode_loop, crypto_subtle, fnv_offset_basis, fnv_prime, unsigned_shift, xor_assign
- **network**: fetch_call, url_literal
- **serialization**: json_parse, json_stringify
- **storage/identity**: cookie_access, token_prefix

## Reading this report

- Call edges are resolved by name, so a shadowed or reassigned identifier can point at the wrong function. Verify a flow against the source lines before relying on it.
- Roles are inferred from AST facts listed under each role as evidence. Treat confidence "low" and "none" as a lead, not a finding.
- Anonymous functions are attributed to the enclosing function by line containment, which is exact, but their call sites may be indirect.
- functions[] holds the 25 most important of 220 functions, so 195 are not detailed here. They are not absent from the analysis: structure.json has all of them, and "xq find" / "xq show" name and print any of them (marked ~, meaning no published role). See summary.functions_detailed.

The machine-readable form of everything above is in `xray.json`, and the raw AST facts are in `structure.json`.
