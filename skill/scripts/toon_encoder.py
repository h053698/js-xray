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
