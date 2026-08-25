#!/usr/bin/env python3
"""Query an existing .xrayjs directory without loading the whole thing.

Reverse engineering obfuscated code is iterative: find a symbol, see who calls
it, read its source, move to the next one. Answering each of those by reading
all of xray.json costs the same ~15k tokens whether the answer is one line or
the whole file, and after four questions the context is gone. This CLI makes the
cost proportional to the answer.

It is a *reader*, not a stage. Every value it prints was already decided by
explain.py and written to an artifact; nothing here re-classifies a role,
re-judges an algorithm or recomputes an importance score. That restraint is the
whole point: a query tool that derived its own answers would drift from
xray.json, and the caller would have no way to tell which of the two was lying.

Where a label is needed for a function xray.json did not detail -- it publishes
only the top --top functions by importance, out of every function in
structure.json -- the label comes from importing explain.display_name, the same
function that produced the published names, rather than a second implementation
of the same convention.

The first argument names the run, and may be left out. An explicit .xrayjs
directory always wins; a source file resolves to the <stem>.xrayjs beside it;
nothing at all resolves to the single .xrayjs directory in the current one. Two
candidates are reported rather than picked between -- answering the right
question about the wrong file is the one failure a caller cannot detect from the
answer.
"""
import argparse
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, HERE)

import explain  # noqa: E402  -- display_name, so labels match xray.json exactly
import report  # noqa: E402  -- PORT_SNIPPETS via port_snippet(), not copied

SCHEMA = "js-xray/explanation/1"

# How much source "show" prints before truncating. An obfuscated function of 40
# lines is already at the edge of what is worth spending context on; --full is
# there for when it is worth it.
SRC_LIMIT = 40


class Missing(Exception):
    """A required artifact is absent. Says which file, and which flag needed it."""


# ---------------------------------------------------------------- loading

class Run:
    """Lazy access to one .xrayjs directory.

    Artifacts load on first use so "summary" never pays for structure.json (230KB
    on the sample), and a directory missing an optional artifact still answers
    every question that does not need it.
    """

    def __init__(self, path, spec=None):
        self.dir = path
        if not os.path.isdir(path):
            raise Missing("not a directory: %s" % path)
        # How the caller named this run, for the commands we suggest back to them.
        # Echoing self.dir would hand a full path to someone who did not type one,
        # teaching the long form the resolution exists to avoid.
        self.spec = spec
        self._xray = None
        self._structure = None
        self._clean = None
        self._report = None
        self._index = None

    def _read_json(self, name):
        p = os.path.join(self.dir, name)
        if not os.path.isfile(p):
            raise Missing("%s not found in %s" % (name, self.dir))
        try:
            with open(p, encoding="utf-8") as fh:
                return json.load(fh)
        except ValueError as exc:
            raise Missing("%s is not valid JSON: %s" % (name, exc))

    @property
    def xray(self):
        if self._xray is None:
            data = self._read_json("xray.json")
            got = data.get("schema")
            # Loud, not lenient. A later schema could keep these field names and
            # change what they mean, and answering from it anyway would hand back
            # a confident wrong answer -- the one failure mode this tool must not
            # have, since the caller asked precisely to avoid reading the file.
            if got != SCHEMA:
                raise Missing(
                    "xray.json has schema %r, expected %r. This xq reads only %s; "
                    "re-run the pipeline, or use the xq that shipped with that "
                    "schema." % (got, SCHEMA, SCHEMA))
            self._xray = data
        return self._xray

    @property
    def structure(self):
        if self._structure is None:
            self._structure = self._read_json("structure.json")
        return self._structure

    @property
    def clean(self):
        """clean.js as a list of lines, 0-based: line N of xray.json is [N-1]."""
        if self._clean is None:
            p = os.path.join(self.dir, "clean.js")
            if not os.path.isfile(p):
                raise Missing("clean.js not found in %s" % self.dir)
            with open(p, encoding="utf-8", errors="replace") as fh:
                self._clean = fh.read().splitlines()
        return self._clean

    # -------------------------------------------------------- symbol index

    @property
    def index(self):
        """id -> {id, name, lines, detail?} for every function we can name.

        Three tiers, in descending order of what they can answer:

          1. xray.json functions[] -- the canonical detail, carried verbatim
             under "detail".
          2. every other id xray.json mentions (entry points, flow steps,
             porting entries) -- name and line as published there.
          3. structure.json, when present -- the remaining ids, labelled with
             explain.display_name.

        Tier 1 always wins, so a function detailed in xray.json is reported from
        xray.json even though structure.json also describes it.
        """
        if self._index is not None:
            return self._index
        idx = {}
        x = self.xray

        def note(fid, name, line=None, end=None):
            if not fid:
                return
            cur = idx.setdefault(fid, {"id": fid, "name": name,
                                       "lines": [line, end], "detail": None})
            if cur["name"] is None:
                cur["name"] = name
            if cur["lines"][0] is None and line is not None:
                cur["lines"] = [line, end]

        for fn in x.get("functions") or []:
            idx[fn["id"]] = {"id": fn["id"], "name": fn.get("name"),
                             "lines": list(fn.get("lines") or [None, None]),
                             "detail": fn}
        for ep in x.get("entry_points") or []:
            note(ep.get("id"), ep.get("name"), ep.get("line"))
        for flow in x.get("flows") or []:
            entry = flow.get("entry") or {}
            note(entry.get("id"), entry.get("name"), entry.get("line"))
            for step in flow.get("steps") or []:
                note(step.get("id"), step.get("name"), step.get("line"))
        porting = x.get("porting") or {}
        for algo in porting.get("algorithms") or []:
            lines = algo.get("lines") or [None, None]
            note(algo.get("id"), algo.get("function"), lines[0],
                 lines[1] if len(lines) > 1 else None)
        for net in porting.get("network_contracts") or []:
            note(net.get("id"), net.get("function"), net.get("line"))

        # Tier 3. structure.json is optional here: without it we still answer
        # about everything xray.json named, which is what most questions are
        # about anyway.
        try:
            struct = self.structure
        except Missing:
            struct = None
        if struct:
            by_id = explain.build_index(struct)
            for fn in struct.get("functions") or []:
                fid = fn["id"]
                if fid in idx and idx[fid]["detail"] is not None:
                    idx[fid]["raw_name"] = idx[fid]["detail"].get("raw_name")
                    idx[fid]["kind"] = idx[fid]["detail"].get("kind")
                    continue
                label = explain.display_name(fn, by_id)
                if fid in idx:
                    if idx[fid]["lines"][0] is None:
                        idx[fid]["lines"] = [fn.get("start_line"), fn.get("end_line")]
                    elif idx[fid]["lines"][1] is None:
                        idx[fid]["lines"][1] = fn.get("end_line")
                    if idx[fid]["name"] is None:
                        idx[fid]["name"] = label
                else:
                    idx[fid] = {"id": fid, "name": label,
                                "lines": [fn.get("start_line"), fn.get("end_line")],
                                "detail": None}
                idx[fid]["raw_name"] = fn.get("name")
                idx[fid]["kind"] = fn.get("kind")
        for entry in idx.values():
            if "raw_name" not in entry:
                entry["raw_name"] = (entry.get("detail") or {}).get("raw_name")
        self._index = idx
        return idx

    def resolve(self, token):
        """A function id or name -> the matching index entries.

        Exact id, then exact display name, then exact raw name, then a
        case-insensitive substring. Each tier returns alone: an exact match for
        "on" must not arrive buried under every name containing "on".
        """
        idx = self.index
        if token in idx:
            return [idx[token]]
        for key in ("name", "raw_name"):
            hits = [e for e in idx.values() if e.get(key) == token]
            if hits:
                return sorted(hits, key=_sort_key)
        low = token.lower()
        hits = [e for e in idx.values()
                if low in (e.get("name") or "").lower()
                or low in (e.get("raw_name") or "").lower()]
        return sorted(hits, key=_sort_key)


def _sort_key(entry):
    detail = entry.get("detail") or {}
    # Functions xray.json details come first, ordered by the importance it
    # assigned them; the rest fall back to source position.
    return (0 if detail else 1, -(detail.get("importance") or 0),
            entry["lines"][0] if entry["lines"][0] is not None else 1 << 30,
            entry["id"])


# ---------------------------------------------------------------- vm banner

def vm_verdict(run):
    return (run.xray.get("summary") or {}).get("vm_obfuscation")


def vm_banner(run):
    """One line, first, when the analysed file is a bytecode interpreter.

    An agent asking what function X does on a VM-obfuscated file gets a truthful
    answer about an interpreter part, and will report it as the module behaviour
    unless told here. Deliberately short: it has to be cheap enough to print on
    every answer.
    """
    verdict = vm_verdict(run)
    if verdict == "vm-obfuscated":
        return ["! VM-obfuscated (summary.vm_obfuscation=vm-obfuscated): this file is "
                "a bytecode interpreter. What follows describes the VM -- its dispatch "
                "loop and operand decoding -- not the module logic. Evidence in "
                "vm_signals."]
    if verdict == "suspected":
        return ["! VM obfuscation suspected (summary.vm_obfuscation=suspected): some of "
                "this is likely interpreter internals rather than module logic. Check "
                "vm_signals[].line against clean.js."]
    return []


# ---------------------------------------------------------------- helpers

def loc(lines):
    if not isinstance(lines, list) or not lines:
        return "L?"
    a = lines[0]
    b = lines[1] if len(lines) > 1 else None
    if a is None:
        return "L?"
    if b is None or b == a:
        return "L%s" % a
    return "L%s-%s" % (a, b)


def top_role(detail):
    """The first named role in the order explain.py wrote them. Never re-ranked."""
    for role in (detail or {}).get("roles") or []:
        if role.get("role") != "unclassified":
            return role
    return None


def role_label(detail):
    role = top_role(detail)
    if not role:
        return "-"
    return "%s (%s)" % (role["role"], role["confidence"])


def compile_pattern(pattern, literal=False):
    """Regex when it compiles, plain substring otherwise.

    Obfuscated identifiers look like "$", "t[", "(?" -- either invalid regexes or
    surprising ones. Falling back beats making the caller escape them.
    """
    if literal:
        return re.compile(re.escape(pattern), re.IGNORECASE), False
    try:
        return re.compile(pattern, re.IGNORECASE), True
    except re.error:
        return re.compile(re.escape(pattern), re.IGNORECASE), False


def pick(run, token, out):
    """Resolve to exactly one function, or explain why we cannot."""
    hits = run.resolve(token)
    if not hits:
        out.append("no function matches %r. Try: xq %sfind %s"
                   % (token, (run.spec + " ") if run.spec else "", token))
        return None
    if len(hits) > 1:
        out.append("%d functions match %r; re-run with an id:" % (len(hits), token))
        for e in hits[:20]:
            out.append("  %-8s %-44s %s" % (e["id"], e["name"] or "-", loc(e["lines"])))
        if len(hits) > 20:
            out.append("  ... %d more" % (len(hits) - 20))
        return None
    return hits[0]


# ---------------------------------------------------------------- subcommands

def cmd_summary(run, args):
    x = run.xray
    s = x.get("summary") or {}
    if args.json:
        return {"summary": s, "vm_signals": x.get("vm_signals"),
                "confidence_notes": x.get("confidence_notes") or [],
                "size": x.get("size"), "deobfuscation": x.get("deobfuscation")}
    out = vm_banner(run)
    if out:
        out.append("")
    size = x.get("size") or {}
    out.append("%s  %s lines, %s bytes" % (
        os.path.basename(x.get("source_file") or run.dir),
        size.get("lines"), size.get("bytes")))
    out.append("functions %s   classes %s   entry_points %s   vm %s" % (
        s.get("functions"), s.get("classes"), s.get("entry_points"),
        s.get("vm_obfuscation") or "unknown"))
    roles = s.get("roles") or {}
    named = [(k, v) for k, v in roles.items() if k != "unclassified"]
    if named:
        out.append("")
        out.append("roles:")
        for role, count in named:
            out.append("  %-40s %s" % (role, count))
        if roles.get("unclassified"):
            out.append("  %-40s %s" % ("(unclassified)", roles["unclassified"]))
    endpoints = s.get("endpoints") or []
    if endpoints:
        out.append("")
        out.append("endpoints:")
        for url in endpoints:
            out.append("  " + str(url))
    deob = x.get("deobfuscation") or {}
    if deob:
        out.append("")
        out.append("deobfuscation: %s strings inlined, %s unresolved, rolled_back=%s"
                   % (deob.get("strings_inlined"), deob.get("unresolved"),
                      deob.get("rolled_back")))
    notes = x.get("confidence_notes") or []
    if notes:
        out.append("")
        out.append("caveats:")
        for note in notes:
            out.append("  - " + note)
    return out


def cmd_find(run, args):
    """Symbol search over names, and over string literals when asked.

    Literals are behind --strings: on a real SDK the string hits outnumber the
    function hits several times over, and find is nearly always asked about a
    symbol.
    """
    rx, is_regex = compile_pattern(args.pattern, args.literal)
    fn_hits = [e for e in run.index.values()
               if rx.search(e.get("name") or "") or rx.search(e.get("raw_name") or "")]
    fn_hits.sort(key=_sort_key)
    truncated = 0
    if args.limit and len(fn_hits) > args.limit:
        truncated = len(fn_hits) - args.limit
        fn_hits = fn_hits[:args.limit]

    str_hits, lit_hits = [], []
    if args.strings:
        try:
            struct = run.structure
        except Missing:
            struct = None
        if struct:
            seen = set()
            for fn in struct.get("functions") or []:
                for lit in fn.get("strings") or []:
                    if rx.search(lit) and (fn["id"], lit) not in seen:
                        seen.add((fn["id"], lit))
                        entry = run.index.get(fn["id"]) or {}
                        str_hits.append({"id": fn["id"], "in": entry.get("name"),
                                         "string": lit})
        literals = run.xray.get("literals") or {}
        for item in literals.get("urls") or []:
            if rx.search(item.get("url") or ""):
                lit_hits.append(item)
        for path in literals.get("paths") or []:
            if rx.search(path):
                lit_hits.append({"url": path, "line": None})

    if args.json:
        return {"pattern": args.pattern, "regex": is_regex,
                "functions": [{"id": e["id"], "name": e["name"], "lines": e["lines"],
                               "role": role_label(e.get("detail")),
                               "importance": (e.get("detail") or {}).get("importance"),
                               "detailed_in_xray": e.get("detail") is not None}
                              for e in fn_hits],
                "omitted_by_limit": truncated,
                "strings": str_hits, "literals": lit_hits}

    out = []
    if not is_regex and not args.literal:
        out.append("(%r is not a valid regex; searched as a literal)" % args.pattern)
    if not fn_hits and not str_hits and not lit_hits:
        out.append("no match for %r" % args.pattern)
        return out
    for e in fn_hits:
        detail = e.get("detail")
        imp = "" if detail is None else "  imp=%s" % detail.get("importance")
        mark = " " if detail is not None else "~"
        out.append("%s%-8s %-42s %-11s %s%s" % (
            mark, e["id"], e["name"] or "-", loc(e["lines"]),
            role_label(detail), imp))
    if truncated:
        out.append("... %d more, raise --limit" % truncated)
    if any(e.get("detail") is None for e in fn_hits):
        out.append("")
        out.append("~ named from structure.json; xray.json details only its top "
                   "functions[], so there is no role or importance for these")
    if str_hits:
        out.append("")
        out.append("string literals:")
        for hit in str_hits[:args.limit or 40]:
            out.append("  %-8s %-30s %r" % (hit["id"], hit["in"] or "-", hit["string"]))
    if lit_hits:
        out.append("")
        out.append("url/path literals:")
        for hit in lit_hits:
            where = " (L%s)" % hit["line"] if hit.get("line") else ""
            out.append("  %s%s" % (hit["url"], where))
    return out


def source_of(run, entry, args):
    """(lines, omitted_count) from clean.js for an entry line range."""
    lines_field = entry["lines"] or [None]
    start = lines_field[0]
    end = lines_field[1] if len(lines_field) > 1 else None
    if start is None:
        return None, 0
    try:
        lines = run.clean
    except Missing:
        return None, 0
    body = lines[start - 1:(end or start)]
    limit = None if args.full else (args.lines or SRC_LIMIT)
    if limit is not None and len(body) > limit:
        return body[:limit], len(body) - limit
    return body, 0


def cmd_show(run, args):
    out = []
    entry = pick(run, args.name, out)
    if entry is None:
        return out
    detail = entry.get("detail")
    src, omitted = source_of(run, entry, args)

    if args.json:
        # "function" is the xray.json functions[] entry itself, unmodified, so a
        # caller comparing the two gets equality rather than a shape that merely
        # resembles it.
        return {"id": entry["id"], "name": entry["name"], "lines": entry["lines"],
                "function": detail,
                "detailed_in_xray": detail is not None,
                "vm_obfuscation": vm_verdict(run),
                "source": src, "source_omitted": omitted}

    out = vm_banner(run)
    if out:
        out.append("")
    out.append("%s  %s  %s" % (entry["id"], entry["name"] or "-", loc(entry["lines"])))
    if detail is None:
        out.append("")
        out.append("xray.json does not detail this function -- it publishes only its "
                   "top functions[] by importance. Name and lines are from "
                   "structure.json; the source below is the primary answer.")
    else:
        sig = "%s%s(%s)" % ("async " if detail.get("async") else "",
                            detail.get("raw_name") or detail.get("kind") or "",
                            ", ".join(detail.get("params") or []))
        out.append("%s   importance %s   %s" % (
            sig, detail.get("importance"),
            "reached from an entry point" if detail.get("reachable_from_entry")
            else "NOT reached from any entry point"))
        roles = [r for r in detail.get("roles") or []
                 if r.get("role") != "unclassified"]
        if roles:
            out.append("")
            for role in roles:
                line = "role: %s (%s)" % (role["role"], role["confidence"])
                if role.get("inherited_from"):
                    line += " -- inherited from %s" % role["inherited_from"]
                out.append(line)
                for ev in role.get("evidence") or []:
                    out.append("      %s" % ev)
        for label, key in (("calls", "calls"), ("reads", "reads"),
                           ("returns", "returns")):
            vals = detail.get(key) or []
            if vals:
                out.append("")
                out.append("%s: %s" % (label, ", ".join(str(v) for v in vals)))
        for net in detail.get("network") or []:
            out.append("")
            out.append("network: %s %s %s" % (net.get("kind"),
                                              net.get("method") or "", net.get("url")))
            for key in ("url_expression", "body", "credentials", "headers"):
                if net.get(key):
                    out.append("      %s: %s" % (key, net[key]))
        if detail.get("algorithms"):
            out.append("")
            out.append("algorithms: %s"
                       % ", ".join(str(a) for a in detail["algorithms"]))

    if src is None:
        out.append("")
        out.append("(no source: clean.js missing, or no line range for this function)")
        return out
    out.append("")
    out.append("clean.js %s:" % loc(entry["lines"]))
    start = entry["lines"][0] or 1
    width = len(str(start + len(src)))
    for offset, text in enumerate(src):
        out.append("%*d  %s" % (width, start + offset, text))
    if omitted:
        out.append("... %d more lines, use --full" % omitted)
    return out


def function_spans(run):
    """(start, end, entry) per function we can place, for line -> function.

    Spans come from whatever named the function: xray.json lines[] for the
    detailed ones, structure.json start/end for the rest.
    """
    spans = []
    for entry in run.index.values():
        lines_field = entry["lines"] or [None]
        start = lines_field[0]
        end = lines_field[1] if len(lines_field) > 1 else None
        if start is None:
            continue
        spans.append((start, end or start, entry))
    spans.sort(key=lambda s: (s[0], -(s[1] - s[0])))
    return spans


def owner_of(spans, line):
    """The innermost function containing a line -- the one a reader means."""
    best = None
    for start, end, entry in spans:
        if start <= line <= end and (best is None or (end - start) <= (best[1] - best[0])):
            best = (start, end, entry)
    return best[2] if best else None


def cmd_grep(run, args):
    """clean.js search with the owning function attached to every hit.

    Plain grep answers with a line number, which then costs another lookup to
    place. The function is the part the caller wanted.
    """
    rx, is_regex = compile_pattern(args.pattern, args.literal)
    spans = function_spans(run)
    hits, stopped = [], False
    for num, text in enumerate(run.clean, 1):
        if rx.search(text):
            owner = owner_of(spans, num)
            hits.append({"line": num, "text": text.strip()[:args.width],
                         "id": owner["id"] if owner else None,
                         "in": owner["name"] if owner else None})
            if args.limit and len(hits) >= args.limit:
                stopped = True
                break
    if args.json:
        return {"pattern": args.pattern, "regex": is_regex, "hits": hits,
                "stopped_at_limit": stopped}
    out = []
    if not is_regex and not args.literal:
        out.append("(%r is not a valid regex; searched as a literal)" % args.pattern)
    if not hits:
        out.append("no match for %r in clean.js" % args.pattern)
        return out
    for hit in hits:
        out.append("%6d  %-8s %-32s  %s" % (
            hit["line"], hit["id"] or "-",
            (hit["in"] or "(top level)")[:32], hit["text"]))
    if stopped:
        out.append("... stopped at --limit %d" % args.limit)
    return out


def cmd_callers(run, args):
    return walk_edges(run, args, "callers")


def cmd_callees(run, args):
    return walk_edges(run, args, "callees")


def walk_edges(run, args, direction):
    out = []
    entry = pick(run, args.name, out)
    if entry is None:
        return out
    cg = run.structure.get("call_graph") or {}
    edges = cg.get("edges") or []
    resolution = cg.get("resolution")

    adjacency = {}
    for edge in edges:
        src, dst = edge.get("from"), edge.get("to")
        if direction == "callers":
            adjacency.setdefault(dst, []).append((src, edge.get("via")))
        else:
            adjacency.setdefault(src, []).append((dst, edge.get("via")))

    seen = {entry["id"]}
    level = [entry["id"]]
    layers = []
    for depth in range(1, args.depth + 1):
        found, nxt = [], []
        for fid in level:
            for other, via in adjacency.get(fid, []):
                found.append({"depth": depth, "id": other, "via": via, "of": fid})
                if other not in seen:
                    seen.add(other)
                    nxt.append(other)
        if not found:
            break
        layers.append(found)
        level = nxt
        if not level:
            break

    def describe(fid):
        e = run.index.get(fid)
        if not e:
            return {"id": fid, "name": None, "lines": [None, None], "role": None}
        return {"id": fid, "name": e["name"], "lines": e["lines"],
                "role": role_label(e.get("detail"))}

    warning = ("call_graph.resolution = %r. Edges match call *names*, so a "
               "shadowed or reassigned identifier can point at the wrong function, "
               "and calls made through a variable or property are missing "
               "entirely. Confirm a path against the source before relying on it."
               % (resolution or "unknown"))

    if args.json:
        return {"of": {"id": entry["id"], "name": entry["name"]},
                "direction": direction,
                "resolution": resolution,
                "warning": warning,
                "layers": [[dict(hit, **describe(hit["id"])) for hit in layer]
                           for layer in layers]}

    out = ["%s of %s %s" % (direction, entry["id"], entry["name"] or "-")]
    if not layers:
        out.append("  none in call_graph.edges")
    for layer in layers:
        for hit in layer:
            info = describe(hit["id"])
            via = "  via %s" % hit["via"] if hit["via"] else ""
            parent = ""
            if hit["depth"] > 1:
                owner = run.index.get(hit["of"]) or {}
                parent = "  <- %s" % (owner.get("name") or hit["of"])
            out.append("  %s%-8s %-38s %-11s%s%s" % (
                "  " * (hit["depth"] - 1), info["id"], info["name"] or "-",
                loc(info["lines"]), via, parent))
    out.append("")
    # Not a footnote: a wrong edge sends a reader down a path that does not exist,
    # and the resolution strategy is the reason it can happen.
    out.append("! " + warning)
    return out


def cmd_flow(run, args):
    out = []
    entry = pick(run, args.name, out)
    if entry is None:
        return out
    target = entry["id"]
    matches = []
    for pos, flow in enumerate(run.xray.get("flows") or []):
        steps = [s for s in flow.get("steps") or [] if s.get("id") == target]
        if (flow.get("entry") or {}).get("id") == target or steps:
            matches.append((pos, flow, steps))

    if args.json:
        return {"of": {"id": target, "name": entry["name"]},
                "vm_obfuscation": vm_verdict(run),
                "flows": [{"index": pos, "entry": flow.get("entry"),
                           "steps": flow.get("steps"),
                           "also_entered_by": flow.get("also_entered_by"),
                           "matched_steps": steps}
                          for pos, flow, steps in matches]}

    out = vm_banner(run)
    if out:
        out.append("")
    if not matches:
        out.append("%s %s appears in no traced flow." % (entry["id"],
                                                         entry["name"] or "-"))
        out.append("Only the top entry points are traced, so flows[] is not "
                   "exhaustive -- try: callers %s" % entry["id"])
        return out
    for pos, flow, steps in matches:
        fentry = flow.get("entry") or {}
        out.append("flow[%d] entry %s (L%s) -- %s" % (
            pos, fentry.get("name"), fentry.get("line"), fentry.get("why")))
        for other in flow.get("also_entered_by") or []:
            out.append("  also entered by %s (L%s)" % (other.get("name"),
                                                       other.get("line")))
        for step in flow.get("steps") or []:
            mark = ">" if step.get("id") == target else " "
            bits = []
            if step.get("does"):
                bits.append(", ".join(step["does"]))
            if step.get("algorithms"):
                bits.append("algorithms: "
                            + ", ".join(str(a) for a in step["algorithms"]))
            for net in step.get("network") or []:
                bits.append("%s %s %s" % (net.get("kind"), net.get("method") or "",
                                          net.get("url")))
            suffix = "  -- " + "; ".join(bits) if bits else ""
            out.append("%s %s%-8s %s (L%s)%s" % (
                mark, "  " * step.get("depth", 0), step.get("id"),
                step.get("name"), step.get("line"), suffix))
        out.append("")
    return out


def cmd_port(run, args):
    porting = run.xray.get("porting") or {}
    algos = porting.get("algorithms") or []
    if args.name:
        low = args.name.lower()
        algos = [a for a in algos
                 if low in (a.get("function") or "").lower()
                 or a.get("id") == args.name
                 or any(low in f.lower() for f in a.get("families") or [])]

    # report.py owns the family -> snippet mapping. Importing it keeps xq and
    # report.md from giving two different answers for one algorithm; a copy here
    # would go stale the first time PORT_SNIPPETS gains an entry.
    def snippets_for(algo):
        found = []
        for family in algo.get("families") or []:
            snippet = report.port_snippet(family, algo.get("multiply_style"))
            if snippet:
                found.append({"family": family, "python": snippet})
        return found

    if args.json:
        return {"vm_obfuscation": vm_verdict(run),
                "algorithms": [dict(a, python_snippets=snippets_for(a)) for a in algos],
                "network_contracts": porting.get("network_contracts") or [],
                "inputs": porting.get("inputs") or [],
                "pitfalls": porting.get("pitfalls") or []}

    out = vm_banner(run)
    if out:
        out.append("")
    if args.name and not algos:
        out.append("no algorithm in porting.algorithms matches %r" % args.name)
        names = [a.get("function") for a in porting.get("algorithms") or []]
        if names:
            out.append("have: %s" % ", ".join(str(n) for n in names))
        else:
            out.append("porting.algorithms is empty for this run")
        return out

    for algo in algos:
        out.append("%s  %s  %s" % (algo.get("id"), algo.get("function"),
                                   loc(algo.get("lines"))))
        out.append("  families:  %s" % (", ".join(algo.get("families") or []) or "-"))
        if algo.get("constants"):
            out.append("  constants: %s" % ", ".join(str(c) for c in algo["constants"]))
        if algo.get("operators"):
            out.append("  operators: %s" % ", ".join(algo["operators"]))
        if algo.get("loops") is not None:
            out.append("  loops:     %s" % algo["loops"])
        if algo.get("multiply_style"):
            out.append("  multiply:  %s -- %s" % (algo["multiply_style"],
                                                  algo.get("multiply_note") or ""))
        for ret in algo.get("returns") or []:
            out.append("  returns:   %s" % ret)
        for snippet in snippets_for(algo):
            out.append("")
            out.append("  %s in Python:" % snippet["family"])
            for line in snippet["python"].splitlines():
                out.append("    " + line)
        if algo.get("multiply_style") == "mixed":
            out.append("  (no snippet: this function mixes multiply styles, so it "
                       "has to be read directly)")
        out.append("")

    # A named lookup is a question about that algorithm; the file-wide sections
    # would bury the answer it asked for.
    if args.name:
        return out

    for net in porting.get("network_contracts") or []:
        out.append("%s %s in %s (L%s)" % (net.get("kind"), net.get("method") or "",
                                          net.get("function"), net.get("line")))
        out.append("  url:   %s" % net.get("url"))
        for key in ("url_expression", "headers", "body", "credentials"):
            if net.get(key):
                out.append("  %-6s %s" % (key + ":", net[key]))
        out.append("")
    inputs = porting.get("inputs") or []
    if inputs:
        shown = inputs[:args.limit] if args.limit else inputs
        out.append("inputs a port must supply (%d):" % len(inputs))
        for item in shown:
            out.append("  %-36s read by %s" % (item.get("property"),
                                               ", ".join(item.get("read_by") or [])))
        if len(inputs) > len(shown):
            out.append("  ... %d more" % (len(inputs) - len(shown)))
        out.append("")
    for pit in porting.get("pitfalls") or []:
        out.append("pitfall: %s" % pit.get("issue"))
        out.append("  %s" % pit.get("detail"))
    return out


def cmd_entries(run, args):
    eps = run.xray.get("entry_points") or []
    if args.json:
        return {"entry_points": eps}
    out = []
    for ep in eps:
        if args.traced and not ep.get("traced"):
            continue
        shares = ep.get("shares_flow_with")
        tail = "  shares flow with %s" % shares if shares else ""
        out.append("%-8s %-42s L%-6s %-7s %s%s" % (
            ep.get("id"), ep.get("name"), ep.get("line"),
            "traced" if ep.get("traced") else "-", ep.get("why") or "", tail))
    if not out:
        out.append("no entry points" + (" are traced" if args.traced else ""))
    return out


def cmd_roles(run, args):
    """Functions carrying a role, or the histogram when no role is named."""
    x = run.xray
    if not args.role:
        counts = (x.get("summary") or {}).get("roles") or {}
        if args.json:
            return {"roles": counts}
        return ["%-40s %s" % (k, v) for k, v in counts.items()]

    low = args.role.lower()
    hits = []
    for fn in x.get("functions") or []:
        for role in fn.get("roles") or []:
            if low in role.get("role", "").lower():
                hits.append({"id": fn["id"], "name": fn["name"], "lines": fn["lines"],
                             "role": role["role"], "confidence": role["confidence"],
                             "evidence": role.get("evidence") or [],
                             "importance": fn.get("importance")})
                break
    note = ("per-function roles exist only for the functions xray.json details; "
            "summary.roles counts every function in the file")
    if args.json:
        return {"role": args.role, "functions": hits, "note": note}
    out = []
    if not hits:
        out.append("no detailed function has a role matching %r" % args.role)
        counts = (x.get("summary") or {}).get("roles") or {}
        if counts:
            out.append("roles in summary: %s" % ", ".join(counts))
        return out
    for hit in hits:
        out.append("%-8s %-42s %-11s %s (%s)" % (
            hit["id"], hit["name"], loc(hit["lines"]),
            hit["role"], hit["confidence"]))
        for ev in hit["evidence"][:3]:
            out.append("         %s" % ev)
    out.append("")
    out.append("(%s)" % note)
    return out


# ---------------------------------------------------------------- cli

COMMANDS = {
    "summary": cmd_summary,
    "find": cmd_find,
    "show": cmd_show,
    "callers": cmd_callers,
    "callees": cmd_callees,
    "flow": cmd_flow,
    "port": cmd_port,
    "grep": cmd_grep,
    "entries": cmd_entries,
    "roles": cmd_roles,
}

# Commands that cannot answer without a given artifact. Checked up front so the
# error names the missing file and the command that needed it, instead of the
# question coming back mysteriously empty.
NEEDS_STRUCTURE = ("callers", "callees")
NEEDS_CLEAN = ("grep",)


# ------------------------------------------------------------ target resolution

SUFFIX = ".xrayjs"


class Ambiguous(Exception):
    """More than one run could have been meant. Lists them; picks none.

    Separate from Missing because the two want opposite handling: a missing
    artifact is a fact about one run, while this is a question the caller has to
    answer. Guessing here would produce a well-formed answer about the wrong
    file, which nothing downstream can catch.
    """


def _xrayjs_dirs(where):
    """The .xrayjs directories directly inside 'where', sorted.

    One level only. Recursing would make the cost of typing "xq summary" depend
    on the size of the tree below the cwd, and would silently reach runs the
    caller cannot see in an ls.
    """
    try:
        names = os.listdir(where)
    except OSError:
        return []
    return sorted(os.path.join(where, n) for n in names
                  if n.endswith(SUFFIX) and os.path.isdir(os.path.join(where, n)))


def resolve_target(spec, cwd=None):
    """Return (directory, how) for a first argument that may be absent.

    Priority, in order:
      1. an existing directory, used verbatim -- keeps every explicit path that
         worked before working, including plain directories the tests build by
         hand, and lets an explicit path win over a subcommand of the same name
      2. a file path: the sibling <stem>.xrayjs
      3. no path at all: the one .xrayjs in the cwd, or a refusal
    """
    cwd = cwd or os.getcwd()
    if spec is not None:
        if os.path.isdir(spec):
            return spec, "explicit"
        if os.path.isfile(spec):
            stem = os.path.splitext(spec)[0]
            paired = stem + SUFFIX
            if os.path.isdir(paired):
                return paired, "paired with %s" % os.path.basename(spec)
            raise Missing(
                "%s has not been analysed: %s does not exist. Run: python3 "
                "skill/scripts/xray.py %s" % (os.path.basename(spec),
                                              os.path.basename(paired), spec))
        # neither: report it as the path it looks like, not as a bad subcommand
        raise Missing("no such file or directory: %s" % spec)

    found = _xrayjs_dirs(cwd)
    if len(found) == 1:
        return found[0], "the only %s here" % SUFFIX
    if not found:
        raise Missing(
            "no %s directory in %s. Name one explicitly, or run: python3 "
            "skill/scripts/xray.py <file>.js" % (SUFFIX, cwd))
    raise Ambiguous(
        "%d %s directories in %s -- name the one you mean:\n%s"
        % (len(found), SUFFIX, cwd,
           "\n".join("  " + os.path.basename(p) for p in found)))


def _looks_like_run(path):
    """Is this directory a run, rather than a directory that shares a name with a
    subcommand? Ordinary source trees do have a port/ or find/; a run has the
    suffix or an xray.json in it."""
    if not os.path.isdir(path):
        return False
    return path.rstrip(os.sep).endswith(SUFFIX) or \
        os.path.isfile(os.path.join(path, "xray.json"))


def split_target(argv):
    """Peel an optional leading target off argv.

    argparse cannot express "one positional that is either a path or the start of
    a subcommand", so the split happens first: the target is present only when
    the first non-flag token is not a subcommand name -- unless a run directory
    of exactly that name is sitting there, in which case the explicit path wins.
    The check is for a run and not merely a directory, so an ordinary port/ or
    find/ in a source tree does not swallow the subcommand of the same name.
    """
    for i, tok in enumerate(argv):
        if tok in ("-h", "--help"):
            return None, list(argv)
        if tok.startswith("-") and tok != "-":
            continue  # a global flag such as --json, kept for argparse
        if tok in COMMANDS and os.sep not in tok and not _looks_like_run(tok):
            return None, list(argv)
        return tok, list(argv[:i]) + list(argv[i + 1:])
    return None, list(argv)


def build_parser():
    ap = argparse.ArgumentParser(
        prog="xq",
        usage="xq [TARGET] [--json] <subcommand> [args]",
        description="Query an .xrayjs directory one answer at a time, instead of "
                    "re-reading all of xray.json for every question.",
        epilog="TARGET is an .xrayjs directory, or the .js file beside one. Omit it "
               "to use the only .xrayjs directory in the current directory; when "
               "there are several, xq lists them instead of choosing.")
    # TARGET is deliberately not a positional here: an optional positional in
    # front of subparsers swallows the subcommand name, so split_target() removes
    # it from argv before argparse ever sees it.
    ap.add_argument("--json", action="store_true",
                    help="machine-readable output; values verbatim from the artifacts")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("summary", help="what this file is, plus the caveats. Start here.")

    p = sub.add_parser("find", help="search function names, and --strings for literals")
    p.add_argument("pattern")
    p.add_argument("--strings", action="store_true",
                   help="also search string literals and url/path literals")
    p.add_argument("--literal", action="store_true",
                   help="never treat the pattern as a regex")
    p.add_argument("--limit", type=int, default=40)

    p = sub.add_parser("show", help="everything about one function, with its source")
    p.add_argument("name", help="id (fn197) or name (on)")
    p.add_argument("--full", action="store_true", help="print every source line")
    p.add_argument("--lines", type=int,
                   help="source lines to print (default %d)" % SRC_LIMIT)

    for name, helptext in (("callers", "who calls this"),
                           ("callees", "what this calls")):
        p = sub.add_parser(name, help=helptext + ", from call_graph.edges")
        p.add_argument("name")
        p.add_argument("--depth", type=int, default=1)

    p = sub.add_parser("flow", help="only the flows this function appears in")
    p.add_argument("name")

    p = sub.add_parser("port",
                       help="porting spec: algorithms, contracts, inputs, pitfalls")
    p.add_argument("name", nargs="?", help="algorithm name, id or family; omit for all")
    p.add_argument("--all", action="store_true", help="explicit form of omitting name")
    p.add_argument("--limit", type=int, default=40)

    p = sub.add_parser("grep", help="search clean.js, with the owning function per hit")
    p.add_argument("pattern")
    p.add_argument("--literal", action="store_true",
                   help="never treat the pattern as a regex")
    p.add_argument("--limit", type=int, default=60)
    p.add_argument("--width", type=int, default=120,
                   help="max chars printed per matched line")

    p = sub.add_parser("entries", help="entry points")
    p.add_argument("--traced", action="store_true", help="only the traced ones")

    p = sub.add_parser("roles", help="functions with a role, or the histogram")
    p.add_argument("role", nargs="?", help="role substring; omit for the histogram")

    return ap


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    spec, rest = split_target(argv)
    if spec in COMMANDS and not any(tok in COMMANDS for tok in rest):
        # A run directory named after a subcommand took priority as a path, and
        # now nothing is left to run. Say so: argparse would only report a missing
        # argument, which reads like a bug in the caller's command line.
        print("xq: %r is both a subcommand and a run directory here, and was taken "
              "as the directory. Write %r to keep it as the path, or run it from "
              "elsewhere." % (spec, os.path.join(os.curdir, spec)), file=sys.stderr)
        return 2
    args = build_parser().parse_args(rest)
    if getattr(args, "all", False):
        args.name = None
    try:
        target, how = resolve_target(spec)
        # stderr, always: stdout stays the answer alone, so a caller parsing it
        # (or diffing --json) is unaffected by the convenience.
        if how != "explicit":
            print("xq: %s (%s)" % (os.path.basename(target.rstrip(os.sep)), how),
                  file=sys.stderr)
        run = Run(target, spec=spec)
        if args.cmd in NEEDS_STRUCTURE:
            run.structure
        if args.cmd in NEEDS_CLEAN:
            run.clean
        result = COMMANDS[args.cmd](run, args)
    except Ambiguous as exc:
        print("xq: %s" % exc, file=sys.stderr)
        return 3
    except Missing as exc:
        print("xq: %s" % exc, file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(result, indent=1, ensure_ascii=False))
    else:
        print("\n".join(str(line) for line in result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
