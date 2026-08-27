#!/usr/bin/env python3
"""Render the explanation JSON as Markdown for a human reader.

This is a view, not an analysis: everything here comes from xray.json. The order
is deliberate -- what the module does, then the flows, then the porting details --
because a reader needs the shape of the thing before the constants mean anything.

Confidence is printed next to every inferred role. An inference that reads like a
fact is worse than no inference, since it is the one a reader will not check.
"""
import argparse
import json
import os

FENCE = chr(96) * 3
BT = chr(96)

# Algorithm family -> a Python snippet that reproduces it correctly. Keyed by the
# family names structure.mjs emits, so a new constant only needs a new entry here.
# Porting snippets keyed by (algorithm family, multiply style). JavaScript has two
# different 32-bit multiplies and they produce different digests, so one snippet
# per family would be wrong half the time:
#   Math.imul(a, b)  -> exact 32-bit product
#   a * b >>> 0      -> float64 product, then truncated; low bits already lost
INT32_HELPER = (
    "def to_int32(h):\n"
    "    h &= 0xFFFFFFFF\n"
    "    return h - 0x100000000 if h >= 0x80000000 else h"
)

# The other half of a correct port, and the one that hides longer: what a single
# iteration of the loop consumes. JS charCodeAt(i) yields a UTF-16 code unit, so
# an astral character (emoji, rare CJK, most symbols above U+FFFF) is two
# iterations of two surrogate halves. Python's ord(ch) yields one code point, so
# a snippet written with ord() agrees on the whole BMP -- every ASCII and Hangul
# and CJK test passes -- and returns a different digest the first time an emoji
# reaches it. A snippet that survives only ASCII tests is the failure this table
# exists to prevent, so the character feed is chosen the same way the multiply
# is: from what the source actually does, and stated when it is not known.
CODE_UNITS_HELPER = (
    "def code_units(s):\n"
    "    # What JS charCodeAt(i) returns: UTF-16 code units, so a character above\n"
    "    # U+FFFF arrives as its two surrogate halves. ord(ch) would yield one\n"
    "    # code point instead and diverge there -- and only there.\n"
    "    for ch in s:\n"
    "        cp = ord(ch)\n"
    "        if cp > 0xFFFF:\n"
    "            cp -= 0x10000\n"
    "            yield 0xD800 + (cp >> 10)\n"
    "            yield 0xDC00 + (cp & 0x3FF)\n"
    "        else:\n"
    "            yield cp"
)

# Per char_source: the expression that feeds the loop, whether CODE_UNITS_HELPER
# has to come with it, and the comment that says why -- or, when explain.py found
# no evidence, what the snippet is assuming and how to check it.
CHAR_FEEDS = {
    "utf16-code-units": (
        "code_units(data)", True,
        "# The source reads characters with charCodeAt, so the loop consumes\n"
        "# UTF-16 code units. data is a str.",
    ),
    "code-points": (
        "(ord(ch) for ch in data)", False,
        "# The source reads codePointAt, so one Python character is one iteration\n"
        "# and ord() is the right unit. data is a str.",
    ),
    "bytes": (
        'data.encode("utf-8")', False,
        "# The source encodes to bytes (TextEncoder / Buffer) before hashing, so\n"
        "# the loop consumes UTF-8 bytes, not characters. Check the encoding in\n"
        "# clean.js if the source picked something other than UTF-8.",
    ),
    "mixed": (
        "code_units(data)", True,
        "# ASSUMPTION: charCodeAt feeds this loop. Both charCodeAt and a byte\n"
        "# encoder appear in this function, so which one reaches the hash is not\n"
        "# decidable from the AST facts -- read the loop in clean.js. If it hashes\n"
        "# bytes, feed data.encode(\"utf-8\") instead; the digests differ on any\n"
        "# non-ASCII input.",
    ),
    None: (
        "code_units(data)", True,
        "# ASSUMPTION: charCodeAt feeds this loop (UTF-16 code units), which is\n"
        "# what most hand-rolled JS hashes do. No charCodeAt / codePointAt /\n"
        "# TextEncoder call was recorded for this function, so this is not\n"
        "# evidence -- check the loop in clean.js. If it hashes bytes, feed\n"
        "# data.encode(\"utf-8\"); if it reads codePointAt, feed ord(ch) directly.\n"
        "# All three agree on ASCII and disagree above it.",
    ),
}

# A {feed} in a snippet marks it as character-driven: port_snippet fills it from
# CHAR_FEEDS and prepends the helper and the note that go with the choice.
PORT_SNIPPETS = {
    ("FNV-1a 32-bit", "imul"): (
        "h = 2166136261\n"
        "for c in {feed}:\n"
        "    h ^= c\n"
        "    h = (h * 16777619) & 0xFFFFFFFF"
    ),
    # JS: h = h * 16777619 >>> 0. The xor leaves a signed int32, and the float64
    # product of that with the prime overflows 2**53, so the rounding is part of
    # the algorithm. Verified against Node: masking an exact product diverges.
    ("FNV-1a 32-bit", "truncated-float"): (
        INT32_HELPER + "\n\n"
        "h = 2166136261\n"
        "for c in {feed}:\n"
        "    h = (h ^ c) & 0xFFFFFFFF\n"
        "    h = int(float(to_int32(h)) * 16777619) & 0xFFFFFFFF"
    ),
    ("murmur3 fmix32", "imul"): (
        "def fmix32(h):\n"
        "    h ^= h >> 16\n"
        "    h = (h * 2246822507) & 0xFFFFFFFF\n"
        "    h ^= h >> 13\n"
        "    h = (h * 3266489909) & 0xFFFFFFFF\n"
        "    h ^= h >> 16\n"
        "    return h"
    ),
    ("murmur3 fmix32", "truncated-float"): (
        INT32_HELPER + "\n\n"
        "def fmix32(h):\n"
        "    h = (h ^ (h >> 16)) & 0xFFFFFFFF\n"
        "    h = int(float(to_int32(h)) * 2246822507) & 0xFFFFFFFF\n"
        "    h = (h ^ (h >> 13)) & 0xFFFFFFFF\n"
        "    h = int(float(to_int32(h)) * 3266489909) & 0xFFFFFFFF\n"
        "    return (h ^ (h >> 16)) & 0xFFFFFFFF"
    ),
    ("MD5", None): "import hashlib\nhashlib.md5(data).hexdigest()",
    ("SHA-256", None): "import hashlib\nhashlib.sha256(data).hexdigest()",
    ("CRC-32", None): "import zlib\nzlib.crc32(data) & 0xFFFFFFFF",
    # djb2 is defined over bytes in its C original (unsigned char *str) and is
    # almost always written over charCodeAt in JS, so the unit genuinely depends
    # on the source rather than on the algorithm. It takes {feed} for that
    # reason: with evidence the snippet follows the source, and without evidence
    # it says which of the two it picked.
    ("djb2", None): "h = 5381\nfor c in {feed}:\n    h = ((h * 33) + c) & 0xFFFFFFFF",
    ("LCG", None): "state = (state * 1664525 + 1013904223) & 0xFFFFFFFF",
}


def port_snippet(family, style, char_source=None):
    """Snippet for a family, matched to how the source multiplies.

    Returns None when the style is unknown or mixed rather than guessing: a wrong
    snippet is worse than none, because it looks authoritative and fails only on
    longer inputs.

    char_source is explain.py's finding about what one iteration consumes. For a
    character-driven family it selects the feed; unlike the multiply style it does
    not withhold the snippet when unknown, because the loop and the constants are
    still right and the alternative -- no snippet at all -- leaves the reader with
    nothing. What it does instead is name the assumption in the snippet, so the
    one line a reader has to check is in front of them.
    """
    if (family, None) in PORT_SNIPPETS:
        return fill_feed(PORT_SNIPPETS[(family, None)], char_source)
    if style in ("imul", "truncated-float"):
        snippet = PORT_SNIPPETS.get((family, style))
        return fill_feed(snippet, char_source) if snippet else None
    return None


def fill_feed(snippet, char_source):
    """Resolve {feed} in a character-driven snippet, or pass the snippet through."""
    if "{feed}" not in snippet:
        return snippet
    feed, needs_helper, note = CHAR_FEEDS.get(char_source, CHAR_FEEDS[None])
    parts = [note]
    if needs_helper:
        parts.append(CODE_UNITS_HELPER)
    parts.append(snippet.replace("{feed}", feed))
    return "\n\n".join(parts)


CONF_MARK = {"high": "high", "medium": "medium", "low": "low", "none": "unknown"}

# Heading and lead-in per VM verdict. This section is rendered before the summary
# table, because a reader who skims the top of the report and stops has to have
# seen it -- the rest of the document describes an interpreter, not the module.
VM_BANNER = {
    "vm-obfuscated": (
        "## Do not trust the findings below: this file is VM-obfuscated",
        "The original logic was compiled into a bytecode array, and what is left in "
        "the source is the interpreter that executes it. Everything below -- flows, "
        "key functions, reimplementation notes -- describes that interpreter: its "
        "dispatch loop, its registers, its operand decoding. None of it is what this "
        "module does.",
        "The behaviour lives in the bytecode operands, which this pipeline does not "
        "recover. Reading the sections below as the module's behaviour will produce a "
        "confident and wrong description.",
    ),
    "suspected": (
        "## Read with care: this file may be VM-obfuscated",
        "Part of a bytecode-interpreter fingerprint is present, so some of the "
        "functions below are likely interpreter internals rather than the module's "
        "own logic.",
        "Check the signals against the cited lines in the deobfuscated source before "
        "relying on any flow that runs through the dispatch loop.",
    ),
}


def render_vm_warning(vm):
    """The banner for a VM verdict, with its evidence. Empty list when clean."""
    banner = VM_BANNER.get((vm or {}).get("verdict"))
    if not banner:
        return []
    heading, lead, tail = banner
    out = [heading, "", lead, "", tail, ""]
    signals = vm.get("signals") or []
    if signals:
        out.append("Signals detected (score %s/100):" % vm.get("score"))
        out.append("")
        for sig in signals:
            where = " (line %s)" % sig["line"] if sig.get("line") else ""
            out.append("- **%s**%s - %s" % (sig.get("kind"), where, sig.get("detail")))
        out.append("")
    return out


def code(text, lang=""):
    return FENCE + lang + "\n" + text.rstrip("\n") + "\n" + FENCE


def rel(path, base):
    if not path:
        return "-"
    try:
        return os.path.relpath(path, base)
    except ValueError:
        return path


def render_roles(roles):
    """One line per role, with its confidence and the facts behind it."""
    out = []
    for r in roles:
        if r["role"] == "unclassified":
            continue
        tag = CONF_MARK.get(r["confidence"], r["confidence"])
        line = "- **%s** (%s)" % (r["role"], tag)
        if r.get("inherited_from"):
            line += " - inherited from " + BT + r["inherited_from"] + BT
        out.append(line)
        for ev in r.get("evidence", [])[:4]:
            out.append("  - " + ev)
    return out


def render(data, args):
    base = os.path.dirname(os.path.abspath(args.output))
    s = data.get("summary", {})
    L = []

    L.append("# js-xray report")
    L.append("")
    # Before the summary table: see VM_BANNER.
    L.extend(render_vm_warning(data.get("vm_signals")))
    L.append("| | |")
    L.append("|---|---|")
    L.append("| source | " + BT + rel(args.source, base) + BT + " |")
    L.append("| deobfuscated | " + BT + rel(args.clean, base) + BT + " |")
    L.append("| size | %s lines, %s bytes |" % (
        data.get("size", {}).get("lines"), data.get("size", {}).get("bytes")))
    # Both numbers when they differ: the table is the first thing read, and a
    # bare function count next to a shorter "Key functions" list invites the
    # reader to assume the list is the whole file.
    if s.get("functions_omitted"):
        L.append("| functions | %s (%s detailed below, %s omitted by --top) |" % (
            s.get("functions"), s.get("functions_detailed"), s.get("functions_omitted")))
    else:
        L.append("| functions | %s |" % s.get("functions"))
    L.append("| classes | %s |" % s.get("classes"))
    L.append("| entry points | %s |" % s.get("entry_points"))
    d = data.get("deobfuscation") or {}
    if d:
        # Per pass, never as one number. A single "strings inlined: 0" here is
        # exactly what made a successful deobfuscation read as a failed one: it
        # was the second pass's figure, while webcrack had already inlined
        # hundreds in the first. A run predating passes[] is labelled as the one
        # pass it measured rather than presented as a total.
        if "passes" in d:
            L.append("| strings inlined | %s total: %s |" % (
                d.get("strings_inlined_total", 0),
                ", ".join("%s %s" % (p.get("pass"), p.get("strings_inlined", 0))
                          for p in d.get("passes") or []) or "-"))
        else:
            L.append("| strings inlined (second pass only) | %s resolved, %s unresolved |"
                     % (d.get("strings_inlined", 0), d.get("unresolved", 0)))
    L.append("")

    if data.get("error"):
        L.append("> Structure extraction degraded: %s" % data["error"])
        L.append("")

    # ---- what the module does ----
    L.append("## What this module does")
    L.append("")
    roles = s.get("roles") or {}
    named = [(k, v) for k, v in roles.items() if k != "unclassified"]
    if named:
        L.append("Roles found across %d functions:" % s.get("functions", 0))
        L.append("")
        for role, count in named:
            L.append("- %s - %d function(s)" % (role, count))
        unclassified = roles.get("unclassified", 0)
        if unclassified:
            L.append("- %d function(s) had no distinguishing facts, typically "
                     "obfuscation scaffolding and small helpers" % unclassified)
    else:
        L.append("No roles could be inferred from the AST facts.")
    L.append("")

    endpoints = s.get("endpoints") or []
    if endpoints:
        L.append("Endpoints referenced:")
        L.append("")
        for u in endpoints:
            L.append("- " + BT + str(u) + BT)
        L.append("")

    # ---- flows ----
    L.append("## Flows")
    L.append("")
    if not data.get("flows"):
        L.append("No entry point could be identified, so no flow was traced.")
        L.append("")
    for flow in data.get("flows", []):
        entry = flow["entry"]
        L.append("### " + entry["name"])
        L.append("")
        L.append("Entry at line %s - %s." % (entry.get("line"), entry.get("why")))
        L.append("")
        shared = flow.get("also_entered_by") or []
        if shared:
            L.append("The same path is entered by " + ", ".join(
                BT + o["name"] + BT + " (L%s)" % o.get("line") for o in shared) + ".")
            L.append("")
        for step in flow.get("steps", []):
            indent = "  " * step["depth"]
            bits = []
            if step.get("does"):
                bits.append(", ".join(step["does"]))
            if step.get("algorithms"):
                bits.append("algorithms: " + ", ".join(step["algorithms"]))
            if step.get("network"):
                for net in step["network"]:
                    bits.append("%s %s %s" % (net.get("kind", ""),
                                              net.get("method", ""),
                                              net.get("url", "")))
            suffix = (" - " + "; ".join(bits)) if bits else ""
            L.append("%s- " % indent + BT + step["name"] + BT +
                     " (L%s)%s" % (step.get("line"), suffix))
        L.append("")

    # ---- functions ----
    L.append("## Key functions")
    L.append("")
    shown = data.get("functions", [])[:args.max_functions]
    # Two separate truncations reach this list: explain.py published the top
    # --top by importance, and this renderer prints the first --max-functions of
    # those. Both are stated, because a reader cannot tell from the list itself
    # that either happened.
    total_fns = s.get("functions")
    if total_fns and len(shown) < total_fns:
        detailed = s.get("functions_detailed") or len(data.get("functions", []))
        line = ("The %d most important of %d functions, ranked by importance."
                % (len(shown), total_fns))
        if detailed > len(shown):
            line += (" xray.json details %d of them; this report prints %d."
                     % (detailed, len(shown)))
        line += (" The rest are in " + BT + "structure.json" + BT + " and answerable with "
                 + BT + "xq find" + BT + " / " + BT + "xq show" + BT + ".")
        L.append(line)
        L.append("")
    for fn in shown:
        header = "### " + fn["name"]
        if not fn.get("reachable_from_entry"):
            header += " (not reached from any entry point)"
        L.append(header)
        L.append("")
        sig = "%s%s(%s)" % ("async " if fn.get("async") else "",
                            fn.get("raw_name") or fn.get("kind"),
                            ", ".join(fn.get("params", [])))
        L.append("Lines %s-%s, " % tuple(fn["lines"]) + BT + sig + BT)
        L.append("")
        rl = render_roles(fn.get("roles", []))
        if rl:
            L.extend(rl)
            L.append("")
        if fn.get("reads"):
            L.append("Reads: " + ", ".join(BT + r + BT for r in fn["reads"][:10]))
            L.append("")
        if fn.get("calls"):
            L.append("Calls: " + ", ".join(BT + c + BT for c in fn["calls"][:10]))
            L.append("")

    # ---- porting ----
    porting = data.get("porting", {}) or {}
    L.append("## Reimplementation notes")
    L.append("")

    if porting.get("algorithms"):
        L.append("### Algorithms")
        L.append("")
        for algo in porting["algorithms"]:
            L.append("**%s** at lines %s-%s: %s" % (
                algo["function"], algo["lines"][0], algo["lines"][1],
                ", ".join(algo["families"])))
            L.append("")
            if algo.get("multiply_style"):
                L.append("32-bit multiply style: **%s** - %s" % (
                    algo["multiply_style"], algo.get("multiply_note") or ""))
                L.append("")
            # Printed next to the multiply style, because it is the same class of
            # mistake: a per-step detail that agrees on ASCII and changes the
            # digest later. When the facts did not decide it, the reader is told
            # that too -- the snippet below is assuming one of the two.
            if algo.get("char_source"):
                L.append("Character unit: **%s** - %s" % (
                    algo["char_source"], algo.get("char_source_note") or ""))
                L.append("")
            elif algo.get("loops"):
                L.append("Character unit: **not determined** - no charCodeAt, "
                         "codePointAt or byte encoder was recorded for this function, "
                         "so what one iteration consumes has to be read from "
                         + BT + "clean.js" + BT + ". The snippet below states which "
                         "unit it assumed.")
                L.append("")
            if algo.get("constants"):
                L.append("Constants: " + ", ".join(str(c) for c in algo["constants"]))
                L.append("")
            if algo.get("returns"):
                L.append("Returns " + BT + algo["returns"][0] + BT)
                L.append("")
            for family in algo["families"]:
                snippet = port_snippet(family, algo.get("multiply_style"),
                                       algo.get("char_source"))
                if snippet:
                    L.append("%s in Python:" % family)
                    L.append("")
                    L.append(code(snippet, "python"))
                    L.append("")
                elif algo.get("multiply_style") == "mixed":
                    L.append("No snippet for %s: this function mixes Math.imul and "
                             "truncated float multiplies, so it has to be read directly."
                             % family)
                    L.append("")

    if porting.get("network_contracts"):
        L.append("### Network contracts")
        L.append("")
        for net in porting["network_contracts"]:
            L.append("- **%s** in " % net.get("kind", "request") + BT + net["function"] + BT +
                     " (L%s)" % net.get("line"))
            L.append("  - url: " + BT + str(net.get("url")) + BT)
            if net.get("method"):
                L.append("  - method: " + str(net["method"]))
            if net.get("headers"):
                L.append("  - headers: " + ", ".join(str(h) for h in net["headers"]))
            if net.get("body"):
                L.append("  - body: " + BT + str(net["body"]) + BT)
            if net.get("credentials"):
                L.append("  - credentials: " + str(net["credentials"]))
        L.append("")

    if porting.get("inputs"):
        L.append("### Input surface")
        L.append("")
        L.append("Environment values the module reads. A port has to supply these:")
        L.append("")
        for item in porting["inputs"][:30]:
            L.append("- " + BT + item["property"] + BT + " - read by " +
                     ", ".join(item["read_by"]))
        L.append("")

    if porting.get("pitfalls"):
        L.append("### Pitfalls")
        L.append("")
        for p in porting["pitfalls"]:
            L.append("- **%s** - %s" % (p["issue"], p["detail"]))
        L.append("")

    # ---- anchors, when the optional pass ran ----
    if args.analysis and os.path.isfile(args.analysis):
        try:
            with open(args.analysis, encoding="utf-8") as fh:
                analysis = json.load(fh)
        except Exception:
            analysis = None
        if analysis and analysis.get("categories"):
            L.append("## Keyword anchors")
            L.append("")
            L.append("Textual matches from the anchor pass, useful as a cross-check "
                     "on the AST findings above.")
            L.append("")
            for cat, hits in sorted(analysis["categories"].items()):
                labels = [str(h) for h in hits] if isinstance(hits, list) else [str(hits)]
                L.append("- **%s**: %s" % (cat, ", ".join(labels)))
            L.append("")

    # ---- how much to trust this ----
    L.append("## Reading this report")
    L.append("")
    for note in data.get("confidence_notes", []):
        L.append("- " + note)
    L.append("")
    L.append("The machine-readable form of everything above is in " + BT + "xray.json" + BT +
             ", and the raw AST facts are in " + BT + "structure.json" + BT + ".")
    L.append("")
    return "\n".join(L)


def main():
    ap = argparse.ArgumentParser(description="render the explanation json as markdown")
    ap.add_argument("explanation", help="xray.json from explain.py")
    ap.add_argument("output", help="report.md path")
    ap.add_argument("--analysis", help="optional analysis json from the anchor pass")
    ap.add_argument("--meta", help="webcrack meta json")
    ap.add_argument("--source", help="original input path for display")
    ap.add_argument("--clean", help="deobfuscated js path for display")
    ap.add_argument("--inline-meta", help="second-pass inlining meta json")
    ap.add_argument("--max-functions", type=int, default=15)
    args = ap.parse_args()

    with open(args.explanation, encoding="utf-8") as fh:
        data = json.load(fh)
    text = render(data, args)
    with open(args.output, "w", encoding="utf-8") as fh:
        fh.write(text)
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
