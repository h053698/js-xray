#!/usr/bin/env python3
"""Encode xray.json to TOON and report the token/char savings.

This is the stage that actually makes the encoder in toon_encoder.py useful:
it reads the explanation JSON the pipeline just wrote, encodes it with
toon_encoder.encode(), writes xray.toon next to it, and prints the size
reduction so a reader does not have to take the format's savings claim on
faith.

Token counts use tiktoken's o200k_base encoding (the GPT-4o/GPT-5 family
encoding) when tiktoken is installed. tiktoken is an optional dependency --
this repo has no required Python third-party packages, and this script must
keep working without it. When tiktoken is missing, the stage falls back to a
character-count reduction and says so explicitly on stderr rather than
silently skipping the token figures.

Usage:
    python3 toon_stats.py xray.json xray.toon [--stats stats.json]
"""
import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, HERE)
from toon_encoder import encode  # noqa: E402

TOKENIZER_NAME = "o200k_base"


def _count_tokens(text):
    """Return (token_count, tokenizer_name) or (None, None) if tiktoken is unavailable."""
    try:
        import tiktoken
    except ImportError:
        return None, None
    enc = tiktoken.get_encoding(TOKENIZER_NAME)
    return len(enc.encode(text)), TOKENIZER_NAME


def _pct_reduction(before, after):
    if before <= 0:
        return 0.0
    return (1 - (after / before)) * 100.0


def compute_stats(json_text, toon_text):
    """Build the stats dict shared by the CLI and tests. Pure function, no I/O."""
    json_chars = len(json_text)
    toon_chars = len(toon_text)
    char_reduction_pct = _pct_reduction(json_chars, toon_chars)

    json_tokens, tokenizer = _count_tokens(json_text)
    if json_tokens is None:
        toon_tokens = None
        token_reduction_pct = None
    else:
        toon_tokens, _ = _count_tokens(toon_text)
        token_reduction_pct = _pct_reduction(json_tokens, toon_tokens)

    return {
        "json_chars": json_chars,
        "toon_chars": toon_chars,
        "char_reduction_pct": round(char_reduction_pct, 2),
        "json_tokens": json_tokens,
        "toon_tokens": toon_tokens,
        "token_reduction_pct": round(token_reduction_pct, 2) if token_reduction_pct is not None else None,
        "tokenizer": tokenizer,
    }


def report_stats(stats, stream=sys.stderr):
    """Print the human-readable summary compute_stats() produced."""
    stream.write(
        "  chars: json=%d toon=%d (-%.1f%%)\n"
        % (stats["json_chars"], stats["toon_chars"], stats["char_reduction_pct"])
    )
    if stats["tokenizer"] is None:
        stream.write(
            "  tiktoken not installed, char-count ratio shown instead of token counts\n"
        )
    else:
        stream.write(
            "  tokens (%s): json=%d toon=%d (-%.1f%%)\n"
            % (stats["tokenizer"], stats["json_tokens"], stats["toon_tokens"], stats["token_reduction_pct"])
        )


def main(argv):
    ap = argparse.ArgumentParser(description="encode xray.json to TOON and report savings")
    ap.add_argument("input", help="path to xray.json")
    ap.add_argument("output", help="path to write xray.toon")
    ap.add_argument("--stats", help="path to write toon_stats.json (default: alongside output)")
    args = ap.parse_args(argv[1:])

    with open(args.input, "r", encoding="utf-8") as f:
        json_text = f.read()
    value = json.loads(json_text)

    toon_text = encode(value)
    with open(args.output, "w", encoding="utf-8", newline="\n") as f:
        f.write(toon_text)

    stats = compute_stats(json_text, toon_text)
    report_stats(stats)

    stats_path = args.stats or os.path.join(os.path.dirname(os.path.abspath(args.output)), "toon_stats.json")
    with open(stats_path, "w", encoding="utf-8") as f:
        json.dump(stats, f, indent=2)
        f.write("\n")

    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
