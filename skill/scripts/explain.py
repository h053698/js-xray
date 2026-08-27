#!/usr/bin/env python3
"""Turn structural facts into an agent-consumable explanation of a JS module.

structure.mjs answers "what is in this file". This stage answers the two
questions a caller actually has:

  1. What does this module do, in flows I can narrate to a person?
  2. What do I need to know to reimplement or decrypt any part of it?

Everything here is inference, so every claim carries the facts it came from.
A role with one weak signal and a role with four converging ones must not look
the same to a reader, otherwise an agent will state guesses as findings.

Two corrections are applied to the raw facts first:

  * Anonymous functions get a parent by line containment. The call graph is
    name-based, so an inline callback shows called_by == 0 even when it holds the
    hot loop -- the FNV hash in the Sentinel sample is exactly this case.
  * Reachability is computed from real entry points rather than trusting
    called_by, so helpers reached only through callbacks are not reported dead.
"""
import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, HERE)

MAX_FLOW_DEPTH = 6
MAX_FLOW_NODES = 40
MAX_TRACED_ENTRIES = 8

# Why --top stays at 25 rather than scaling with the file, even though a reader of
# a 291-function module found 25 too few:
#
# functions[] costs about 750 characters per entry on the sentinel sample, so
# detailing every function of a 291-function file grows xray.json from ~56KB to
# ~185KB. The whole point of this artifact is that an agent can read it instead
# of the source, and tripling it defeats that -- the caller who needs more than
# the top slice generally needs one specific function, which "xq show" answers
# for a fraction of the cost.
#
# So the cap stays and the truncation is made impossible to miss instead:
# summary.functions_detailed / functions_omitted carry the numbers, and a
# confidence note says where the rest are. The failure being fixed was never
# "25 is the wrong number" but "the reader could not tell 25 was not all of
# them" -- someone read functions[] as the whole file and went to clean.js by
# hand rather than re-running with a larger --top.

# What to say when the file turns out to be a bytecode interpreter rather than
# the logic a reader came for. Everything else this module produces is derived
# from the interpreter's own AST, so the warning has to come before it, in the
# same voice as the other notes: what is wrong, and what not to trust.
VM_WARNING = {
    "vm-obfuscated": (
        "This file is VM-obfuscated (JSVMP): the original logic was compiled to a "
        "bytecode array and what remains in the AST is the interpreter that runs it. "
        "Every function below is an interpreter part -- dispatch, registers, operand "
        "decoding -- so flows, functions and porting describe the virtual machine, "
        "not the module's behaviour. Do not report them as what this code does. The "
        "behaviour is in the bytecode operands, which this pipeline does not "
        "recover; see summary.vm_obfuscation and vm_signals for the evidence."
    ),
    "suspected": (
        "This file shows part of a VM-obfuscation (JSVMP) fingerprint: some of the "
        "extracted functions are probably a bytecode interpreter rather than the "
        "module's own logic. Check vm_signals against clean.js before trusting any "
        "flow or porting note that passes through the dispatch loop cited there."
    ),
}


def vm_note(vm_signals):
    """The confidence note for a VM verdict, or None when there is nothing to say.

    An unknown verdict (structure extraction degraded, so nothing was examined)
    gets no note: the degradation is already reported through "error", and adding
    a VM caveat there would invent a suspicion nothing supports.
    """
    verdict = (vm_signals or {}).get("verdict")
    return VM_WARNING.get(verdict)


# Bitwise work on 32-bit lanes is the signature of a hand-rolled hash or cipher,
# and it is also the number one source of porting bugs in other languages.
BITWISE = {"^", "&", "|", "<<", ">>", ">>>", "^=", "&=", "|=", "<<=", ">>=", ">>>="}

FINGERPRINT_ROOTS = ("navigator", "screen", "performance", "document", "window", "location")

# Substrings that mark a call as belonging to a capability, checked against the
# dotted call paths structure.mjs records.
CALL_MARKERS = {
    "base64": ("atob", "btoa", "toString(\"base64\")", "Buffer.from"),
    "charcode": ("charCodeAt", "fromCharCode", "codePointAt", "TextEncoder", "TextDecoder"),
    "webcrypto": ("crypto.subtle", "crypto.getRandomValues", "createHash", "createHmac"),
    "serialize": ("JSON.stringify", "JSON.parse"),
    "timer": ("setTimeout", "setInterval", "requestAnimationFrame", "requestIdleCallback"),
    "random": ("Math.random", "crypto.getRandomValues"),
    "dom": ("document.querySelector", "document.getElement", "document.createElement"),
}

# ---- anti-analysis scaffolding (javascript-obfuscator self-defending /
# ---- debugProtection / disableConsoleOutput) --------------------------------
#
# These stubs are not the module's logic. They are boilerplate the obfuscator
# injects to make the file unpleasant to debug, and their shape is close to
# fixed. webcrack removes them when it recognises them, but its matchers require
# an exact AST shape (an exact two-statement function body, an exact
# [VariableDeclaration, ReturnStatement] IIFE body), so any later pass that
# perturbs the shape -- a bundler, a minifier, a re-obfuscation -- leaves them
# in the file. Note that webcrack.json's "self-defending, debug-protection,
# jsx, jsx-new" count is a grouped pass counter, not a removal count: it reads
# the same whether or not anything was actually removed, so it cannot be used
# to decide this.
#
# What surviving stubs cost: on a fixture of 6 real functions they add 23 more,
# so a role histogram reads as a 29-function module of which most is
# unclassified, and any role they do pick up is a claim about scaffolding
# presented next to claims about the module.
#
# This labels rather than deletes. Removing the functions would leave a reader
# unable to check the call, and the project's existing choice for VM
# obfuscation was to warn with evidence rather than drop the functions. The
# label keeps the stubs auditable while letting a reader (and summary.roles)
# separate scaffolding from logic.

ANTI_ANALYSIS_ROLE = "anti-analysis scaffolding"

# The regexes these stubs build to inspect their own source text. Both are
# literal strings in javascript-obfuscator's output, so they are matched as
# exact substrings rather than sniffed for "looks like a regex".
#
#   "(((.+)+)+)+$"     -- catastrophic-backtracking bait in the self-defending
#                         toString() check
#   "function *\( *\)" -- the self-defending source-shape assertion
#   "\w+ *\( *\)"     -- the same assertion in the string-array decoder's
#                         self-check
#   "\+\+ *(?:[a-zA-Z_$]..." -- the debug-protection counter assertion
SELF_CHECK_PATTERNS = (
    "(((.+)+)+)+$",
    "function *\\( *\\)",
    "\\w+ *\\( *\\)",
    "\\+\\+ *(?:[a-zA-Z_$]",
)

# Strings only a debugger trap constructs. "debugger" is passed to Function or
# .constructor to build a debugger statement dynamically, which is how these
# stubs survive a transform that would drop a bare one; "while (true) {}" is
# the hang-the-tab variant.
DEBUGGER_STRINGS = ("debugger", "while (true) {}", "while(true){}")

# The global-object reacquisition preamble. Every one of these stubs starts by
# re-deriving the global object through the Function constructor so it works
# outside its original scope. Distinctive enough to name, but on its own it is
# only a hint: it appears in legitimate universal-module preambles too.
GLOBAL_REACQUIRE = 'constructor("return this")'

# The console methods disableConsoleOutput overwrites, in the order it emits
# them. Real code hooks console too, so the list alone proves nothing -- what
# distinguishes the stub is that it takes the whole set including the ones no
# application logs through.
CONSOLE_HOOK_METHODS = ("log", "warn", "info", "error", "exception", "table", "trace")

# How much of that set has to be present. "exception", "table" and "trace" are
# the tell: a logger wrapper hooks log/warn/error, it does not enumerate
# console.exception. Requiring 5 of 7 admits the stub and excludes the wrapper.
CONSOLE_HOOK_MIN = 5


# Calls that mean the function is actually *running* a source self-check rather
# than merely holding the pattern as data. This distinction is load-bearing: an
# obfuscated string-array provider carries every literal the module uses in one
# table, including the self-check regex, so matching on the literal alone tags
# the decoder that supplies the module's own strings. Such a provider makes no
# calls at all -- it returns its table -- while the stub reads a function body
# and matches it.
SELF_CHECK_EXECUTORS = ("toString", "search", "test", "match", "RegExp", "exec")


def anti_analysis_signals(fn):
    """Signals that a function is obfuscator anti-analysis scaffolding.

    Returns a list of (kind, evidence) pairs. Each entry is a fact about the
    AST, so the caller can publish them as the evidence for its verdict rather
    than asserting the verdict alone.
    """
    calls = fn.get("calls", []) or []
    strings = fn.get("strings", []) or []
    rets = fn.get("returns", []) or []
    # returns[] holds generated source previews, so a self-check that lives in
    # a returned expression is visible there and nowhere else.
    text_pool = list(strings) + list(rets)
    out = []

    if fn.get("debugger_statements"):
        out.append(("debugger-statement",
                    "contains %d bare debugger statement(s)"
                    % fn["debugger_statements"]))

    dbg = sorted({s for s in strings if s in DEBUGGER_STRINGS})
    if dbg:
        out.append(("debugger-string",
                    "builds a debugger trap from the literal(s) %s"
                    % ", ".join(repr(s) for s in dbg)))

    checks = sorted({p for p in SELF_CHECK_PATTERNS
                     if any(p in t for t in text_pool)})
    # Requires the pattern *and* a call that could apply it. See
    # SELF_CHECK_EXECUTORS: without this, every string-array provider whose
    # table happens to include the literal gets tagged, which is how the real
    # Sentinel SDK's own string decoders came out as scaffolding.
    if checks and _has(calls, SELF_CHECK_EXECUTORS):
        out.append(("source-self-check",
                    "tests its own source text against %s"
                    % ", ".join(repr(c) for c in checks)))
        checks_active = True
    else:
        checks_active = False

    # toString() on a function, fed to a regex or search: the stub reading its
    # own body to see whether it has been reformatted by a debugger.
    if checks_active and _has(calls, ("toString",)):
        out.append(("tostring-inspection",
                    "reads its own body with toString() and matches it"))

    if any(GLOBAL_REACQUIRE in t for t in text_pool):
        out.append(("global-reacquire",
                    "re-derives the global object via %s" % GLOBAL_REACQUIRE))

    hooked = [m for m in CONSOLE_HOOK_METHODS if m in strings]
    if len(hooked) >= CONSOLE_HOOK_MIN:
        out.append(("console-override",
                    "overwrites %d console methods including %s"
                    % (len(hooked), ", ".join(hooked))))

    # Self-recursion with no loop of its own: the shape of the debug-protection
    # counter, which re-enters itself instead of iterating. Corroborating only,
    # never sufficient -- plenty of real code recurses.
    name = fn.get("name")
    if name and name in calls and not (fn.get("control") or {}).get("loops"):
        out.append(("self-recursion", "calls itself (%s) with no loop" % name))

    return out


def anti_analysis_role(fn):
    """The anti-analysis role for a function, or None.

    A required condition plus corroboration, deliberately, because the cheap
    version of this check destroys findings rather than adding one. Normal code
    hooks console, measures time and validates with regexes; tagging on any one
    of those would relabel a module's real error handling as scaffolding, and a
    reader who is told a function is boilerplate stops reading it.

    So one of three things specific to these stubs has to be present:

      * a debugger trap (a bare debugger statement, or "debugger" handed to a
        function constructor),
      * a source self-check against one of the obfuscator's literal regexes,
      * a console override that takes essentially the whole console surface.

    Confidence then reflects how much agrees. Two or more required-tier signals,
    or one plus corroboration, is the full fingerprint and reads "high"; a lone
    required signal stays "medium", because a hand-written debugger trap is a
    real thing a reader may still want to look at.
    """
    signals = anti_analysis_signals(fn)
    if not signals:
        return None

    kinds = {k for k, _ in signals}
    required = kinds & {"debugger-statement", "debugger-string",
                        "source-self-check", "console-override"}
    if not required:
        # Only corroborating signals: a global-object preamble or a recursive
        # helper. Both occur in ordinary code, so nothing is claimed.
        return None

    corroborating = kinds - required
    if len(required) >= 2 or (required and corroborating):
        confidence = "high"
    else:
        confidence = "medium"

    return {
        "role": ANTI_ANALYSIS_ROLE,
        "confidence": confidence,
        "evidence": [ev for _k, ev in signals],
    }


def _has(haystack, needles):
    return [n for n in needles if any(n in h for h in haystack)]


def build_index(structure):
    """Index functions by id and attach parent/child links by line containment."""
    fns = structure.get("functions", []) or []
    by_id = {f["id"]: f for f in fns}

    # Innermost enclosing function wins: sort by span so the tightest range is last.
    ordered = sorted(fns, key=lambda f: (f.get("start_line") or 0, -(f.get("end_line") or 0)))
    for fn in fns:
        fn["_parent"] = None
        fn["_children"] = []
    for fn in fns:
        s, e = fn.get("start_line"), fn.get("end_line")
        if s is None or e is None:
            continue
        best = None
        for cand in ordered:
            if cand is fn:
                continue
            cs, ce = cand.get("start_line"), cand.get("end_line")
            if cs is None or ce is None:
                continue
            if cs <= s and ce >= e and (ce - cs) > (e - s):
                if best is None or (cand["start_line"] >= best["start_line"]
                                    and cand["end_line"] <= best["end_line"]):
                    best = cand
        if best is not None:
            fn["_parent"] = best["id"]
            best["_children"].append(fn["id"])
    return by_id


def display_name(fn, by_id):
    """A label a human can locate in the file, even for anonymous functions.

    The label stops at the nearest *named* ancestor. Chaining every anonymous
    parent produces names like
    "<iife@L1> > <iife@L14> > <anonymous@L16> > <anonymous@L17>" that are longer
    than the code they point at, and the line span already identifies the function
    unambiguously.

    The span is included because anonymous siblings can start on the same line -- a
    call taking two inline callbacks -- and would otherwise print identically.
    """
    if fn.get("name"):
        if fn.get("class"):
            return "%s.%s" % (fn["class"], fn["name"])
        return fn["name"]

    span = "L%s" % fn.get("start_line")
    if fn.get("end_line") and fn.get("end_line") != fn.get("start_line"):
        span += "-%s" % fn["end_line"]
    elif fn.get("start_col") is not None:
        span += "c%s" % fn["start_col"]  # siblings share the line; the column does not
    label = "<%s@%s>" % (fn.get("kind", "fn"), span)
    seen = set()
    cur = by_id.get(fn.get("_parent") or "")
    while cur is not None and cur["id"] not in seen:
        seen.add(cur["id"])
        if cur.get("name"):
            owner = "%s.%s" % (cur["class"], cur["name"]) if cur.get("class") else cur["name"]
            return "%s > %s" % (owner, label)
        cur = by_id.get(cur.get("_parent") or "")
    return label


def classify(fn, by_id):
    """Infer what a function is for. Returns a list of {role, confidence, evidence}.

    Roles are not exclusive -- a function that fingerprints the browser and posts
    the result is both. Confidence reflects how many independent facts agree, so a
    caller can tell a hash loop with named constants from a lone xor.
    """
    roles = []
    calls = fn.get("calls", []) or []
    globs = fn.get("globals", []) or []
    ops = set(fn.get("operators", []) or [])
    ctrl = fn.get("control", {}) or {}
    algos = fn.get("algorithms", []) or []
    nums = fn.get("numbers", []) or []
    strings = fn.get("strings", []) or []

    def add(role, confidence, evidence):
        roles.append({"role": role, "confidence": confidence, "evidence": evidence})

    # --- obfuscator anti-analysis scaffolding ---
    # Decided first, and it suppresses the weak fallback roles below rather than
    # sitting next to them. A debug-protection stub throws to break out of its
    # own recursion, which the error-path rule reads as validation; publishing
    # both would put a claim about the module's error handling next to the
    # evidence that this is not the module. The strong capability rules still
    # run: if a stub genuinely performs network I/O that is worth knowing, and
    # nothing about this label should hide it.
    anti = anti_analysis_role(fn)
    if anti is not None:
        roles.append(anti)

    # --- named algorithm: the strongest signal available ---
    if algos:
        families = sorted({a.split(" (")[0] for a in algos})
        add("hash/digest", "high",
            ["magic constants match %s" % ", ".join(families)] +
            (["loop over input"] if ctrl.get("loops") else []))

    # --- hand-rolled bit mixing without a recognised constant ---
    bitwise = sorted(ops & BITWISE)
    if bitwise and not algos:
        conf = "medium" if ctrl.get("loops") else "low"
        ev = ["32-bit operators %s" % " ".join(bitwise)]
        if ctrl.get("loops"):
            ev.append("inside a loop, so it accumulates state")
        if _has(calls, CALL_MARKERS["charcode"]):
            ev.append("reads input as character codes")
        add("bit mixing (unrecognised algorithm)", conf, ev)

    # --- encoding rather than hashing: reversible transforms ---
    enc = _has(calls, CALL_MARKERS["base64"]) + [o for o in ops if "base64" in o]
    if enc:
        add("encode/decode", "high" if len(enc) > 1 else "medium",
            ["base64 primitives: %s" % ", ".join(sorted(set(enc)))])

    if _has(calls, CALL_MARKERS["webcrypto"]):
        add("cryptography (platform)", "high",
            ["calls %s" % ", ".join(_has(calls, CALL_MARKERS["webcrypto"]))])

    # --- network: the module boundary worth documenting precisely ---
    if fn.get("network"):
        kinds = sorted({n.get("kind", "?") for n in fn["network"]})
        add("network transport", "high",
            ["performs %s" % ", ".join(kinds)] +
            ["target %s" % n["url"] for n in fn["network"] if n.get("url")][:3])

    # --- fingerprinting: reading the environment to describe the client ---
    fp = [g for g in globs if g.split(".")[0] in FINGERPRINT_ROOTS]
    if len(fp) >= 3:
        add("environment fingerprinting", "high" if len(fp) >= 5 else "medium",
            ["reads %d browser properties: %s" % (len(fp), ", ".join(fp[:8]))])
    elif fp and _has(calls, CALL_MARKERS["serialize"]):
        add("environment fingerprinting", "low",
            ["reads %s and serialises it" % ", ".join(fp)])

    # --- persistence ---
    if fn.get("storage"):
        add("persistence", "high", ["storage ops: %s" % ", ".join(str(s) for s in fn["storage"][:5])])

    # --- state holder: constructors and anything writing many this.* fields ---
    writes = fn.get("writes_this", []) or []
    if fn.get("kind") == "constructor" or len(writes) >= 3:
        add("state holder", "high" if fn.get("kind") == "constructor" else "medium",
            ["assigns this.%s" % w for w in writes[:6]] or ["class constructor"])

    # --- serialization ---
    if _has(calls, CALL_MARKERS["serialize"]) and not fn.get("network"):
        add("serialization", "low", ["uses %s" % ", ".join(_has(calls, CALL_MARKERS["serialize"]))])

    # --- retry / polling ---
    if _has(calls, CALL_MARKERS["timer"]) and (ctrl.get("loops") or fn.get("awaits")):
        add("scheduling/retry", "medium",
            ["timer calls %s with %d await(s)" % (
                ", ".join(_has(calls, CALL_MARKERS["timer"])), fn.get("awaits", 0))])

    # --- error path ---
    if fn.get("throws") and not roles:
        add("validation/error path", "low", ["throws %d time(s)" % len(fn["throws"])])

    # --- string-array decoder left over from obfuscation ---
    if (fn.get("loc_lines", 0) <= 12 and len(fn.get("params", [])) in (1, 2)
            and not roles and ("-=" in ops or fn.get("returns"))):
        rets = " ".join(fn.get("returns", [])[:2])
        if "[" in rets:
            add("lookup/decoder shim", "low",
                ["small indexed lookup: returns %s" % rets[:80]])

    if not roles:
        hints = []
        if ctrl.get("loops"):
            hints.append("%d loop(s)" % ctrl["loops"])
        if ctrl.get("branches"):
            hints.append("%d branch(es)" % ctrl["branches"])
        if strings:
            hints.append("literals %s" % ", ".join(repr(s) for s in strings[:3]))
        if nums:
            hints.append("constants %s" % ", ".join(str(n) for n in nums[:3]))
        add("unclassified", "none", hints or ["no distinguishing facts recorded"])

    return roles


def rollup_child_roles(fns, by_id, roles_by_id):
    """Propagate a nested closure's roles up to the function that contains it.

    A wrapper whose entire purpose is to hold a hash loop records no bitwise
    operators itself, so it classifies as unclassified while its inner closure
    carries the finding. Reading a flow at that level would miss the algorithm
    entirely. The inherited role is marked so it is never mistaken for a direct
    observation.

    Anti-analysis scaffolding is excluded from this. The rollup's premise is
    that a wrapper holding one closure is *about* what that closure does, which
    holds for a hash loop and fails badly here: an obfuscator injects its stubs
    as siblings of the real logic, so the enclosing function is usually the
    bundle wrapper spanning the whole file. Propagating the label there marks
    the entire module as scaffolding, which is the one outcome worse than not
    labelling it at all -- it would tell a reader to skip the code they came
    for. A stub is always reported on the function that actually contains the
    trap.
    """
    order = sorted(fns, key=lambda f: -(f.get("start_line") or 0))
    for fn in order:
        own = {r["role"] for r in roles_by_id.get(fn["id"], [])}
        inherited = []
        for child_id in fn.get("_children", []) or []:
            child = by_id.get(child_id)
            if child is None or child.get("name"):
                continue  # named children are reachable on their own
            for r in roles_by_id.get(child_id, []):
                if r["role"] in ("unclassified", ANTI_ANALYSIS_ROLE) or r["role"] in own:
                    continue
                own.add(r["role"])
                inherited.append({
                    "role": r["role"],
                    "confidence": r["confidence"],
                    "inherited_from": display_name(child, by_id),
                    "evidence": r["evidence"],
                })
        if inherited:
            existing = [r for r in roles_by_id.get(fn["id"], []) if r["role"] != "unclassified"]
            roles_by_id[fn["id"]] = existing + inherited


def find_entry_points(structure, by_id):
    """Identify where control enters the module, best evidence first.

    An exported or globally-assigned name is a real entry point. Beyond those we
    accept top-level functions nothing calls, since in a bundle that is what an
    outside caller would reach.

    The bundle wrapper is excluded on purpose. Almost every minified file is one
    IIFE spanning the whole source, and tracing from it reaches everything at once,
    which describes nothing. Its useful contents surface as their own entry
    points. It is still returned separately, because reachability has to start
    there too.
    """
    module = structure.get("module", {}) or {}
    total_lines = structure.get("lines") or 0
    exported = set(module.get("exports", []) or [])
    for ga in module.get("global_assignments", []) or []:
        exported.add(str(ga.get("target", "")).split(".")[-1])
        value = str(ga.get("value", ""))
        for token in value.replace("(", " ").replace(")", " ").split():
            if token.isidentifier():
                exported.add(token)

    def is_bundle_wrapper(fn):
        span = (fn.get("end_line") or 0) - (fn.get("start_line") or 0)
        return (fn.get("_parent") is None and not fn.get("name")
                and total_lines and span >= total_lines * 0.8)

    entries = []
    wrappers = []
    for fn in structure.get("functions", []) or []:
        name = fn.get("name")
        why = None
        if name and name in exported:
            why = "named in the module public surface"
        elif fn.get("kind") == "iife" and fn.get("_parent") is None:
            if is_bundle_wrapper(fn):
                # Not a behaviour of its own, so it is kept out of the flows, but it
                # does run on load and code only it can reach is not dead.
                wrappers.append(fn["id"])
                continue
            why = "top-level IIFE, runs on load"
        elif (name and not fn.get("called_by") and fn.get("loc_lines", 0) >= 4
              and not fn.get("class")):
            why = "function with no in-file caller"
        if why:
            entries.append({"id": fn["id"], "name": display_name(fn, by_id),
                            "line": fn.get("start_line"), "why": why})

    # class methods are reachable from outside once the class is constructed
    for cls in structure.get("classes", []) or []:
        for fn in structure.get("functions", []) or []:
            if fn.get("class") == cls.get("name") and fn.get("name") in (cls.get("methods") or []):
                if not str(fn.get("name")).startswith("_") and not fn.get("called_by"):
                    entries.append({"id": fn["id"], "name": display_name(fn, by_id),
                                    "line": fn.get("start_line"),
                                    "why": "public method of class %s" % cls.get("name")})

    seen, unique = set(), []
    for e in entries:
        if e["id"] in seen:
            continue
        seen.add(e["id"])
        unique.append(e)
    return unique, wrappers


ENTRY_TIER = {
    "named in the module public surface": 0,
    "public method of class": 1,
    "top-level IIFE, runs on load": 2,
    "function with no in-file caller": 3,
}


def rank_entry_points(entries, by_id, roles_by_id):
    """Order entry points by how much they explain, strongest evidence first.

    Excluding the bundle wrapper promotes every decoder shim inside it to "no
    in-file caller", and there are dozens of those. Left unranked they crowd out
    the real API. An exported name or a public method is direct evidence of an
    entry point; a missing caller is only a hint, so it ranks last and is broken
    by how much behaviour the function actually carries.
    """
    def key(entry):
        tier = 3
        for prefix, value in ENTRY_TIER.items():
            if entry["why"].startswith(prefix):
                tier = value
                break
        fn = by_id.get(entry["id"], {})
        interest = 0
        for r in roles_by_id.get(entry["id"], []):
            interest += {"high": 30, "medium": 12, "low": 4, "none": 0}[r["confidence"]]
        if fn.get("network"):
            interest += 60
        if fn.get("algorithms"):
            interest += 40
        interest += min(fn.get("loc_lines") or 0, 40)
        interest += 3 * len(fn.get("_children") or [])
        return (tier, -interest, entry.get("line") or 0)

    return sorted(entries, key=key)


def resolve_targets(structure, by_id):
    """Build the lookup tables successors() needs.

    Two tables, because two call shapes matter. Plain `foo()` resolves by name.
    `this.foo()` cannot: the name lives on a class, and in obfuscated output the
    same short method name is reused across classes. Keying those by (class, name)
    keeps a method call inside its own class instead of jumping to a namesake.
    """
    by_name = {}
    by_member = {}
    for fn in structure.get("functions", []) or []:
        name = fn.get("name")
        if not name:
            continue
        by_name.setdefault(name, []).append(fn["id"])
        if fn.get("class"):
            by_member[(fn["class"], name)] = fn["id"]
    return {"by_name": by_name, "by_member": by_member}


def successors(fn, by_id, tables):
    """Callees of a function: named calls, own-class methods, inline callbacks.

    Children are included because obfuscated code hides the real work in anonymous
    closures no name-based edge can reach -- the hash loop in the Sentinel sample
    lives in exactly such a closure.
    """
    by_name = tables["by_name"]
    by_member = tables["by_member"]
    out = []

    for call in fn.get("calls", []) or []:
        target = call.replace("new ", "")
        parts = target.split(".")
        if parts[0] == "this" and len(parts) >= 2:
            # resolve against the owning class first, then any same-named function
            cid = by_member.get((fn.get("class"), parts[1]))
            if cid is None:
                for cand in by_name.get(parts[1], []):
                    cid = cand
                    break
            if cid and cid != fn["id"]:
                out.append((cid, "calls %s" % target))
            continue
        for cand in by_name.get(parts[0], []):
            if cand != fn["id"]:
                out.append((cand, "calls %s" % target))

    for child in fn.get("_children", []) or []:
        kid = by_id.get(child)
        if kid is not None and not kid.get("name"):
            out.append((child, "inline %s" % kid.get("kind", "function")))

    seen, unique = set(), []
    for cid, via in out:
        if cid in seen:
            continue
        seen.add(cid)
        unique.append((cid, via))
    return unique


def trace_flow(entry_id, by_id, tables, roles_by_id):
    """Walk outward from an entry point, depth first, describing each step.

    Depth-first follows one path to its conclusion before backtracking, which is
    the order behaviour gets narrated in; breadth-first interleaves unrelated
    branches at the same depth.

    Successors are visited most-informative-first and the walk is capped. Minified
    files nest anonymous wrappers several levels deep, and spending the budget on
    those means the fetch or the hash never appears in the trace.
    """
    steps = []
    visited = {entry_id}

    def weight(fid):
        fn = by_id.get(fid) or {}
        score = 0
        if fn.get("network"):
            score += 100
        if fn.get("algorithms"):
            score += 80
        for r in roles_by_id.get(fid, []):
            score += {"high": 30, "medium": 12, "low": 4, "none": 0}[r["confidence"]]
        if fn.get("name"):
            score += 10  # a named callee is something a reader can look up
        return -score

    def walk(fid, depth, via):
        if len(steps) >= MAX_FLOW_NODES:
            return
        fn = by_id.get(fid)
        if fn is None:
            return
        step = {
            "depth": depth,
            "id": fid,
            "name": display_name(fn, by_id),
            "line": fn.get("start_line"),
            "reached_by": via,
            "does": [r["role"] for r in roles_by_id.get(fid, []) if r["role"] != "unclassified"],
        }
        if fn.get("network"):
            step["network"] = fn["network"]
        if fn.get("algorithms"):
            step["algorithms"] = sorted({a.split(" (")[0] for a in fn["algorithms"]})
        steps.append(step)
        if depth >= MAX_FLOW_DEPTH:
            return
        succ = successors(fn, by_id, tables)
        for cid, cvia in sorted(succ, key=lambda pair: weight(pair[0])):
            if cid in visited:
                continue
            visited.add(cid)
            walk(cid, depth + 1, cvia)

    walk(entry_id, 0, "entry point")
    return steps, visited


MULTIPLY_STYLE_NOTE = {
    "imul": ("Math.imul(a, b) -- an exact 32-bit product. Port as "
             "(a * b) & 0xFFFFFFFF in Python, or uint32 multiply in Go/Rust."),
    "truncated-float": ("a * b >>> 0 -- the product is computed in float64 and only "
                        "then truncated, so bits below 2^53 are already lost. A plain "
                        "(a * b) & 0xFFFFFFFF does NOT reproduce it."),
    "mixed": ("Both Math.imul and truncated float multiplies appear in this function. "
              "Read the source line by line; no single rule ports it."),
}

# What one iteration of a character loop consumes. The multiply style decides how
# a step is computed; this decides what is fed into it, and the two go wrong the
# same way -- silently, and only on inputs a smoke test does not reach. ord() in
# place of charCodeAt agrees on the entire BMP, so ASCII, Hangul and CJK tests all
# pass and the digest changes the first time an emoji arrives.
CHAR_SOURCE_NOTE = {
    "utf16-code-units": ("charCodeAt(i) -- UTF-16 code units, so a character above "
                         "U+FFFF is two iterations of its two surrogate halves. "
                         "Python's ord(ch) gives one code point instead and diverges "
                         "there; iterate over UTF-16 code units."),
    "code-points": ("codePointAt(i) -- whole code points, which is what Python's "
                    "ord(ch) already gives. Note that a JS loop stepping by 1 over "
                    "codePointAt visits the trailing surrogate too; check the stride."),
    "bytes": ("TextEncoder / Buffer -- the input is encoded to bytes before hashing, "
              "so the loop consumes bytes and not characters. Encode with the same "
              "encoding the source used before porting the loop."),
    "mixed": ("Both charCodeAt and a byte encoder appear in this function, so which "
              "one feeds the hash is not decidable from the AST facts. Read the loop "
              "in clean.js before porting it."),
}

# Substrings in a recorded call path that fix the unit. Ordered longest-first
# within a group so codePointAt is not read as charCodeAt's prefix.
CHAR_SOURCE_MARKERS = (
    ("utf16-code-units", ("charCodeAt", "charAt", "fromCharCode")),
    ("code-points", ("codePointAt", "fromCodePoint")),
    ("bytes", ("TextEncoder", "Buffer.from", "encodeInto")),
)


def rollup_char_source(fn, by_id):
    """What a character loop in this function consumes, from the calls recorded.

    Same rollup as rollup_arith and for the same reason: the loop is usually in a
    nested closure while the caller is the function a reader recognises.

    Returns None when nothing in the function names a unit. That is a real answer
    -- "the facts do not say" -- and it is reported as an assumption downstream
    rather than resolved by a guess here.
    """
    found = set()
    stack = [fn]
    seen = set()
    while stack:
        cur = stack.pop()
        if id(cur) in seen:
            continue
        seen.add(id(cur))
        paths = list(cur.get("calls") or []) + list(cur.get("globals") or [])
        for path in paths:
            for unit, markers in CHAR_SOURCE_MARKERS:
                if any(m in path for m in markers):
                    found.add(unit)
        for cid in cur.get("_children", []) or []:
            child = by_id.get(cid)
            if child is not None:
                stack.append(child)
    # charCodeAt alongside fromCharCode is one unit, not two; only a byte encoder
    # next to a character reader is a genuine ambiguity about what gets hashed.
    if len(found) > 1:
        return "mixed"
    return found.pop() if found else None


def rollup_arith(fn, by_id):
    """Multiplication style for a function including its inline closures.

    The arithmetic usually lives in a nested callback while the caller is the
    function a reader recognises, so counting only the function itself reports
    no style for exactly the cases that matter.
    """
    imul = 0
    trunc = 0
    stack = [fn]
    seen = set()
    while stack:
        cur = stack.pop()
        if id(cur) in seen:
            continue
        seen.add(id(cur))
        a = cur.get("arith") or {}
        imul += a.get("imul_calls", 0) or 0
        trunc += a.get("truncated_multiplies", 0) or 0
        for cid in cur.get("_children", []) or []:
            child = by_id.get(cid)
            if child is not None:
                stack.append(child)
    style = None
    if imul and trunc:
        style = "mixed"
    elif imul:
        style = "imul"
    elif trunc:
        style = "truncated-float"
    return {"imul_calls": imul, "truncated_multiplies": trunc, "multiply_style": style}

def porting_spec(structure, by_id, roles_by_id):
    """Collect what a reimplementation has to get right.

    The pitfalls are not decoration. JavaScript bitwise operators coerce to int32
    while Python integers are unbounded, so a hash ported without masking agrees
    for short inputs and diverges later -- the failure mode that costs the most
    time when reimplementing this kind of code.
    """
    spec = {"algorithms": [], "network_contracts": [], "inputs": [], "pitfalls": []}

    for fn in structure.get("functions", []) or []:
        if fn.get("algorithms"):
            arith = rollup_arith(fn, by_id)
            char_source = rollup_char_source(fn, by_id)
            spec["algorithms"].append({
                "function": display_name(fn, by_id),
                "id": fn["id"],
                "lines": [fn.get("start_line"), fn.get("end_line")],
                "families": sorted({a.split(" (")[0] for a in fn["algorithms"]}),
                "constants": fn.get("numbers", []),
                "operators": fn.get("operators", []),
                "returns": fn.get("returns", []),
                "loops": (fn.get("control") or {}).get("loops", 0),
                "multiply_style": arith["multiply_style"],
                "multiply_note": MULTIPLY_STYLE_NOTE.get(arith["multiply_style"]),
                # The unit the loop consumes, on the same footing as the multiply
                # style: null means the facts did not say, not that it is bytes.
                "char_source": char_source,
                "char_source_note": CHAR_SOURCE_NOTE.get(char_source),
            })
        for net in fn.get("network", []) or []:
            entry = dict(net)
            entry["function"] = display_name(fn, by_id)
            entry["id"] = fn["id"]
            entry["line"] = fn.get("start_line")
            spec["network_contracts"].append(entry)

    # input surface: every browser property the module reads, deduplicated
    inputs = {}
    for fn in structure.get("functions", []) or []:
        for g in fn.get("globals", []) or []:
            if g.split(".")[0] in FINGERPRINT_ROOTS:
                inputs.setdefault(g, []).append(display_name(fn, by_id))
    spec["inputs"] = [{"property": k, "read_by": sorted(set(v))[:4]}
                      for k, v in sorted(inputs.items())]

    ops_all = set()
    for fn in structure.get("functions", []) or []:
        ops_all |= set(fn.get("operators", []) or [])

    if ops_all & BITWISE:
        spec["pitfalls"].append({
            "issue": "32-bit integer semantics",
            "detail": ("JavaScript bitwise operators truncate to int32 and >>> yields "
                       "uint32. In Python mask with & 0xFFFFFFFF after every step; in "
                       "Go/Rust use uint32 types."),
        })

    # Multiplication is where ports silently diverge, so report the styles that
    # are actually present instead of one generic warning.
    styles = {a.get("multiply_style") for a in spec["algorithms"] if a.get("multiply_style")}
    for style in sorted(styles):
        spec["pitfalls"].append({
            "issue": "32-bit multiply style: " + style,
            "detail": MULTIPLY_STYLE_NOTE[style],
        })
    if "truncated-float" in styles or "mixed" in styles:
        spec["pitfalls"].append({
            "issue": "float64 rounding in a * b >>> 0",
            "detail": ("The accumulator is a signed int32 after ^, so the operand can be "
                       "negative, and prime * 2**31 exceeds 2**53. Reproduce it exactly "
                       "in Python with: h = int(float(to_int32(h)) * PRIME) & 0xFFFFFFFF, "
                       "where to_int32 reinterprets the low 32 bits as signed. Masking "
                       "an exact product instead gives a different digest."),
        })

    # The encoding trap, reported the same way and for the same reason as the
    # multiply: it is the other half of "what the loop does per step", it fails
    # only above the BMP, and warning about the multiply while staying silent
    # here is what let ord()-based snippets ship. Only raised when a character
    # reader is actually present, so a byte-oriented file is not told about a
    # trap it cannot hit.
    char_sources = {a.get("char_source") for a in spec["algorithms"]}
    if {"utf16-code-units", "mixed"} & char_sources:
        spec["pitfalls"].append({
            "issue": "charCodeAt is UTF-16 code units, not code points",
            "detail": ("charCodeAt(i) returns a UTF-16 code unit, so a character above "
                       "U+FFFF (emoji, rare CJK, most symbols) is two iterations of its "
                       "two surrogate halves. Python's ord(ch) returns one code point, "
                       "which is the same number for every character in the BMP and a "
                       "different one above it: an ord()-based port passes every ASCII, "
                       "Hangul and CJK test and then returns a different digest for the "
                       "first emoji it sees. Iterate over UTF-16 code units instead -- "
                       "split astral code points into surrogates, or read pairs out of "
                       "s.encode('utf-16-le') -- and put an astral case in the tests, "
                       "since no ASCII input can catch this."),
        })
    for algo in spec["algorithms"]:
        if algo.get("char_source") == "mixed":
            spec["pitfalls"].append({
                "issue": "character unit is undecided in " + algo["function"],
                "detail": ("Both charCodeAt and a byte encoder appear here, so the AST "
                           "facts do not say whether the hash consumes UTF-16 code units "
                           "or encoded bytes. The two agree on ASCII and differ on "
                           "everything else, so read the loop in clean.js rather than "
                           "taking the snippet's assumption."),
            })
    if spec["network_contracts"]:
        spec["pitfalls"].append({
            "issue": "request shape is part of the contract",
            "detail": ("Header order, credentials mode and exact body encoding are often "
                       "validated server-side. Copy them from the contract rather than "
                       "assuming defaults."),
        })
    if spec["inputs"]:
        spec["pitfalls"].append({
            "issue": "environment values are inputs, not constants",
            "detail": ("The listed browser properties feed the algorithm. A port must "
                       "supply plausible values with matching types and formatting, "
                       "since they change the output."),
        })
    return spec


def full_reachability(entries, wrapper_ids, by_id, tables):
    """Everything the entry points can reach, ignoring the narrative budget.

    trace_flow stops at MAX_FLOW_DEPTH/MAX_FLOW_NODES so a flow stays readable,
    but that budget must not decide whether a function is dead code. Minified
    bundles routinely bury the interesting work behind a couple of anonymous
    closures, which puts it outside every traced flow; calling that dead points a
    reader away from the part they came for.
    """
    seen = set()
    stack = [e["id"] for e in entries] + list(wrapper_ids)
    while stack:
        cur = stack.pop()
        if cur in seen:
            continue
        seen.add(cur)
        fn = by_id.get(cur)
        if fn is None:
            continue
        for nxt, _via in successors(fn, by_id, tables):
            if nxt not in seen:
                stack.append(nxt)
    return seen


def deobfuscation_report(webcrack_meta=None, inline_meta=None):
    """Report string inlining as the two passes it actually is.

    The pipeline inlines strings twice: webcrack resolves the module-level string
    array first, then inline_strings.py resolves the per-scope arrays webcrack
    left behind. Publishing only the second pass under a bare "strings_inlined"
    made a successful run read as a failed one -- webcrack had inlined 713
    strings and the field said 0, so a reader concluded nothing was decoded and
    went digging in webcrack.json to find out otherwise.

    So each pass reports its own count under its own name, and the only
    unqualified number is the total. No single figure here can be mistaken for
    the whole story, because no single figure is presented as one.
    """
    passes = []
    total = 0

    if webcrack_meta:
        changes = webcrack_meta.get("changes") or {}
        # webcrack's own transform name for the step that substitutes decoded
        # strings back into the source; the count is how many it replaced.
        inlined = changes.get("inline-decoded-strings", 0) or 0
        entry = {
            "pass": "webcrack",
            "strings_inlined": inlined,
            "decoder_wrappers_inlined": changes.get("inline-decoder-wrappers", 0) or 0,
            "ok": bool(webcrack_meta.get("ok")),
        }
        for key in ("string_array", "rotate", "encoding", "decoders"):
            if webcrack_meta.get(key):
                entry[key] = webcrack_meta[key]
        if webcrack_meta.get("error"):
            entry["error"] = webcrack_meta["error"]
        passes.append(entry)
        total += inlined

    if inline_meta:
        inlined = inline_meta.get("replaced", 0) or 0
        passes.append({
            "pass": "inline_strings",
            "strings_inlined": inlined,
            "unresolved": inline_meta.get("unresolved", 0),
            "arrays": inline_meta.get("arrays", 0),
            "decoders": len(inline_meta.get("decoders", []) or []),
            "rolled_back": inline_meta.get("rolled_back", False),
        })
        total += inlined

    if not passes:
        return None
    return {"strings_inlined_total": total, "passes": passes}


def deobfuscation_note(deob):
    """The caveat a two-pass count needs, or None when there is nothing to warn about.

    Only emitted when the passes disagree in the direction that misled a reader
    before: strings were inlined overall, but one pass contributed none of them.
    That is the shape that reads as "nothing was decoded" if a reader stops at
    the first number they see.
    """
    if not deob:
        return None
    passes = deob.get("passes") or []
    if len(passes) < 2 or not deob.get("strings_inlined_total"):
        return None
    zero = [p["pass"] for p in passes if not p.get("strings_inlined")]
    if not zero:
        return None
    return (
        "String inlining ran in two passes and they report separately: %s. A zero "
        "for %s does not mean nothing was decoded -- %d string(s) were inlined in "
        "total. Read deobfuscation.strings_inlined_total for the whole picture."
        % (", ".join("%s inlined %d" % (p["pass"], p.get("strings_inlined") or 0)
                     for p in passes),
           " and ".join(zero), deob["strings_inlined_total"])
    )


def explain(structure, inline_meta=None, top=25, webcrack_meta=None):
    by_id = build_index(structure)
    fns = structure.get("functions", []) or []
    tables = resolve_targets(structure, by_id)

    roles_by_id = {fn["id"]: classify(fn, by_id) for fn in fns}
    rollup_child_roles(fns, by_id, roles_by_id)

    raw_entries, wrappers = find_entry_points(structure, by_id)
    entries = rank_entry_points(raw_entries, by_id, roles_by_id)
    flows, reached = [], set()
    # Several public methods often delegate to one internal path, producing flows
    # that differ only in their first step. Emitting each in full triples the
    # report without adding information, so identical tails are collapsed and the
    # entry points that share them are listed on the survivor.
    traced = entries[:MAX_TRACED_ENTRIES]
    seen_shapes = {}
    for entry in traced:
        steps, visited = trace_flow(entry["id"], by_id, tables, roles_by_id)
        reached |= visited
        entry["traced"] = True
        shape = tuple(step["id"] for step in steps[1:])
        if shape and shape in seen_shapes:
            seen_shapes[shape]["also_entered_by"].append(
                {"name": entry["name"], "line": entry.get("line"), "why": entry["why"]})
            entry["shares_flow_with"] = seen_shapes[shape]["entry"]["name"]
            continue
        flow = {"entry": entry, "steps": steps, "also_entered_by": []}
        if shape:
            seen_shapes[shape] = flow
        flows.append(flow)
    for entry in entries[MAX_TRACED_ENTRIES:]:
        entry["traced"] = False

    # Reachability is computed over all entry points without the flow budget,
    # so "not reached" means no call path exists, not "the narrative ran out".
    reached |= full_reachability(entries, wrappers, by_id, tables)

    # rank functions by how much a reader needs them, not by size alone
    def interest(fn):
        score = 0
        for r in roles_by_id.get(fn["id"], []):
            score += {"high": 40, "medium": 18, "low": 6, "none": 0}[r["confidence"]]
        score += 30 * len(fn.get("network", []) or [])
        score += 25 if fn.get("algorithms") else 0
        score += min(len(fn.get("globals", []) or []) * 2, 20)
        score += min(fn.get("called_by", 0) * 3, 15)
        score += min((fn.get("loc_lines") or 0) // 10, 8)
        return score

    ranked = sorted(fns, key=interest, reverse=True)
    functions_out = []
    for fn in ranked[:top]:
        functions_out.append({
            "id": fn["id"],
            "name": display_name(fn, by_id),
            "raw_name": fn.get("name"),
            "kind": fn.get("kind"),
            "lines": [fn.get("start_line"), fn.get("end_line")],
            "params": fn.get("params", []),
            "async": fn.get("async", False),
            "roles": roles_by_id.get(fn["id"], []),
            "calls": (fn.get("calls") or [])[:12],
            "reads": (fn.get("globals") or [])[:12],
            "network": fn.get("network", []),
            "algorithms": fn.get("algorithms", []),
            "returns": (fn.get("returns") or [])[:3],
            "reachable_from_entry": fn["id"] in reached,
            "importance": interest(fn),
        })

    role_counts = {}
    for rs in roles_by_id.values():
        for r in rs:
            role_counts[r["role"]] = role_counts.get(r["role"], 0) + 1

    unreached = [display_name(f, by_id) for f in fns if f["id"] not in reached]

    vm_signals = structure.get("vm_signals") or {"verdict": "unknown", "score": 0, "signals": []}
    notes = [
        "Call edges are resolved by name, so a shadowed or reassigned identifier "
        "can point at the wrong function. Verify a flow against the source lines "
        "before relying on it.",
        "Roles are inferred from AST facts listed under each role as evidence. "
        "Treat confidence \"low\" and \"none\" as a lead, not a finding.",
        "Anonymous functions are attributed to the enclosing function by line "
        "containment, which is exact, but their call sites may be indirect.",
    ]
    # functions[] is a ranked excerpt, not the file. A reader who takes it for the
    # whole set concludes the module has 25 functions when it has 291, and stops
    # looking -- which is what happened before this note existed. Only said when
    # something was actually left out, so it stays a fact about this run.
    omitted = max(len(fns) - len(functions_out), 0)
    if omitted:
        notes.append(
            "functions[] holds the %d most important of %d functions, so %d are not "
            "detailed here. They are not absent from the analysis: structure.json has "
            "all of them, and \"xq find\" / \"xq show\" name and print any of them "
            "(marked ~, meaning no published role). See summary.functions_detailed."
            % (len(functions_out), len(fns), omitted))
    # A VM verdict invalidates every other note rather than qualifying it, so it
    # goes first: a reader who stops after one line has to have read this one.
    note = vm_note(vm_signals)
    if note:
        notes.insert(0, note)

    deob = deobfuscation_report(webcrack_meta, inline_meta)
    deob_note = deobfuscation_note(deob)
    if deob_note:
        notes.append(deob_note)

    out = {
        "schema": "js-xray/explanation/1",
        "source_file": structure.get("source_file"),
        "size": {"lines": structure.get("lines"), "bytes": structure.get("bytes")},
        "summary": {
            "functions": len(fns),
            # How many of those len(fns) functions functions[] actually details.
            # Published unconditionally, including when nothing was truncated, so
            # a reader comparing the two numbers never has to wonder whether a
            # missing field means "not truncated" or "older run".
            "functions_detailed": len(functions_out),
            "functions_omitted": omitted,
            "classes": len(structure.get("classes", []) or []),
            "entry_points": len(entries),
            # Machine-readable verdict, so an agent can bail out on this field
            # alone instead of parsing the prose in confidence_notes.
            "vm_obfuscation": vm_signals.get("verdict"),
            "roles": dict(sorted(role_counts.items(), key=lambda kv: -kv[1])),
            "endpoints": [u.get("url") if isinstance(u, dict) else u
                          for u in (structure.get("literals", {}) or {}).get("urls", [])],
        },
        "entry_points": entries,
        "flows": flows,
        "functions": functions_out,
        "classes": structure.get("classes", []),
        "porting": porting_spec(structure, by_id, roles_by_id),
        "module": structure.get("module", {}),
        "literals": structure.get("literals", {}),
        # Carried through verbatim: the verdict is an interpretation, so the facts
        # it rests on travel with it for a reader to check.
        "vm_signals": vm_signals,
        "confidence_notes": notes,
    }
    if deob:
        out["deobfuscation"] = deob
    if structure.get("error"):
        out["error"] = structure["error"]
    return out


def main():
    ap = argparse.ArgumentParser(description="explain a JS module from its structural facts")
    ap.add_argument("structure", help="structure.json from structure.py")
    ap.add_argument("output", help="where to write the explanation json")
    ap.add_argument("--inline-meta", help="inline.json from the string-inlining pass")
    ap.add_argument("--meta", help="webcrack.json from the first deobfuscation pass, "
                                  "so the two inlining passes can be reported apart")
    ap.add_argument("--top", type=int, default=25, help="how many functions to detail")
    args = ap.parse_args()

    with open(args.structure, encoding="utf-8") as fh:
        structure = json.load(fh)

    def load_meta(path):
        """A stage metadata file, or None. A missing or corrupt one must not stop
        the explanation: it costs a line of the deobfuscation report, not the
        analysis."""
        if not path or not os.path.isfile(path):
            return None
        try:
            with open(path, encoding="utf-8") as fh:
                return json.load(fh)
        except Exception:
            return None

    inline_meta = load_meta(args.inline_meta)
    webcrack_meta = load_meta(args.meta)

    data = explain(structure, inline_meta, top=args.top, webcrack_meta=webcrack_meta)
    with open(args.output, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2)
    s = data["summary"]
    detail = "%d functions" % s["functions"]
    if s.get("functions_omitted"):
        # Said on the pipeline's own log line too, not only inside the file: the
        # truncation is the kind of thing a caller wants to see while the run is
        # in front of them, when raising --top is still cheap.
        detail += " (%d detailed, %d omitted by --top %d)" % (
            s["functions_detailed"], s["functions_omitted"], args.top)
    print("%s, %d entry points, %d flows, %d algorithms, %d network contracts" % (
        detail, s["entry_points"], len(data["flows"]),
        len(data["porting"]["algorithms"]), len(data["porting"]["network_contracts"])))
    if s.get("vm_obfuscation") not in ("none", "unknown", None):
        # Loud on stderr as well as in the file: a run whose output does not
        # describe the module must not look like an ordinary success.
        sys.stderr.write("WARNING: VM obfuscation %s (score %s) -- the extracted "
                         "functions are interpreter internals, not module logic\n" % (
                             s["vm_obfuscation"], data["vm_signals"].get("score")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
