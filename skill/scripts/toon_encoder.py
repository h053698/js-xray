#!/usr/bin/env python3
"""Pure-stdlib encoder from JSON-model values to TOON (Token-Oriented Object Notation).

Implements the encoder side of the TOON v4.1 specification
(https://github.com/toon-format/spec, SPEC.md, 2026-07-26 working draft):
encode(value) -> str. No third-party dependencies.

Scope: this encoder targets the comma delimiter only (TOON's default and the
only one js-xray needs). Tab/pipe document delimiters (SPEC S11) are out of
scope -- comma covers every form this module emits.

Supported input: any value that round-trips through json.loads(json.dumps(x)),
i.e. dict, list, str, int, float, bool, None, recursively. Non-finite floats
(NaN, +Infinity, -Infinity) are normalized to null per SPEC S3.

Encoder options implemented: indent_size (default 2). Delimiter is fixed at
comma; strict decoding options do not apply (this module is encode-only).

Usage:
    python3 toon_encoder.py input.json [output.toon]
    (or) import toon_encoder; toon_encoder.encode(value)
"""
import json
import math
import re
import sys

DELIM = ","  # document + active delimiter: comma only (see module docstring)
INDENT_UNIT = "  "  # SPEC S12: default indentSize = 2 spaces

_UNQUOTED_KEY_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_.]*$")  # SPEC S7.3
_NUMERIC_LIKE_RE = re.compile(r"^[+-]?[0-9]+(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?$")  # SPEC S7.2

# SPEC S7.1: escape table, matched top-to-bottom, first match wins.
_ESCAPES = (
    ("\\", "\\\\"),
    ('"', '\\"'),
    ("\n", "\\n"),
    ("\r", "\\r"),
    ("\t", "\\t"),
)


class ToonEncodeError(ValueError):
    """Raised when a value cannot be represented in TOON (SPEC S3)."""


def _escape_codepoint(ch):
    cp = ord(ch)
    if 0 <= cp <= 0x1F and ch not in ("\n", "\r", "\t"):
        return "\\u%04x" % cp
    return ch


def _escape_string(s):
    """Escape a string's contents per SPEC S7.1 (used inside quotes)."""
    out = []
    for ch in s:
        replaced = None
        for raw, esc in _ESCAPES:
            if ch == raw:
                replaced = esc
                break
        if replaced is not None:
            out.append(replaced)
        else:
            out.append(_escape_codepoint(ch))
    return "".join(out)


def _has_unpaired_surrogate(s):
    for ch in s:
        cp = ord(ch)
        if 0xD800 <= cp <= 0xDFFF:
            return True
    return False


def _quote_string(s):
    if _has_unpaired_surrogate(s):
        raise ToonEncodeError(
            "string contains an unpaired surrogate and is not representable in TOON: %r" % s
        )
    return '"' + _escape_string(s) + '"'


def _needs_quote_key(key):
    """SPEC S7.3: object keys, entry keys, and field names."""
    return not _UNQUOTED_KEY_RE.match(key)


def encode_key(key):
    if not isinstance(key, str):
        raise ToonEncodeError("object keys must be strings, got %r" % (key,))
    if _needs_quote_key(key):
        return _quote_string(key)
    return key


def _string_needs_quote(s, delim):
    """SPEC S7.2: quoting rules for string values (delimiter-aware, S11.1)."""
    if s == "":
        return True
    if s[0] in (" ", "\t") or s[-1] in (" ", "\t"):
        return True
    if s in ("true", "false", "null"):
        return True
    if _NUMERIC_LIKE_RE.match(s):
        return True
    if ":" in s or '"' in s or "\\" in s:
        return True
    if any(c in s for c in "[]{}"):
        return True
    if any(0x00 <= ord(c) <= 0x1F for c in s):
        return True
    if delim in s:
        return True
    if s == "-" or s.startswith("-"):
        return True
    if s == "#" or s.startswith("#"):
        return True
    return False


def _format_number(n):
    """SPEC S2: canonical decimal number form."""
    if isinstance(n, bool):
        raise ToonEncodeError("internal error: bool must be handled before number formatting")
    if isinstance(n, float):
        if math.isnan(n) or math.isinf(n):
            return "null"
        if n == 0.0:
            return "0"
        if n.is_integer() and abs(n) < 1e21:
            return _format_number(int(n))
        if 1e-6 <= abs(n) < 1e21:
            text = repr(n)
            if "e" in text or "E" in text:
                from decimal import Decimal
                text = format(Decimal(repr(n)), "f")
            if "." in text:
                text = text.rstrip("0").rstrip(".")
                if text in ("", "-"):
                    text = "0"
            return text
        text = repr(n)
        if "e" not in text and "E" not in text:
            text = "%e" % n
        mantissa, _, exponent = text.lower().partition("e")
        if "." in mantissa:
            mantissa = mantissa.rstrip("0").rstrip(".")
        exp_sign = "+" if not exponent.startswith("-") else "-"
        exp_digits = exponent.lstrip("+-").lstrip("0") or "0"
        return "%se%s%s" % (mantissa, exp_sign, exp_digits)
    if n == 0:
        return "0"
    return str(int(n))


def _encode_primitive(value, delim=DELIM):
    """Encode one primitive to its TOON token, quoting per SPEC S7.2/S11.1."""
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
            return "null"
        return _format_number(value)
    if isinstance(value, str):
        if _string_needs_quote(value, delim):
            return _quote_string(value)
        return value
    raise ToonEncodeError("not a JSON primitive: %r" % (value,))


def _is_primitive(v):
    return v is None or isinstance(v, (bool, int, float, str))


def _object_keys_signature(obj):
    """Order-independent signature of an object's key set, for uniformity checks."""
    return frozenset(obj.keys())


def _classify_column(values):
    """SPEC S9.3 column classification: 'primitive', 'nested', or None (disqualified).

    values: list of the column's values across all rows (already known to be
    either all primitives-ok or all-object candidates by the caller's shape
    check -- this function performs the actual per-column judgement).
    """
    if all(_is_primitive(v) for v in values):
        return "primitive"
    if all(isinstance(v, dict) and not isinstance(v, list) and len(v) > 0 for v in values):
        sigs = [_object_keys_signature(v) for v in values]
        if len(set(sigs)) != 1:
            return None
        # every sub-column must itself be uniform-primitive or nested-uniform
        first_keys = list(values[0].keys())
        for k in first_keys:
            sub_values = [v[k] for v in values]
            if _classify_column(sub_values) is None:
                return None
        return "nested"
    return None


def _tabular_field_plan(objects):
    """Return the ordered field plan for a uniform array of objects, or None.

    A field plan is a list of (name, kind, subplan) where kind is 'primitive'
    or 'nested'; subplan is None for primitive fields and a nested field plan
    for nested fields. Returns None if the objects do not qualify for tabular
    form per SPEC S9.3.
    """
    if not objects:
        return None
    if not all(isinstance(o, dict) for o in objects):
        return None
    if any(len(o) == 0 for o in objects):
        return None  # empty object disqualifies tabular form (S9.3)
    sigs = [_object_keys_signature(o) for o in objects]
    if len(set(sigs)) != 1:
        return None
    field_order = list(objects[0].keys())
    plan = []
    for name in field_order:
        col_values = [o[name] for o in objects]
        kind = _classify_column(col_values)
        if kind is None:
            return None
        if kind == "primitive":
            plan.append((name, "primitive", None))
        else:
            sub_plan = _tabular_field_plan(col_values)
            if sub_plan is None:
                return None
            plan.append((name, "nested", sub_plan))
    return plan


def _flatten_row(obj, plan, delim=DELIM):
    """Depth-first pre-order walk of the field plan, producing leaf tokens for one row."""
    cells = []
    for name, kind, sub_plan in plan:
        value = obj[name]
        if kind == "primitive":
            cells.append(_encode_primitive(value, delim))
        else:
            cells.extend(_flatten_row(value, sub_plan, delim))
    return cells


def _field_header(plan, delim=DELIM):
    """Render a field plan as the header's {..} field-list text (SPEC S6, S9.3)."""
    parts = []
    for name, kind, sub_plan in plan:
        key_text = encode_key(name)
        if kind == "primitive":
            parts.append(key_text)
        else:
            parts.append(key_text + "{" + _field_header(sub_plan, delim) + "}")
    return delim.join(parts)


def _keyed_tabular_field_plan(entry_values):
    """Like _tabular_field_plan but for keyed-tabular object detection (SPEC S9.5).

    entry_values: list of the object's *values* (each itself expected to be a dict).
    Requires >= 2 entries per SPEC S9.5.
    """
    if len(entry_values) < 2:
        return None
    return _tabular_field_plan(entry_values)


def _is_array_of_arrays_of_primitives(arr):
    return all(isinstance(v, list) for v in arr) and all(
        all(_is_primitive(x) for x in v) for v in arr
    )


def _encode_inline_array(values, delim=DELIM):
    """SPEC S9.1: primitive array inline form body (values after the header colon)."""
    return delim.join(_encode_primitive(v, delim) for v in values)


def _lines_for_value_as_object_field(key, value, depth, delim=DELIM):
    """Encode one object field 'key: ...' (or its multi-line block form) at depth.

    Returns a list of text lines (without leading indent; indent is applied by
    the caller for the first line, and by recursive calls for nested lines).
    Each line here is already the *full* line content for its own depth; the
    caller is responsible only for the top-level indent of the first line
    when it differs (list-item hyphen lines), see _encode_list_item_object.
    """
    key_text = encode_key(key)
    return _lines_for_keyed_value(key_text, value, depth, delim)


def _lines_for_keyed_value(key_text, value, depth, delim=DELIM):
    """Shared core: render 'key_text: ...' for any JsonValue at the given depth.

    key_text is the already-encoded (quoted if needed) key. Returns full lines
    (each prefixed with INDENT_UNIT * depth).
    """
    pad = INDENT_UNIT * depth
    if _is_primitive(value):
        return [pad + key_text + ": " + _encode_primitive(value, delim)]

    if isinstance(value, list):
        return _lines_for_keyed_array(key_text, value, depth, delim)

    if isinstance(value, dict):
        return _lines_for_keyed_object(key_text, value, depth, delim)

    raise ToonEncodeError("unsupported value type: %r" % (value,))


def _lines_for_keyed_array(key_text, arr, depth, delim=DELIM):
    pad = INDENT_UNIT * depth
    n = len(arr)

    if n == 0:
        # SPEC S9.1: empty arrays in object-field position -> "key: []"
        return [pad + key_text + ": []"]

    if all(_is_primitive(v) for v in arr):
        # SPEC S9.1: inline form
        header = "%s%s[%d]: %s" % (pad, key_text, n, _encode_inline_array(arr, delim))
        return [header]

    if all(isinstance(v, dict) for v in arr):
        plan = _tabular_field_plan(arr)
        if plan is not None:
            # SPEC S9.3: tabular form
            header = "%s%s[%d]{%s}:" % (pad, key_text, n, _field_header(plan, delim))
            lines = [header]
            for obj in arr:
                row_cells = _flatten_row(obj, plan, delim)
                lines.append(INDENT_UNIT * (depth + 1) + delim.join(row_cells))
            return lines
        # fall through to list form (S9.4) for non-uniform object arrays

    # SPEC S9.2 / S9.4: list form
    header = "%s%s[%d]:" % (pad, key_text, n)
    lines = [header]
    for item in arr:
        lines.extend(_lines_for_list_item(item, depth + 1, delim))
    return lines


def _lines_for_keyed_object(key_text, obj, depth, delim=DELIM):
    pad = INDENT_UNIT * depth

    if len(obj) == 0:
        # SPEC S8: empty object -> "key:" with nothing nested
        return [pad + key_text + ":"]

    keyed_plan = _keyed_tabular_detect(obj)
    if keyed_plan is not None:
        # SPEC S9.5: keyed tabular form
        n = len(obj)
        header = "%s%s[%d:]{%s}:" % (pad, key_text, n, _field_header(keyed_plan, delim))
        lines = [header]
        for entry_key, entry_value in obj.items():
            entry_key_text = encode_key(entry_key)
            row_cells = _flatten_row(entry_value, keyed_plan, delim)
            lines.append(
                INDENT_UNIT * (depth + 1) + entry_key_text + ": " + delim.join(row_cells)
            )
        return lines

    # SPEC S8: nested object, one field per line at depth+1
    lines = [pad + key_text + ":"]
    for field_key, field_value in obj.items():
        lines.extend(_lines_for_value_as_object_field(field_key, field_value, depth + 1, delim))
    return lines


def _keyed_tabular_detect(obj):
    """SPEC S9.5 detection: object has >=2 entries, all values uniform non-empty objects."""
    if len(obj) < 2:
        return None
    values = list(obj.values())
    if not all(isinstance(v, dict) and len(v) > 0 for v in values):
        return None
    return _tabular_field_plan(values)


def _lines_for_list_item(item, depth, delim=DELIM):
    """SPEC S9.2/S9.4/S10: encode one array element as a '- ...' list item at depth.

    depth here is the depth *of the hyphen line itself* (item depth), matching
    the outer array header's depth + 1.
    """
    pad = INDENT_UNIT * depth

    if _is_primitive(item):
        return [pad + "- " + _encode_primitive(item, delim)]

    if isinstance(item, list):
        n = len(item)
        if n == 0:
            # SPEC S9.2: empty inner array as a list item -> "- []"
            return [pad + "- []"]
        if all(_is_primitive(v) for v in item):
            return [pad + "- [%d]: %s" % (n, _encode_inline_array(item, delim))]
        # nested array of arrays/objects as a list item: header on hyphen line,
        # items at +1 relative to hyphen line (SPEC S9.4)
        lines = [pad + "- [%d]:" % n]
        for sub_item in item:
            lines.extend(_lines_for_list_item(sub_item, depth + 1, delim))
        return lines

    if isinstance(item, dict):
        return _lines_for_list_item_object(item, depth, delim)

    raise ToonEncodeError("unsupported list item type: %r" % (item,))


def _lines_for_list_item_object(obj, depth, delim=DELIM):
    """SPEC S10: object appearing as a list item."""
    pad = INDENT_UNIT * depth

    if len(obj) == 0:
        return [pad + "-"]

    items = list(obj.items())
    first_key, first_value = items[0]
    rest = items[1:]

    # SPEC S10: if the first field is a tabular array or keyed tabular object,
    # its header goes on the hyphen line itself, with rows/entries at depth+2.
    if isinstance(first_value, list) and len(first_value) > 0 and all(
        isinstance(v, dict) for v in first_value
    ):
        plan = _tabular_field_plan(first_value)
        if plan is not None:
            key_text = encode_key(first_key)
            n = len(first_value)
            lines = [pad + "- %s[%d]{%s}:" % (key_text, n, _field_header(plan, delim))]
            for row_obj in first_value:
                row_cells = _flatten_row(row_obj, plan, delim)
                lines.append(INDENT_UNIT * (depth + 2) + delim.join(row_cells))
            for field_key, field_value in rest:
                lines.extend(
                    _lines_for_value_as_object_field(field_key, field_value, depth + 1, delim)
                )
            return lines

    if isinstance(first_value, dict) and len(first_value) > 0:
        keyed_plan = _keyed_tabular_detect(first_value)
        if keyed_plan is not None:
            key_text = encode_key(first_key)
            n = len(first_value)
            lines = [pad + "- %s[%d:]{%s}:" % (key_text, n, _field_header(keyed_plan, delim))]
            for entry_key, entry_value in first_value.items():
                entry_key_text = encode_key(entry_key)
                row_cells = _flatten_row(entry_value, keyed_plan, delim)
                lines.append(
                    INDENT_UNIT * (depth + 2)
                    + entry_key_text
                    + ": "
                    + delim.join(row_cells)
                )
            for field_key, field_value in rest:
                lines.extend(
                    _lines_for_value_as_object_field(field_key, field_value, depth + 1, delim)
                )
            return lines

    # General case: first field goes on the hyphen line, rest as normal fields
    # at depth+1 (SPEC S10).
    key_text = encode_key(first_key)
    if _is_primitive(first_value):
        first_line = pad + "- " + key_text + ": " + _encode_primitive(first_value, delim)
        lines = [first_line]
    elif isinstance(first_value, list):
        n = len(first_value)
        if n == 0:
            lines = [pad + "- " + key_text + ": []"]
        elif all(_is_primitive(v) for v in first_value):
            lines = [pad + "- " + key_text + "[%d]: %s" % (n, _encode_inline_array(first_value, delim))]
        else:
            lines = [pad + "- " + key_text + "[%d]:" % n]
            for sub_item in first_value:
                lines.extend(_lines_for_list_item(sub_item, depth + 2, delim))
    elif isinstance(first_value, dict):
        if len(first_value) == 0:
            lines = [pad + "- " + key_text + ":"]
        else:
            lines = [pad + "- " + key_text + ":"]
            for field_key, field_value in first_value.items():
                lines.extend(
                    _lines_for_value_as_object_field(field_key, field_value, depth + 2, delim)
                )
    else:
        raise ToonEncodeError("unsupported value type: %r" % (first_value,))

    for field_key, field_value in rest:
        lines.extend(_lines_for_value_as_object_field(field_key, field_value, depth + 1, delim))
    return lines


def _normalize(value):
    """SPEC S3: host-type normalization. NaN/+-Inf -> null; everything else as-is.

    Input is assumed to already be a JSON-model value (dict/list/str/int/float/
    bool/None), i.e. the caller ran it through json.loads(json.dumps(x)) or
    otherwise guarantees JSON-model shape. Only numeric non-finite normalization
    happens here; structural validation happens during encoding itself.
    """
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return None
    if isinstance(value, list):
        return [_normalize(v) for v in value]
    if isinstance(value, dict):
        return {k: _normalize(v) for k, v in value.items()}
    return value


def encode(value, indent_size=2, delimiter=","):
    """Encode a JSON-model value to a TOON v4.1 document (string, no trailing newline).

    value: dict, list, str, int, float, bool, or None (recursively). Any value
        that survives json.loads(json.dumps(value)) is acceptable input.
    indent_size: spaces per indentation level (SPEC S12 default: 2).
    delimiter: must be "," -- this encoder implements the comma delimiter only.

    Returns the TOON document text. Per SPEC S12, encoders MUST NOT emit a
    trailing newline; callers that write to a file should add one themselves
    if their tooling expects EOF-terminated text files.
    """
    if delimiter != ",":
        raise NotImplementedError(
            "this encoder implements the comma delimiter only (got %r)" % (delimiter,)
        )
    global INDENT_UNIT
    prev_indent = INDENT_UNIT
    INDENT_UNIT = " " * indent_size
    try:
        value = _normalize(value)
        delim = delimiter

        if _is_primitive(value):
            # SPEC S5: a single primitive is a valid (if unusual) root form.
            return _encode_primitive(value, delim)

        if isinstance(value, list):
            n = len(value)
            if n == 0:
                # SPEC S9.1: empty root array
                return "[]"
            if all(_is_primitive(v) for v in value):
                return "[%d]: %s" % (n, _encode_inline_array(value, delim))
            if all(isinstance(v, dict) for v in value):
                plan = _tabular_field_plan(value)
                if plan is not None:
                    lines = ["[%d]{%s}:" % (n, _field_header(plan, delim))]
                    for obj in value:
                        row_cells = _flatten_row(obj, plan, delim)
                        lines.append(INDENT_UNIT + delim.join(row_cells))
                    return "\n".join(lines)
            # list form at root
            lines = ["[%d]:" % n]
            for item in value:
                lines.extend(_lines_for_list_item(item, 1, delim))
            return "\n".join(lines)

        if isinstance(value, dict):
            if len(value) == 0:
                # SPEC S8: empty object at root -> empty document
                return ""
            keyed_plan = _keyed_tabular_detect(value)
            if keyed_plan is not None:
                n = len(value)
                lines = ["[%d:]{%s}:" % (n, _field_header(keyed_plan, delim))]
                for entry_key, entry_value in value.items():
                    entry_key_text = encode_key(entry_key)
                    row_cells = _flatten_row(entry_value, keyed_plan, delim)
                    lines.append(
                        INDENT_UNIT + entry_key_text + ": " + delim.join(row_cells)
                    )
                return "\n".join(lines)
            lines = []
            for field_key, field_value in value.items():
                lines.extend(_lines_for_value_as_object_field(field_key, field_value, 0, delim))
            return "\n".join(lines)

        raise ToonEncodeError("unsupported root value type: %r" % (value,))
    finally:
        INDENT_UNIT = prev_indent


# ---------------------------------------------------------------------------
# Decoder
#
# Every rule below is the inverse of an encoder rule above, which is why the two
# live in one module: a decoder in its own file would let one side be edited
# without the other, and the first thing to break would be the round trip.
#
# The judgements are cross-checked against the reference implementation
# (@toon-format/toon 4.1.1, strict mode), because "our encoder round-trips
# through our decoder" is satisfied by two matching misreadings of the spec.
# ---------------------------------------------------------------------------

# SPEC S7.2 as the *decoder* sees it. Deliberately narrower than the encoder's
# _NUMERIC_LIKE_RE: the encoder quotes the wider set (it also treats "+5" and
# "007" as number-like and so quotes those strings), while a bare token only
# becomes a number if it is in canonical S2 form -- no leading "+", no leading
# zeros. Because the encoder quotes the superset, every bare token it emits that
# could be read as a number *is* one, and every string that might have been
# confused for a number arrives quoted. Widening this pattern would start
# turning strings into numbers; narrowing it would turn numbers into strings.
_NUMERIC_LITERAL_RE = re.compile(r"^-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?$")

_LEADING_WS_RE = re.compile(r"^[ \t]*")
_BRACKET_LENGTH_RE = re.compile(r"^(?:0|[1-9][0-9]*)$")

# SPEC S7.1 read backwards: the escapes _ESCAPES writes, plus \uXXXX from
# _escape_codepoint. Anything else after a backslash is a corrupt document, not
# a literal backslash -- the encoder always doubles a real one.
_UNESCAPES = {"n": "\n", "t": "\t", "r": "\r", "\\": "\\", '"': '"'}


class ToonDecodeError(ValueError):
    """Raised when a TOON document cannot be read as written.

    Carries the 1-based line number when one is known. Every count mismatch,
    bad indent and unterminated quote lands here rather than being papered over:
    xq answers questions *from* this data, so a row silently dropped here comes
    back as a confident wrong answer with nothing left to notice it by.
    """

    def __init__(self, message, line=None, source=None):
        self.line = line
        self.source = source
        if line is not None:
            message = "line %d: %s" % (line, message)
            if source is not None:
                message += "\n  %s" % source
        ValueError.__init__(self, message)


def _trim_spaces(text):
    """Strip ASCII spaces only (SPEC S7): a tab or NBSP is part of the token."""
    return text.strip(" ")


def _find_closing_quote(content, start):
    i = start + 1
    while i < len(content):
        if content[i] == "\\" and i + 1 < len(content):
            i += 2
            continue
        if content[i] == '"':
            return i
        i += 1
    return -1


def _find_unquoted_char(content, char, start=0):
    """Index of char outside quoted spans, or -1. Structural scan for ':' '[' etc."""
    in_quotes = False
    i = start
    while i < len(content):
        c = content[i]
        if c == "\\" and i + 1 < len(content) and in_quotes:
            i += 2
            continue
        if c == '"':
            in_quotes = not in_quotes
            i += 1
            continue
        if c == char and not in_quotes:
            return i
        i += 1
    return -1


def _find_matching_brace(content, brace_start):
    in_quotes = False
    depth = 0
    i = brace_start
    while i < len(content):
        c = content[i]
        if c == "\\" and i + 1 < len(content) and in_quotes:
            i += 2
            continue
        if c == '"':
            in_quotes = not in_quotes
            i += 1
            continue
        if not in_quotes:
            if c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    return i
        i += 1
    return -1


def _unescape_string(text, line=None):
    r"""Inverse of _escape_string (SPEC S7.1), including \uXXXX from _escape_codepoint."""
    out = []
    i = 0
    n = len(text)
    while i < n:
        ch = text[i]
        if ch != "\\":
            out.append(ch)
            i += 1
            continue
        if i + 1 >= n:
            raise ToonDecodeError("invalid escape: backslash at end of string", line)
        nxt = text[i + 1]
        if nxt == "u":
            if i + 6 > n:
                raise ToonDecodeError(
                    "invalid escape: truncated \\u escape at %r" % text[i:i + 6], line)
            hexits = text[i + 2:i + 6]
            if not re.match(r"^[0-9a-fA-F]{4}$", hexits):
                raise ToonDecodeError(
                    "invalid escape: \\u must be followed by 4 hex digits, got %r" % hexits,
                    line)
            cp = int(hexits, 16)
            if 0xD800 <= cp <= 0xDFFF:
                # The encoder refuses to write these (see _has_unpaired_surrogate),
                # so one here means the document was not written by this encoder.
                raise ToonDecodeError(
                    "invalid escape: \\u%s is a lone surrogate; supplementary code "
                    "points must appear as literal UTF-8" % hexits, line)
            out.append(chr(cp))
            i += 6
            continue
        if nxt in _UNESCAPES:
            out.append(_UNESCAPES[nxt])
            i += 2
            continue
        raise ToonDecodeError("invalid escape: \\%s" % nxt, line)
    return "".join(out)


def _parse_string_literal(token, line=None):
    """A quoted token to its string; a bare token to itself (keys, field names)."""
    token = _trim_spaces(token)
    if token.startswith('"'):
        close = _find_closing_quote(token, 0)
        if close == -1:
            raise ToonDecodeError("unterminated string: missing closing quote", line)
        if close != len(token) - 1:
            raise ToonDecodeError("unexpected characters after closing quote", line)
        return _unescape_string(token[1:close], line)
    return token


def _parse_number_token(token):
    """The token as int/float, or None when it is not a canonical S2 number.

    Integer-shaped tokens become ints, not floats: _format_number writes 3 for
    the integer 3, and a float 3.0 coming back out would print as "3.0" through
    every consumer of this data. Non-finite results are not numbers at all
    (matching the reference), so "1e999" stays the string it parses as.
    """
    if not _NUMERIC_LITERAL_RE.match(token):
        return None
    if "." in token or "e" in token or "E" in token:
        value = float(token)
        if math.isinf(value) or math.isnan(value):
            return None
        return value
    value = int(token)
    if math.isinf(float(value)):
        return None
    return value


def _parse_primitive_token(token, line=None):
    """Inverse of _encode_primitive: one token to null/bool/number/string."""
    token = _trim_spaces(token)
    if not token:
        return ""
    if token.startswith('"'):
        return _parse_string_literal(token, line)
    if token == "true":
        return True
    if token == "false":
        return False
    if token == "null":
        return None
    number = _parse_number_token(token)
    if number is not None:
        return number
    return token


def _parse_delimited_values(text, delim=DELIM):
    """Split a row or inline body on the delimiter, honouring quotes (SPEC S9.1/S9.3)."""
    values = []
    buf = []
    in_quotes = False
    i = 0
    n = len(text)
    while i < n:
        c = text[i]
        if c == "\\" and i + 1 < n and in_quotes:
            buf.append(text[i:i + 2])
            i += 2
            continue
        if c == '"':
            in_quotes = not in_quotes
            buf.append(c)
            i += 1
            continue
        if c == delim and not in_quotes:
            values.append(_trim_spaces("".join(buf)))
            buf = []
            i += 1
            continue
        buf.append(c)
        i += 1
    tail = "".join(buf)
    if tail or values:
        values.append(_trim_spaces(tail))
    return values


def _parse_field_entries(text, line=None, delim=DELIM):
    """The {..} field list to a plan of (name, children|None), inverse of _field_header."""
    entries = []
    buf = []
    in_quotes = False
    brace_depth = 0
    i = 0
    n = len(text)
    while i < n:
        c = text[i]
        if c == "\\" and i + 1 < n and in_quotes:
            buf.append(text[i:i + 2])
            i += 2
            continue
        if c == '"':
            in_quotes = not in_quotes
            buf.append(c)
            i += 1
            continue
        if not in_quotes:
            if c == "{":
                brace_depth += 1
            elif c == "}":
                brace_depth -= 1
            elif c == delim and brace_depth == 0:
                entries.append("".join(buf))
                buf = []
                i += 1
                continue
        buf.append(c)
        i += 1
    entries.append("".join(buf))

    plan = []
    for entry in entries:
        entry = _trim_spaces(entry)
        if not entry:
            raise ToonDecodeError("empty field name in field list", line)
        group_start = _find_unquoted_char(entry, "{")
        if group_start == -1:
            plan.append((_parse_string_literal(entry, line), None))
            continue
        name_part = _trim_spaces(entry[:group_start])
        if not name_part:
            raise ToonDecodeError("missing field name before nested field group", line)
        group_end = _find_matching_brace(entry, group_start)
        if group_end == -1:
            raise ToonDecodeError("unmatched brace in field list", line)
        if group_end != len(entry) - 1:
            raise ToonDecodeError("unexpected content after nested field group", line)
        plan.append((_parse_string_literal(name_part, line),
                     _parse_field_entries(entry[group_start + 1:group_end], line, delim)))
    return plan


def _duplicate_field_name(plan):
    seen = set()
    for name, children in plan:
        if name in seen:
            return name
        seen.add(name)
        if children:
            nested = _duplicate_field_name(children)
            if nested is not None:
                return nested
    return None


def _count_leaf_fields(plan):
    """Cells per row: the depth-first leaf count of the field plan (SPEC S9.3)."""
    total = 0
    for _name, children in plan:
        total += _count_leaf_fields(children) if children else 1
    return total


def _object_from_fields(plan, primitives):
    """Rebuild one row's object by walking the field plan, inverse of _flatten_row."""
    index = [0]

    def walk(nodes):
        obj = {}
        for name, children in nodes:
            if children is None and index[0] >= len(primitives):
                continue
            if children is not None:
                obj[name] = walk(children)
            else:
                obj[name] = primitives[index[0]]
                index[0] += 1
        return obj

    return walk(plan)


class _Line:
    """One significant line: its indent, its depth, and its content without indent."""

    __slots__ = ("raw", "content", "indent", "depth", "number")

    def __init__(self, raw, content, indent, depth, number):
        self.raw = raw
        self.content = content
        self.indent = indent
        self.depth = depth
        self.number = number


class _Reader:
    def __init__(self, lines, blank_lines):
        self.lines = lines
        self.blank_lines = blank_lines
        self.pos = 0
        self.last = None

    def peek(self):
        return self.lines[self.pos] if self.pos < len(self.lines) else None

    def read(self):
        line = self.peek()
        if line is not None:
            self.pos += 1
            self.last = line
        return line

    def check_no_blank_lines(self, start, end, context):
        """SPEC S12: a blank line may not interrupt a table or list body.

        The encoder never writes one, so a blank line between rows means lines
        were inserted or removed -- exactly the corruption that would otherwise
        read as a short table.
        """
        if start is None or end is None:
            return
        for number in self.blank_lines:
            if start < number < end:
                raise ToonDecodeError(
                    "blank line inside %s is not allowed" % context, number)


def _scan_lines(text, indent_size):
    """Split a document into significant lines, dropping comments and blanks.

    Splits on "\n" alone, like the reference: str.splitlines() would also break
    on U+2028, U+0085 and friends, and those are legal *inside* a quoted string
    (the encoder only escapes C0 controls), so splitlines would tear a value in
    half and then fail to explain why.
    """
    lines = []
    blank_lines = []
    for number, raw in enumerate(text.split("\n"), start=1):
        if number == 1 and raw.startswith("\ufeff"):
            raw = raw[1:]
        if raw.endswith("\r"):
            raw = raw[:-1]
        leading = _LEADING_WS_RE.match(raw).group(0)
        if "\t" in leading:
            raise ToonDecodeError("tabs are not allowed in indentation", number, raw)
        indent = len(leading)
        content = raw[indent:].rstrip(" ")
        if content.startswith("#"):
            continue  # SPEC S13: full-line comment
        if not content:
            blank_lines.append(number)
            continue
        if indent % indent_size != 0:
            raise ToonDecodeError(
                "indentation must be a multiple of %d spaces, found %d"
                % (indent_size, indent), number, raw)
        lines.append(_Line(raw, content, indent, indent // indent_size, number))
    return lines, blank_lines


def _parse_bracket_segment(segment, line=None):
    """'[3]' -> (3, keyed=False); '[3:]' -> (3, keyed=True). Comma delimiter only."""
    content = segment
    if content.endswith("\t") or content.endswith("|"):
        raise NotImplementedError(
            "this decoder implements the comma delimiter only; header %r declares "
            "the %s delimiter (SPEC S11)"
            % ("[" + segment + "]", "tab" if content.endswith("\t") else "pipe"))
    keyed = False
    if content.endswith(":"):
        keyed = True
        content = content[:-1]
    if not _BRACKET_LENGTH_RE.match(content):
        raise ToonDecodeError(
            "invalid array length %r (expected a non-negative integer without "
            "leading zeros)" % ("[" + segment + "]"), line)
    return int(content, 10), keyed


def _parse_array_header(content, line=None):
    """Parse 'key[3]{a,b}:' and friends. None when the line is not a header at all.

    Returns a dict with key (None when keyless), length, keyed, fields (None when
    absent) and inline (the text after the colon, None when there is none).
    Raises when the line *is* a header but a malformed one -- being lenient there
    would reinterpret a damaged header as an ordinary key.
    """
    trimmed = content.lstrip(" ")
    if trimmed.startswith('"'):
        close = _find_closing_quote(trimmed, 0)
        if close == -1:
            return None
        if not trimmed[close + 1:].startswith("["):
            return None
        key_end = len(content) - len(trimmed) + close + 1
        bracket_start = content.find("[", key_end)
    else:
        bracket_start = _find_unquoted_char(content, "[")
    if bracket_start == -1:
        return None
    first_colon = _find_unquoted_char(content, ":")
    if first_colon != -1 and first_colon < bracket_start:
        return None  # "key: [1]" is a primitive, not a header
    bracket_end = _find_unquoted_char(content, "]", bracket_start)
    if bracket_end == -1:
        return None

    brace_end = bracket_end + 1
    brace_start = _find_unquoted_char(content, "{", bracket_end)
    colon_after_bracket = _find_unquoted_char(content, ":", bracket_end)
    if brace_start != -1 and brace_start < colon_after_bracket:
        gap = content[bracket_end + 1:brace_start]
        if gap != "":
            raise ToonDecodeError(
                "unexpected content %r between bracket segment and field list"
                % gap.strip(), line, content)
        found = _find_matching_brace(content, brace_start)
        if found != -1:
            brace_end = found + 1

    colon = _find_unquoted_char(content, ":", max(bracket_end, brace_end))
    if colon == -1:
        return None
    gap_start = max(bracket_end + 1, brace_end)
    gap = content[gap_start:colon]
    if gap != "":
        raise ToonDecodeError(
            "unexpected content %r between bracket segment and colon" % gap.strip(),
            line, content)

    key = None
    if bracket_start > 0:
        raw_key = content[:bracket_start]
        if raw_key != raw_key.rstrip():
            raise ToonDecodeError(
                "unexpected whitespace between key and bracket segment", line, content)
        key = _parse_string_literal(raw_key, line) if raw_key.startswith('"') else raw_key

    inline = _trim_spaces(content[colon + 1:]) or None
    length, keyed = _parse_bracket_segment(content[bracket_start + 1:bracket_end], line)

    fields = None
    if brace_start != -1 and brace_start < colon:
        found = _find_matching_brace(content, brace_start)
        if found != -1 and found < colon:
            fields = _parse_field_entries(content[brace_start + 1:found], line)

    if keyed and fields is None:
        raise ToonDecodeError("keyed header requires a field list", line, content)
    if fields is not None:
        duplicate = _duplicate_field_name(fields)
        if duplicate is not None:
            raise ToonDecodeError(
                "duplicate field name %r in field list" % duplicate, line, content)
        if inline is not None:
            raise ToonDecodeError(
                "unexpected content after a fields-bearing header colon", line, content)
    return {"key": key, "length": length, "keyed": keyed, "fields": fields,
            "inline": inline}


def _is_array_header_content(content):
    return content.strip().startswith("[") and _find_unquoted_char(content, ":") != -1


def _is_key_value_content(content):
    return _find_unquoted_char(content, ":") != -1


def _is_key_value_line(line):
    content = line.content
    if content.startswith('"'):
        close = _find_closing_quote(content, 0)
        if close == -1:
            return False
        return ":" in content[close + 1:]
    return ":" in content


def _is_data_row(content, delim=DELIM):
    """A tabular row rather than a key-value line: no colon, or a delimiter first."""
    colon = _find_unquoted_char(content, ":")
    if colon == -1:
        return True
    delim_pos = _find_unquoted_char(content, delim)
    return delim_pos != -1 and delim_pos < colon


def _parse_key_token(content, start, line=None):
    """(key, index after its colon) for a quoted or bare key (SPEC S7.3)."""
    if start < len(content) and content[start] == '"':
        close = _find_closing_quote(content, start)
        if close == -1:
            raise ToonDecodeError("unterminated quoted key", line, content)
        key = _unescape_string(content[start + 1:close], line)
        pos = close + 1
        if pos >= len(content) or content[pos] != ":":
            raise ToonDecodeError("missing colon after key", line, content)
        return key, pos + 1
    colon = _find_unquoted_char(content, ":", start)
    if colon == -1:
        raise ToonDecodeError("missing colon after key", line, content)
    return _trim_spaces(content[start:colon]), colon + 1


def _assert_count(actual, expected, what, line):
    """The declared count is data, not decoration.

    '[2]{id,name}' followed by three rows means lines were added or lost. A
    decoder that returned all three would hand xq a table nobody declared, and
    one that returned two would drop a row without saying so.
    """
    if actual != expected:
        raise ToonDecodeError(
            "expected %d %s, got %d" % (expected, what, actual),
            line.number if line is not None else None,
            line.raw if line is not None else None)


def _assert_unique_key(key, seen, line):
    if key in seen:
        raise ToonDecodeError("duplicate sibling key %r" % key, line.number, line.raw)
    seen.add(key)


def _decode_document(reader):
    first = reader.peek()
    if first is None:
        return {}  # SPEC S8: an empty document is the empty object

    if _trim_spaces(first.content) == "[]":
        reader.read()
        _assert_fully_consumed(reader)
        return []

    if _is_array_header_content(first.content):
        header = _parse_array_header(first.content, first.number)
        if header is not None:
            reader.read()
            value = _decode_array_from_header(header, reader, 0, first)
            _assert_fully_consumed(reader)
            return value

    reader.read()
    following = reader.peek()
    if following is None and not _is_key_value_line(first):
        # SPEC S5: a lone primitive is a valid root.
        return _parse_primitive_token(first.content, first.number)
    if not _is_key_value_line(first) and following is not None and following.depth == 0:
        raise ToonDecodeError(
            "top-level document must start with a key-value or array-header line",
            first.number, first.raw)

    obj = {}
    seen = set()
    key, value = _decode_key_value(first, reader, 0, seen)
    obj[key] = value
    while True:
        line = reader.peek()
        if line is None:
            break
        if line.depth != 0:
            raise ToonDecodeError(
                "over-indented line: expected depth 0, found %d" % line.depth,
                line.number, line.raw)
        reader.read()
        key, value = _decode_key_value(line, reader, 0, seen)
        obj[key] = value
    return obj


def _assert_fully_consumed(reader):
    line = reader.peek()
    if line is not None:
        raise ToonDecodeError("unexpected content after the document root",
                             line.number, line.raw)


def _decode_key_value(line, reader, base_depth, seen):
    """One 'key: ...' line (plus whatever it owns below) -> (key, value)."""
    content = line.content
    header = _parse_array_header(content, line.number)
    if header is not None and header["key"] is not None:
        _assert_unique_key(header["key"], seen, line)
        return header["key"], _decode_array_from_header(header, reader, base_depth, line)
    if header is not None and header["key"] is None:
        raise ToonDecodeError(
            "keyless %s header is only valid at the document root"
            % ("keyed" if header["keyed"] else "array"), line.number, line.raw)

    key, end = _parse_key_token(content, 0, line.number)
    rest = _trim_spaces(content[end:])
    _assert_unique_key(key, seen, line)

    if not rest:
        nxt = reader.peek()
        if nxt is not None and nxt.depth > base_depth:
            if nxt.depth > base_depth + 1:
                raise ToonDecodeError(
                    "indentation depth jump: expected depth %d, found %d"
                    % (base_depth + 1, nxt.depth), nxt.number, nxt.raw)
            return key, _decode_object_fields(reader, base_depth + 1)
        return key, {}  # SPEC S8: "key:" with nothing under it is the empty object
    if rest == "[]":
        return key, []
    return key, _parse_primitive_token(rest, line.number)


def _decode_object_fields(reader, base_depth):
    obj = {}
    seen = set()
    depth = None
    while True:
        line = reader.peek()
        if line is None or line.depth < base_depth:
            break
        if depth is None:
            depth = line.depth
        if line.depth == depth:
            reader.read()
            key, value = _decode_key_value(line, reader, depth, seen)
            obj[key] = value
        elif line.depth > depth:
            raise ToonDecodeError(
                "over-indented line: expected depth %d, found %d" % (depth, line.depth),
                line.number, line.raw)
        else:
            break
    return obj


def _decode_array_from_header(header, reader, base_depth, header_line):
    if header["keyed"]:
        return _decode_keyed_object(header, reader, base_depth, header_line)
    if header["inline"] is not None:
        # SPEC S9.1: inline primitive array
        values = _parse_delimited_values(header["inline"])
        items = [_parse_primitive_token(v, header_line.number) for v in values]
        _assert_count(len(items), header["length"], "inline-form values", header_line)
        return items
    if header["fields"]:
        return _decode_tabular(header, reader, base_depth, header_line)
    return _decode_list(header, reader, base_depth, header_line)


def _decode_tabular(header, reader, base_depth, header_line):
    """SPEC S9.3: rows at header depth + 1, one flattened row per line."""
    row_depth = base_depth + 1
    leaf_count = _count_leaf_fields(header["fields"])
    rows = []
    start = end = None
    last = header_line
    while len(rows) < header["length"]:
        line = reader.peek()
        if line is None or line.depth != row_depth or not _is_data_row(line.content):
            break
        reader.read()
        if start is None:
            start = line.number
        end = line.number
        last = line
        values = _parse_delimited_values(line.content)
        _assert_count(len(values), leaf_count, "tabular row values", line)
        rows.append(_object_from_fields(
            header["fields"], [_parse_primitive_token(v, line.number) for v in values]))
    _assert_count(len(rows), header["length"], "tabular rows", last)
    reader.check_no_blank_lines(start, end, "a tabular array")
    nxt = reader.peek()
    if (nxt is not None and nxt.depth == row_depth
            and not nxt.content.startswith("- ") and _is_data_row(nxt.content)):
        raise ToonDecodeError(
            "expected %d tabular rows, found more" % header["length"],
            nxt.number, nxt.raw)
    return rows


def _decode_keyed_object(header, reader, base_depth, header_line):
    """SPEC S9.5: 'entry: cells' lines at header depth + 1."""
    entry_depth = base_depth + 1
    leaf_count = _count_leaf_fields(header["fields"])
    obj = {}
    seen = set()
    start = end = None
    last = header_line
    while True:
        line = reader.peek()
        if line is None or line.depth <= base_depth:
            break
        if line.depth > entry_depth:
            raise ToonDecodeError("unexpected indentation inside keyed tabular object",
                                  line.number, line.raw)
        if _find_unquoted_char(line.content, ":") == -1:
            raise ToonDecodeError("expected an entry row inside keyed tabular object",
                                  line.number, line.raw)
        reader.read()
        if start is None:
            start = line.number
        end = line.number
        last = line
        key, key_end = _parse_key_token(line.content, 0, line.number)
        _assert_unique_key(key, seen, line)
        cells = _trim_spaces(line.content[key_end:])
        values = [] if cells == "" else _parse_delimited_values(cells)
        _assert_count(len(values), leaf_count, "keyed entry cells", line)
        obj[key] = _object_from_fields(
            header["fields"], [_parse_primitive_token(v, line.number) for v in values])
    _assert_count(len(obj), header["length"], "keyed entries", last)
    reader.check_no_blank_lines(start, end, "a keyed tabular object")
    return obj


def _decode_list(header, reader, base_depth, header_line):
    """SPEC S9.2/S9.4: '- ' items at header depth + 1."""
    item_depth = base_depth + 1
    items = []
    start = end = None
    last = header_line
    while len(items) < header["length"]:
        line = reader.peek()
        if line is None or line.depth != item_depth:
            break
        if not (line.content == "-" or line.content.startswith("- ")):
            break
        if start is None:
            start = line.number
        items.append(_decode_list_item(reader, item_depth))
        if reader.last is not None:
            end = reader.last.number
            last = reader.last
    _assert_count(len(items), header["length"], "list-form items", last)
    reader.check_no_blank_lines(start, end, "a list-form array")
    nxt = reader.peek()
    if nxt is not None and nxt.depth == item_depth and nxt.content.startswith("- "):
        raise ToonDecodeError(
            "expected %d list-form items, found more" % header["length"],
            nxt.number, nxt.raw)
    return items


def _decode_list_item(reader, base_depth):
    """SPEC S9.2/S9.4/S10: one '- ...' item.

    What follows the hyphen is read as though it were a line one level deeper:
    an object's remaining fields sit at base_depth + 1, and a table the first
    field opens has its rows at base_depth + 2. That is what the encoder writes
    (see _lines_for_list_item_object).
    """
    line = reader.read()
    if line is None:
        raise ToonDecodeError("expected a list item")
    if line.content == "-":
        return {}  # SPEC S10: the empty object as a list item
    if not line.content.startswith("- "):
        raise ToonDecodeError('expected a list item to start with "- "',
                              line.number, line.raw)
    after = line.content[2:]
    if not _trim_spaces(after):
        return {}
    if _trim_spaces(after) == "[]":
        return []

    item_line = _Line(line.raw, after, line.indent, line.depth, line.number)

    if _is_array_header_content(after):
        header = _parse_array_header(after, line.number)
        if header is not None:
            if header["keyed"] or header["fields"] is not None:
                raise ToonDecodeError(
                    "keyless %s is only valid at the document root"
                    % ("keyed header" if header["keyed"]
                       else "header with a field list"), line.number, line.raw)
            return _decode_array_from_header(header, reader, base_depth, item_line)

    header = _parse_array_header(after, line.number)
    if header is not None and header["key"] is not None and header["fields"] is not None:
        obj = {}
        seen = set([header["key"]])
        obj[header["key"]] = _decode_array_from_header(
            header, reader, base_depth + 1, item_line)
        _follow_sibling_fields(obj, reader, base_depth + 1, seen)
        return obj

    if _is_key_value_content(after):
        obj = {}
        seen = set()
        key, value = _decode_key_value(item_line, reader, base_depth + 1, seen)
        obj[key] = value
        _follow_sibling_fields(obj, reader, base_depth + 1, seen)
        return obj

    return _parse_primitive_token(after, line.number)


def _follow_sibling_fields(obj, reader, follow_depth, seen):
    """The fields of a list-item object after its first, at the item's own depth + 1."""
    while True:
        line = reader.peek()
        if line is None or line.depth < follow_depth:
            break
        if line.depth != follow_depth or line.content.startswith("- "):
            break
        reader.read()
        key, value = _decode_key_value(line, reader, follow_depth, seen)
        obj[key] = value


def decode(text, indent_size=2, delimiter=","):
    """Decode a TOON v4.1 document (string) back to a JSON-model value.

    The inverse of encode(): decode(encode(v)) == v for every v this module can
    encode. Returns dict, list, str, int, float, bool or None, as json.load
    would for the same data.

    text: the document. A trailing newline is fine; a BOM is ignored.
    indent_size: spaces per level, matching the encoder that wrote it (SPEC S12).
    delimiter: must be "," -- this module implements the comma delimiter only.

    Raises ToonDecodeError on anything it cannot read as written: a row count
    that disagrees with its header, an indent that is not a multiple of
    indent_size, an unterminated quote, a duplicate sibling key, an unknown
    escape. Silence would be worse than the error: this data answers questions,
    and a quietly dropped row is indistinguishable from a row that never existed.
    """
    if delimiter != ",":
        raise NotImplementedError(
            "this decoder implements the comma delimiter only (got %r)" % (delimiter,))
    if not isinstance(text, str):
        raise TypeError("decode() expects str, got %s" % type(text).__name__)
    lines, blank_lines = _scan_lines(text, indent_size)
    return _decode_document(_Reader(lines, blank_lines))


def main(argv):
    if len(argv) < 2:
        sys.stderr.write("usage: toon_encoder.py input.json [output.toon]\n")
        return 1
    with open(argv[1], "r", encoding="utf-8") as f:
        data = json.load(f)
    text = encode(data)
    if len(argv) >= 3:
        with open(argv[2], "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
    else:
        sys.stdout.write(text + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
