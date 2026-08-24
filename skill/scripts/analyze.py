#!/usr/bin/env python3
"""Structural analysis of (preferably deobfuscated) JavaScript.

Finds anchor hits with line numbers, extracts whole enclosing functions via
brace matching, and classifies crypto / network / token-assembly behaviour.
"""
import argparse
import bisect
import json
import os
import re
import sys

BACKTICK = chr(96)
QUOTES = "\"'" + BACKTICK

# label -> (pattern, is_regex)
DEFAULT_ANCHORS = [
    ("fnv_offset_basis", r"2166136261", True),
    ("fnv_prime", r"16777619", True),
    ("md5_const", r"1732584193|0x67452301", True),
    ("sha256_const", r"1779033703|0x6a09e667", True),
    ("crc32_poly", r"3988292384|0xedb88320", True),
    ("base64_alphabet", r"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789", False),
    ("charcode_loop", r"charCodeAt\s*\(", True),
    ("xor_assign", r"\^=", True),
    ("unsigned_shift", r">>>\s*0", True),
    ("fetch_call", r"\bfetch\s*\(", True),
    ("xhr", r"XMLHttpRequest", True),
    ("websocket", r"new\s+WebSocket", True),
    ("json_stringify", r"JSON\.stringify", True),
    ("json_parse", r"JSON\.parse", True),
    ("btoa_atob", r"\b(?:btoa|atob)\s*\(", True),
    ("crypto_subtle", r"crypto\.subtle|getRandomValues", True),
    ("navigator_probe", r"navigator\.(?:userAgent|platform|language|hardwareConcurrency|webdriver|plugins)", True),
    ("screen_probe", r"screen\.(?:width|height|colorDepth)", True),
    ("timing_probe", r"performance\.now|Date\.now", True),
    ("canvas_fp", r"toDataURL|getImageData|createOscillator", True),
    ("webgl_fp", r"WEBGL_debug_renderer_info|getSupportedExtensions", True),
    ("eval_like", r"\beval\s*\(|new\s+Function\s*\(", True),
    ("debugger_trap", r"\bdebugger\b", True),
    ("cookie_access", r"document\.cookie", True),
    ("storage_access", r"localStorage|sessionStorage|indexedDB", True),
    ("token_prefix", r"gAAAAA[A-Z]", True),
    ("auth_header", r"[Aa]uthorization|[Bb]earer\s", True),
    ("api_path", r"[\"'](?:/[A-Za-z0-9_.\-]+){2,}[\"']", True),
    ("url_literal", r"https?://[A-Za-z0-9._~:/?#\[\]@!$&'()*+,;=%-]+", True),
]

CATEGORIES = {
    "hashing/crypto": ["fnv_offset_basis", "fnv_prime", "md5_const", "sha256_const",
                       "crc32_poly", "charcode_loop", "xor_assign", "unsigned_shift",
                       "crypto_subtle", "base64_alphabet", "btoa_atob"],
    "network": ["fetch_call", "xhr", "websocket", "api_path", "url_literal", "auth_header"],
    "fingerprinting": ["navigator_probe", "screen_probe", "canvas_fp", "webgl_fp", "timing_probe"],
    "anti-analysis": ["eval_like", "debugger_trap"],
    "storage/identity": ["cookie_access", "storage_access", "token_prefix"],
    "serialization": ["json_stringify", "json_parse"],
}

# Control-flow keywords that look like calls but are not functions.
NOT_FUNCTIONS = {
    "if", "for", "while", "switch", "catch", "with", "do", "else", "try",
    "return", "typeof", "void", "delete", "new", "in", "of", "case", "function",
}

FN_PATTERNS = [
    re.compile(r"(?:async\s+)?function\s*\*?\s*([A-Za-z_$][\w$]*)?\s*\(", re.M),
    re.compile(r"(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*(?:async\s*)?(?:function|\([^)]*\)\s*=>)", re.M),
    re.compile(r"^\s*(?:async\s+|static\s+|get\s+|set\s+)*([A-Za-z_$][\w$]*)\s*\([^)]*\)\s*\{", re.M),
]


def line_index(src):
    return [m.start() for m in re.finditer("\n", src)]


def offset_to_line(nl_offsets, off):
    return bisect.bisect_right(nl_offsets, off) + 1


def match_block(src, brace_pos, max_len=20000):
    """Brace-match forward from an opening brace, skipping strings and comments."""
    depth = 0
    i = brace_pos
    limit = min(len(src), brace_pos + max_len)
    while i < limit:
        c = src[i]
        if c in QUOTES:
            quote = c
            i += 1
            while i < limit:
                if src[i] == "\\":
                    i += 2
                    continue
                if src[i] == quote:
                    break
                if quote == BACKTICK and src[i] == "$" and i + 1 < limit and src[i + 1] == "{":
                    d = 1
                    i += 2
                    while i < limit and d:
                        if src[i] == "{":
                            d += 1
                        elif src[i] == "}":
                            d -= 1
                        i += 1
                    continue
                i += 1
            i += 1
            continue
        if c == "/" and i + 1 < limit:
            nxt = src[i + 1]
            if nxt == "/":
                j = src.find("\n", i)
                i = limit if j == -1 else j + 1
                continue
            if nxt == "*":
                j = src.find("*/", i)
                i = limit if j == -1 else j + 2
                continue
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return i + 1
        i += 1
    return None


def enclosing_function(src, pos, nl_offsets):
    """Smallest function-like block containing pos."""
    best = None
    window_start = max(0, pos - 12000)
    window = src[window_start:pos + 1]
    for pat in FN_PATTERNS:
        for m in pat.finditer(window):
            if (m.group(1) or "") in NOT_FUNCTIONS:
                continue
            start = window_start + m.start()
            brace = src.find("{", window_start + m.end() - 1)
            if brace == -1 or brace > pos:
                continue
            end = match_block(src, brace)
            if end is None or end <= pos:
                continue
            size = end - start
            if best is None or size < best["size"]:
                best = {"name": m.group(1) or "(anonymous)", "start": start, "end": end, "size": size}
    if best:
        best["start_line"] = offset_to_line(nl_offsets, best["start"])
        best["end_line"] = offset_to_line(nl_offsets, best["end"])
        best["code"] = src[best["start"]:best["end"]]
    return best


def load_anchors(path):
    if not path:
        return DEFAULT_ANCHORS
    data = json.load(open(path))
    out = []
    for item in data:
        if isinstance(item, dict):
            out.append((item["label"], item["pattern"], bool(item.get("regex", True))))
        else:
            out.append((item[0], item[1], bool(item[2]) if len(item) > 2 else True))
    return out


def main():
    ap = argparse.ArgumentParser(description="structural JS analysis")
    ap.add_argument("input")
    ap.add_argument("output", help="analysis json path")
    ap.add_argument("--anchors", help="custom anchors json (list of {label,pattern,regex})")
    ap.add_argument("--max-hits", type=int, default=8)
    ap.add_argument("--max-blocks", type=int, default=12)
    ap.add_argument("--context", type=int, default=160)
    args = ap.parse_args()

    src = open(args.input, encoding="utf-8", errors="replace").read()
    nl = line_index(src)
    anchors = load_anchors(args.anchors)

    hits = {}
    hit_positions = []
    for label, pattern, is_regex in anchors:
        try:
            matches = list(re.finditer(pattern if is_regex else re.escape(pattern), src))
        except re.error as exc:
            hits[label] = {"error": "bad pattern: %s" % exc, "hits": []}
            continue
        if not matches:
            continue
        found = []
        for m in matches[:args.max_hits]:
            start = max(0, m.start() - args.context // 2)
            snippet = src[start:m.start() + args.context // 2]
            found.append({
                "line": offset_to_line(nl, m.start()),
                "char": m.start(),
                "match": m.group(0)[:80],
                "context": re.sub(r"\s+", " ", snippet).strip(),
            })
            hit_positions.append((label, m.start()))
        hits[label] = {"count": len(matches), "hits": found}

    blocks = {}
    for label, pos in hit_positions:
        fn = enclosing_function(src, pos, nl)
        if not fn:
            continue
        entry = blocks.setdefault((fn["start"], fn["end"]), {
            "name": fn["name"],
            "start_line": fn["start_line"],
            "end_line": fn["end_line"],
            "bytes": fn["size"],
            "code": fn["code"],
            "labels": set(),
        })
        entry["labels"].add(label)

    ranked = sorted(blocks.values(), key=lambda b: (-len(b["labels"]), b["bytes"]))
    top = []
    for b in ranked[:args.max_blocks]:
        labels = sorted(b["labels"])
        cats = sorted({c for c, ls in CATEGORIES.items() if set(ls) & set(labels)})
        code = b["code"] if b["bytes"] <= 6000 else b["code"][:6000] + "\n/* ...truncated... */"
        top.append({
            "name": b["name"],
            "start_line": b["start_line"],
            "end_line": b["end_line"],
            "bytes": b["bytes"],
            "labels": labels,
            "categories": cats,
            "code": code,
        })

    present = set(hits)
    categories = {c: sorted(present & set(ls)) for c, ls in CATEGORIES.items() if present & set(ls)}
    urls = sorted({h["match"] for h in hits.get("url_literal", {}).get("hits", [])})
    paths = sorted({h["match"].strip("\"'") for h in hits.get("api_path", {}).get("hits", [])})

    result = {
        "file": os.path.abspath(args.input),
        "bytes": len(src),
        "lines": len(nl) + 1,
        "anchor_hits": hits,
        "categories": categories,
        "key_blocks": top,
        "endpoints": {"urls": urls[:20], "paths": paths[:20]},
    }
    open(args.output, "w").write(json.dumps(result, indent=2, ensure_ascii=False))
    print(json.dumps({
        "anchors_hit": len(hits),
        "categories": list(categories),
        "key_blocks": [[b["name"], b["start_line"], b["categories"]] for b in top[:6]],
    }, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
