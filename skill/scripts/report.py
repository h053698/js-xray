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

PORT_SNIPPETS = {
    ("FNV-1a 32-bit", "imul"): (
        "h = 2166136261\n"
        "for ch in data:\n"
        "    h ^= ord(ch)\n"
        "    h = (h * 16777619) & 0xFFFFFFFF"
    ),
    # JS: h = h * 16777619 >>> 0. The xor leaves a signed int32, and the float64
    # product of that with the prime overflows 2**53, so the rounding is part of
    # the algorithm. Verified against Node: masking an exact product diverges.
    ("FNV-1a 32-bit", "truncated-float"): (
        INT32_HELPER + "\n\n"
        "h = 2166136261\n"
        "for ch in data:\n"
        "    h = (h ^ ord(ch)) & 0xFFFFFFFF\n"
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
    ("djb2", None): "h = 5381\nfor ch in data:\n    h = ((h * 33) + ord(ch)) & 0xFFFFFFFF",
    ("LCG", None): "state = (state * 1664525 + 1013904223) & 0xFFFFFFFF",
}


def port_snippet(family, style):
    """Snippet for a family, matched to how the source multiplies.

    Returns None when the style is unknown or mixed rather than guessing: a wrong
    snippet is worse than none, because it looks authoritative and fails only on
    longer inputs.
    """
    if (family, None) in PORT_SNIPPETS:
        return PORT_SNIPPETS[(family, None)]
    if style in ("imul", "truncated-float"):
        return PORT_SNIPPETS.get((family, style))
    return None


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
    L.append("| functions | %s |" % s.get("functions"))
    L.append("| classes | %s |" % s.get("classes"))
    L.append("| entry points | %s |" % s.get("entry_points"))
    d = data.get("deobfuscation") or {}
    if d:
        L.append("| strings inlined | %s resolved, %s unresolved |" % (
            d.get("strings_inlined", 0), d.get("unresolved", 0)))
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
    for fn in data.get("functions", [])[:args.max_functions]:
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
            if algo.get("constants"):
                L.append("Constants: " + ", ".join(str(c) for c in algo["constants"]))
                L.append("")
            if algo.get("returns"):
                L.append("Returns " + BT + algo["returns"][0] + BT)
                L.append("")
            for family in algo["families"]:
                snippet = port_snippet(family, algo.get("multiply_style"))
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
