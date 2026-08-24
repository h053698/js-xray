#!/usr/bin/env python3
"""Render a readable Markdown report from analyze.py output."""
import argparse
import json
import os

FENCE = chr(96) * 3
BT = chr(96)

# anchor label -> (what it means, how to port it to Python)
PORT_HINTS = {
    "fnv_offset_basis": (
        "FNV-1a 32-bit offset basis (2166136261).",
        "h = 2166136261\nfor ch in data:\n    h ^= ord(ch)\n    h = (h * 16777619) & 0xFFFFFFFF",
    ),
    "fnv_prime": (
        "FNV-1a 32-bit prime (16777619).",
        "h = (h * 16777619) & 0xFFFFFFFF  # JS: (h * 16777619) >>> 0",
    ),
    "md5_const": ("MD5 initial state constant.", "import hashlib\nhashlib.md5(data).hexdigest()"),
    "sha256_const": ("SHA-256 initial state constant.", "import hashlib\nhashlib.sha256(data).hexdigest()"),
    "crc32_poly": ("CRC32 reversed polynomial.", "import zlib\nzlib.crc32(data) & 0xFFFFFFFF"),
    "unsigned_shift": (
        "JS coerces to uint32 with the >>> 0 idiom.",
        "value & 0xFFFFFFFF  # every JS >>> 0 becomes a 32-bit mask",
    ),
    "xor_assign": ("In-place XOR, typical of hash mixing loops.", "h ^= ord(ch)"),
    "charcode_loop": (
        "Per-character loop over the input string.",
        "for ch in text:\n    code = ord(ch)  # JS: text.charCodeAt(i)",
    ),
    "base64_alphabet": (
        "Custom or standard base64 alphabet.",
        "import base64\nbase64.b64encode(raw).decode()\n# custom alphabet: raw.translate(str.maketrans(STD, CUSTOM))",
    ),
    "btoa_atob": (
        "btoa/atob base64 helpers.",
        "import base64\nbase64.b64encode(s.encode('latin-1')).decode()  # btoa\nbase64.b64decode(s).decode('latin-1')          # atob",
    ),
    "crypto_subtle": (
        "WebCrypto digest or CSPRNG.",
        "import hashlib, secrets\nhashlib.sha256(data).digest()\nsecrets.token_bytes(16)  # getRandomValues",
    ),
    "fetch_call": (
        "Outbound HTTP request; replicate method, headers and body exactly.",
        "import requests\nresp = requests.post(url, headers=headers, json=body, timeout=30)",
    ),
    "json_stringify": (
        "JSON body construction. Key order and separators affect any hash over it.",
        "import json\njson.dumps(body, separators=(',', ':'))  # match JS JSON.stringify exactly",
    ),
    "json_parse": ("Response parsing.", "data = resp.json()"),
    "timing_probe": (
        "Timing/clock values folded into the payload.",
        "import time\nint(time.time() * 1000)     # Date.now()\ntime.perf_counter() * 1000  # performance.now()",
    ),
    "navigator_probe": (
        "Browser fingerprint fields; must be spoofed consistently.",
        'ua = "Mozilla/5.0 (...) Chrome/... Safari/537.36"  # keep stable per identity',
    ),
    "screen_probe": (
        "Screen metrics in the fingerprint.",
        'screen = {"width": 1920, "height": 1080, "colorDepth": 24}',
    ),
    "canvas_fp": (
        "Canvas/audio fingerprint; usually must be replayed from a real browser.",
        "# capture once from a real browser and reuse the value",
    ),
    "webgl_fp": (
        "WebGL renderer strings.",
        'webgl = {"vendor": "Google Inc. (Apple)", "renderer": "ANGLE (Apple, Apple M1, ...)"}',
    ),
    "token_prefix": (
        "Versioned token prefix; the suffix is normally base64 of a JSON array.",
        "import base64, json\ntoken = prefix + base64.b64encode(json.dumps(payload).encode()).decode()",
    ),
    "storage_access": (
        "Persisted identity between runs.",
        "# persist the same value across requests in your own store",
    ),
    "cookie_access": ("Reads/writes cookies.", "session = requests.Session()  # keeps the cookie jar"),
    "auth_header": ("Authorization header.", 'headers["authorization"] = "Bearer " + access_token'),
    "eval_like": (
        "Dynamic code execution: possible anti-analysis or dynamic dispatch.",
        "# resolve statically; do not execute untrusted code",
    ),
    "debugger_trap": ("Anti-debugging trap.", "# ignore for a static port"),
}

CATEGORY_NOTES = {
    "hashing/crypto": "Deterministic transforms. Port these first; they are testable against known inputs.",
    "network": "Defines the request contract: URL, method, headers, body shape.",
    "fingerprinting": "Environment values collected from the browser. Must stay consistent per identity.",
    "anti-analysis": "Defensive code. Usually skippable for a static port, but confirm it is not load-bearing.",
    "storage/identity": "State that persists across requests.",
    "serialization": "Payload encoding. Byte-exact formatting matters when the result is hashed or signed.",
}


def fmt_int(n):
    return "{:,}".format(n)


def code(s):
    return BT + str(s) + BT


def main():
    ap = argparse.ArgumentParser(description="render js-xray markdown report")
    ap.add_argument("analysis", help="analysis json from analyze.py")
    ap.add_argument("output", help="report.md path")
    ap.add_argument("--meta", help="webcrack meta json")
    ap.add_argument("--source", help="original input path for display")
    ap.add_argument("--clean", help="deobfuscated js path for display")
    args = ap.parse_args()

    data = json.load(open(args.analysis))
    meta = json.load(open(args.meta)) if args.meta and os.path.isfile(args.meta) else {}

    out = []
    add = out.append
    name = os.path.basename(args.source or data.get("file", "input.js"))
    add("# js-xray report: %s" % name)
    add("")

    cats = data.get("categories", {})
    add("## Summary")
    add("")
    if cats:
        add("This file shows evidence of: **%s**." % ", ".join(cats))
    else:
        add("No known behavioural anchors matched. The file may be plain, packed differently, "
            "or need custom anchors.")
    add("")
    add("| field | value |")
    add("| --- | --- |")
    if args.source and os.path.isfile(args.source):
        add("| input | %s (%s bytes) |" % (code(args.source), fmt_int(os.path.getsize(args.source))))
    if meta.get("ok"):
        add("| string array | %s |" % meta.get("string_array", "not detected"))
        add("| rotated | %s |" % meta.get("rotate", "no"))
        add("| decoders | %s |" % meta.get("decoders", "none"))
        add("| node used | %s |" % meta.get("node_version", "?"))
    elif meta:
        add("| deobfuscation | FAILED - %s |" % meta.get("error", "unknown"))
    add("| analyzed source | %s lines, %s bytes |" % (fmt_int(data.get("lines", 0)),
                                                      fmt_int(data.get("bytes", 0))))
    add("| anchors matched | %d |" % len(data.get("anchor_hits", {})))
    add("| key blocks | %d |" % len(data.get("key_blocks", [])))
    add("")

    if meta and not meta.get("ok"):
        add("> Deobfuscation did not run, so identifiers below are still obfuscated.")
        add("> Fix: install a compatible Node (%s) then %s." % (code("fnm install 24"), code("bun install")))
        add("")

    eps = data.get("endpoints", {})
    if eps.get("urls") or eps.get("paths"):
        add("## Endpoints")
        add("")
        for u in eps.get("urls", []):
            add("- %s" % code(u))
        for p in eps.get("paths", []):
            add("- %s" % code(p))
        add("")

    if cats:
        add("## Behaviour breakdown")
        add("")
        for cat, labels in cats.items():
            add("### %s" % cat)
            add("")
            note = CATEGORY_NOTES.get(cat)
            if note:
                add(note)
                add("")
            for lab in labels:
                info = data["anchor_hits"].get(lab, {})
                meaning = PORT_HINTS.get(lab, ("", ""))[0]
                line = "- %s x%d" % (code(lab), info.get("count", 0))
                if meaning:
                    line += " - " + meaning
                add(line)
            add("")

    blocks = data.get("key_blocks", [])
    if blocks:
        add("## Key code blocks")
        add("")
        add("Ranked by how many distinct anchors each function contains.")
        add("")
        for i, b in enumerate(blocks, 1):
            add("### %d. %s - lines %d-%d" % (i, code(b["name"] + "()"), b["start_line"], b["end_line"]))
            add("")
            add("Signals: %s" % ", ".join(code(l) for l in b["labels"]))
            add("")
            add(FENCE + "javascript")
            add(b["code"])
            add(FENCE)
            add("")

    hit_labels = [l for l in data.get("anchor_hits", {}) if l in PORT_HINTS]
    if hit_labels:
        add("## Python porting guide")
        add("")
        add("Only the anchors actually found in this file are listed.")
        add("")
        for lab in hit_labels:
            meaning, snippet = PORT_HINTS[lab]
            add("### %s" % lab)
            add("")
            add(meaning)
            add("")
            add(FENCE + "python")
            add(snippet)
            add(FENCE)
            add("")
        add("### Porting checklist")
        add("")
        add("1. Reproduce the hash on a fixed input and compare against the browser console.")
        add("2. Match JSON.stringify byte-for-byte (no spaces, insertion-ordered keys) before hashing.")
        add("3. Mask every JS >>> 0 or | 0 with & 0xFFFFFFFF to emulate uint32 wrapping.")
        add("4. Keep fingerprint values stable per identity; randomizing per request is a strong signal.")
        add("5. Copy request headers exactly, including order-sensitive custom headers.")
        add("")

    add("## Suggested next steps")
    add("")
    if args.clean:
        add("- Read the cleaned source: %s" % code(args.clean))
    add("- Re-run with custom anchors to chase target-specific identifiers:")
    add("  %s" % code("python3 scripts/xray.py <input.js> --anchors my_anchors.json"))
    if not blocks:
        add("- No key blocks were extracted; the file may be a bundle. "
            "Try unpacking modules or supplying custom anchors.")
    add("")

    text = "\n".join(out) + "\n"
    open(args.output, "w").write(text)
    print("report -> %s (%s bytes)" % (args.output, fmt_int(len(text))))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
