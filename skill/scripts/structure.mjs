#!/usr/bin/env node
// Extract structural facts from a JavaScript file: symbols, call graph, the
// browser surface each function touches, network operations, and class shapes.
//
// This pass only reports what is in the AST. Interpretation (what the flows are,
// what a function is for) happens in explain.py, so the facts stay auditable and
// the heuristics stay in one place.
import fs from "node:fs";
import { parse } from "@babel/parser";
import _traverse from "@babel/traverse";
import _generate from "@babel/generator";

const traverse = _traverse.default || _traverse;
const generate = _generate.default || _generate;

const MAX_STRINGS = 40;
const MAX_NUMBERS = 30;
const MAX_PREVIEW = 200;

// URL and path recognition. URL_ANYWHERE is deliberately global and unanchored:
// endpoints hide inside error messages and concatenated strings.
const URL_ANYWHERE = /(?:https?|wss?|ftp):\/\/[^\s"\x27`<>\\]+/g;
const HAS_URL = /(?:https?|wss?|ftp):\/\//;
const TRAILING_PUNCT = /[).,;:!?\x27"]+$/;
const PATH_LIKE = /^\/[A-Za-z0-9_.\-]+(?:\/[A-Za-z0-9_.\-{}:]*)+\/?$/;
const INTERP_MARK = "${...}";

// Globals worth recording when a function touches them. Everything else is
// noise for the purpose of describing behaviour.
const TRACKED_ROOTS = new Set([
  "navigator", "window", "document", "screen", "performance", "location",
  "localStorage", "sessionStorage", "indexedDB", "crypto", "Math", "JSON",
  "Date", "console", "globalThis", "self", "process", "fetch", "atob", "btoa",
  "XMLHttpRequest", "WebSocket", "TextEncoder", "TextDecoder", "Uint8Array",
  "Array", "Object", "String", "Number", "Promise", "Error", "Map", "Set",
  "WeakMap", "Proxy", "Reflect", "Symbol", "BigInt", "Intl", "URL",
  "URLSearchParams", "Blob", "FormData", "Headers", "Request", "Response",
  "AbortController", "setTimeout", "setInterval", "requestAnimationFrame",
]);

// Aliases for the global object. A path like window.localStorage.getItem names
// the same thing as localStorage.getItem, so the prefix is stripped before
// anything is matched against it.
// How far to follow a name back to the value it holds. Endpoints sit one or
// two hops away; more than that and the chain is usually runtime-dependent.
const MAX_RESOLVE_HOPS = 4;

const GLOBAL_ALIAS = new Set(["window", "globalThis", "self", "top", "parent"]);

// Places a module can keep state across page loads. Recorded separately from
// plain globals because persistence changes what a reimplementation must do:
// the value read here was written by an earlier run, not computed.
const STORAGE_PATH = /^(localStorage|sessionStorage|indexedDB|caches)\b|^document\.cookie$/;

// Constants that identify a well-known algorithm. Presence of the constant is
// strong evidence; the label names what to compare a port against.
const ALGO_CONSTANTS = [
  { value: 2166136261, algo: "FNV-1a 32-bit", role: "offset basis" },
  { value: 16777619, algo: "FNV-1a 32-bit", role: "prime" },
  { value: 2246822507, algo: "murmur3 fmix32", role: "mix constant 1" },
  { value: 3266489909, algo: "murmur3 fmix32", role: "mix constant 2" },
  { value: 1732584193, algo: "MD5", role: "init A" },
  { value: 4023233417, algo: "MD5", role: "init B" },
  { value: 1779033703, algo: "SHA-256", role: "H0" },
  { value: 3144134277, algo: "SHA-256", role: "H1" },
  { value: 1013904223, algo: "LCG", role: "increment" },
  { value: 1664525, algo: "LCG", role: "multiplier" },
  { value: 3988292384, algo: "CRC-32", role: "reversed polynomial" },
  { value: 5381, algo: "djb2", role: "seed" },
];

const ALGO_BY_VALUE = new Map(ALGO_CONSTANTS.map((c) => [c.value, c]));

// ---- JSVMP (JavaScript Virtual Machine Protect) interpreter fingerprint ----
//
// A VM-obfuscated file translates the original logic into a custom bytecode
// array and ships an interpreter for it. Every function this extractor then
// reports is a piece of that interpreter, so the analysis comes out structurally
// sound and behaviourally useless: the thing a reader came for lives in the
// bytecode, which is data. Detection only warns; recovering the bytecode is out
// of scope.
//
// False positives cost more than misses here. A large single-line bundle and a
// switch with many cases are both ordinary in minified code, and calling such a
// file VM-obfuscated teaches a reader to distrust results that were fine. So a
// verdict of "vm-obfuscated" needs the two signals specific to a bytecode
// interpreter -- a bitmasked dispatch switch, and numeric jump targets written
// back into the register that switch reads -- while size and density signals
// only ever corroborate.

// Interpreters dispatch on an opcode field masked out of a packed instruction
// word, so the mask is a small all-ones-ish value. 3 (two bits) is the smallest
// that could select an opcode at all; 0xFFFF is past any real opcode space, and
// above it a "&" is far more likely to be ordinary 16/32-bit arithmetic.
const VM_MASK_MIN = 3;
const VM_MASK_MAX = 0xffff;

// A real JSVMP dispatch carries dozens of opcodes. 12 sits well below the 40-80
// seen in the wild and well above the 3-6 of a hand-written state machine, so it
// separates the two without requiring the file to be large.
const VM_MIN_CASES = 12;

// Jump density: every opcode that continues execution has to write the next
// program counter, so most case bodies contain such a write. Requiring 8 keeps
// out a switch that merely assigns a couple of numeric flags.
const VM_MIN_JUMP_CASES = 8;

// Constant-table reads. Corroborating only, so the bar is set where ordinary
// code does not reach it: 60 distinct numeric indices read off one base.
const VM_MIN_TABLE_HITS = 60;

// Bulk. JSVMP output is a large file collapsed onto very few lines. Both halves
// are required: a 500KB pretty-printed library is not this, and neither is a 2KB
// one-liner. The null-byte ratio is reported alongside to rule out a binary blob
// read as text -- pure JS is effectively always 0%.
const VM_BULK_BYTES = 200 * 1024;
const VM_BULK_LINE_CHARS = 20000;
const VM_NULL_BYTE_MAX_RATIO = 0.01;

// Loop kinds that can host an interpreter's dispatch loop.
const VM_LOOP_TYPES = new Set([
  "WhileStatement", "DoWhileStatement", "ForStatement", "ForOfStatement", "ForInStatement",
]);

function isLowMask(node) {
  return !!node && node.type === "NumericLiteral" && Number.isInteger(node.value) &&
    node.value >= VM_MASK_MIN && node.value <= VM_MASK_MAX;
}

// The register a dispatch switch reads: switch (d[7] & 31) -> d[7].
// Returns null when the discriminant is not a masked value, which is the case
// for every ordinary switch, including control-flow-flattened ones.
function dispatchRegister(disc) {
  if (!disc || disc.type !== "BinaryExpression") return null;
  if (disc.operator !== "&" && disc.operator !== "%") return null;
  if (isLowMask(disc.right)) return { node: disc.left, mask: disc.right.value, op: disc.operator };
  // a & b is commutative, so 31 & d[7] is the same dispatch written backwards
  if (disc.operator === "&" && isLowMask(disc.left)) {
    return { node: disc.right, mask: disc.left.value, op: disc.operator };
  }
  return null;
}

// A jump target is a constant address: 612, -1, or the two-way form
// d[7] = d[k] ? 512 : 425 that a conditional branch compiles to.
function isNumericJumpTarget(node) {
  if (!node) return false;
  if (node.type === "NumericLiteral") return true;
  if (node.type === "UnaryExpression" && node.operator === "-") {
    return isNumericJumpTarget(node.argument);
  }
  if (node.type === "ConditionalExpression") {
    return isNumericJumpTarget(node.consequent) && isNumericJumpTarget(node.alternate);
  }
  return false;
}

// True when the program counter lives in an array slot -- d[7] rather than a
// named variable. This is what separates a bytecode interpreter from
// control-flow flattening, which keeps its state in a plain local and is a much
// milder transform that leaves the real logic in the AST.
function isRegisterSlot(node) {
  return !!node && node.type === "MemberExpression" && node.computed &&
    node.property && node.property.type === "NumericLiteral";
}

// The register file a slot belongs to: d[7] -> "d". Two slots of the same array
// are the same machine's registers, which is how the fetch register and the
// program counter get related to each other below.
function registerFileOf(node) {
  if (!isRegisterSlot(node)) return null;
  return preview(node.object, 40);
}

// Is this assignment target part of the dispatched machine's state? Either the
// exact value the switch reads (switch (pc & 31) ... pc = 612) or another slot of
// the same register file (switch (d[6] & 31) ... d[7] = 612). Both spellings
// appear in the wild, and requiring the first one only would miss half of them.
function isMachineStateTarget(target, dispatchKey, registerFile) {
  const key = preview(target, 60);
  if (key && key === dispatchKey) return key;
  if (!registerFile || !isRegisterSlot(target)) return null;
  return registerFileOf(target) === registerFile ? key : null;
}

function enclosingLoopLine(path) {
  let p = path.parentPath;
  while (p) {
    if (VM_LOOP_TYPES.has(p.node.type)) return p.node.loc ? p.node.loc.start.line : true;
    // stop at a function boundary: a loop outside it does not drive this switch
    if (/Function|Program/.test(p.node.type)) return null;
    p = p.parentPath;
  }
  return null;
}

// Collect the VM signals present in a file and turn them into a verdict.
// Reported under structure.json's "vm_signals" so explain.py can warn without
// re-deriving any of it, and so a reader can audit the evidence.
function detectVmSignals(ast, code) {
  const signals = [];

  // ---- dispatch loop: the switch a bytecode interpreter runs on ----
  let best = null;
  traverse(ast, {
    SwitchStatement(path) {
      const cases = (path.node.cases || []).length;
      if (cases < VM_MIN_CASES) return;
      if (enclosingLoopLine(path) === null) return;  // not a dispatch loop

      const reg = dispatchRegister(path.node.discriminant);
      const regNode = reg ? reg.node : path.node.discriminant;
      const registerKey = preview(regNode, 60);
      if (!registerKey) return;

      // How many case bodies write a constant address into the machine's state.
      // Counted per case, not per assignment: a case that writes the program
      // counter three times is still one jump site, and counting writes would let
      // one unrolled case body clear the threshold on its own.
      const registerFile = registerFileOf(regNode);
      let jumpCases = 0;
      const jumpTargets = new Map();
      for (const casePath of path.get("cases")) {
        let found = null;
        casePath.traverse({
          AssignmentExpression(inner) {
            if (found) return;
            if (inner.node.operator !== "=") return;
            if (!isNumericJumpTarget(inner.node.right)) return;
            const key = isMachineStateTarget(inner.node.left, registerKey, registerFile);
            if (key) found = key;
          },
        });
        if (found) {
          jumpCases += 1;
          jumpTargets.set(found, (jumpTargets.get(found) || 0) + 1);
        }
      }
      // The slot written by the most case bodies is the program counter; naming
      // it in the evidence is what lets a reader find the dispatch by hand.
      let programCounter = registerKey;
      let pcWrites = 0;
      for (const [key, count] of jumpTargets) {
        if (count > pcWrites) { programCounter = key; pcWrites = count; }
      }

      const candidate = {
        cases,
        jumpCases,
        masked: !!reg,
        mask: reg ? reg.mask : null,
        maskOp: reg ? reg.op : null,
        registerKey,
        programCounter,
        registerIsSlot: isRegisterSlot(regNode),
        line: path.node.loc ? path.node.loc.start.line : null,
        span: (path.node.end || 0) - (path.node.start || 0),
      };
      // Keep the strongest candidate: a masked dispatch beats an unmasked one,
      // then more jump targets, then more opcodes.
      if (!best) {
        best = candidate;
      } else {
        const a = [candidate.masked ? 1 : 0, candidate.jumpCases, candidate.cases];
        const b = [best.masked ? 1 : 0, best.jumpCases, best.cases];
        for (let i = 0; i < a.length; i++) {
          if (a[i] !== b[i]) {
            if (a[i] > b[i]) best = candidate;
            break;
          }
        }
      }
    },
  });

  if (best && best.masked) {
    signals.push({
      kind: "masked-switch-dispatch",
      detail: "switch on (" + best.registerKey + " " + best.maskOp + " " + best.mask +
        ") with " + best.cases + " cases, inside a loop",
      line: best.line,
    });
  } else if (best) {
    // An unmasked loop-switch is also what control-flow flattening looks like,
    // so it is recorded but never enough on its own.
    signals.push({
      kind: "loop-switch-dispatch",
      detail: "switch on " + best.registerKey + " with " + best.cases +
        " cases, inside a loop, discriminant not bitmasked",
      line: best.line,
    });
  }
  if (best && best.jumpCases >= VM_MIN_JUMP_CASES) {
    signals.push({
      kind: "dense-numeric-jumps",
      detail: best.programCounter + " assigned a constant address in " + best.jumpCases +
        " of " + best.cases + " case bodies",
      line: best.line,
    });
  }
  if (best && best.registerIsSlot) {
    signals.push({
      kind: "array-slot-program-counter",
      detail: "the dispatched value is the array slot " + best.registerKey +
        ", not a named variable",
      line: best.line,
    });
  }

  // ---- numeric constant table: C[9][667] style reads off one base ----
  const tableHits = new Map();
  traverse(ast, {
    MemberExpression(path) {
      const n = path.node;
      if (!n.computed || !n.property || n.property.type !== "NumericLiteral") return;
      const base = preview(n.object, 40);
      if (!base || base.length > 40) return;
      if (!tableHits.has(base)) {
        if (tableHits.size >= 500) return;  // bounded: this runs on 500KB inputs
        tableHits.set(base, new Set());
      }
      const seen = tableHits.get(base);
      if (seen.size < 5000) seen.add(n.property.value);
    },
  });
  let table = null;
  for (const [base, seen] of tableHits) {
    if (!table || seen.size > table.count) table = { base, count: seen.size };
  }
  if (table && table.count >= VM_MIN_TABLE_HITS) {
    signals.push({
      kind: "numeric-constant-table",
      detail: table.base + "[N] read at " + table.count + " distinct numeric indices",
      line: null,
    });
  }

  // ---- text statistics: bulk collapsed onto very few lines ----
  // Byte counts, line lengths and the null-byte ratio are text facts, so they
  // are measured on the text instead of inferred from the AST.
  const bytes = Buffer.byteLength(code, "utf8");
  const lineList = code.split("\n");
  let maxLine = 0;
  for (const ln of lineList) if (ln.length > maxLine) maxLine = ln.length;
  const nullBytes = code.split("\u0000").length - 1;
  const nullRatio = bytes ? nullBytes / bytes : 0;
  if (bytes >= VM_BULK_BYTES && maxLine >= VM_BULK_LINE_CHARS &&
      nullRatio < VM_NULL_BYTE_MAX_RATIO) {
    signals.push({
      kind: "single-line-bulk",
      detail: (bytes / 1024).toFixed(0) + "KB over " + lineList.length +
        " line(s), longest " + maxLine + " chars, " +
        (nullRatio * 100).toFixed(1) + "% null bytes",
      line: null,
    });
  }

  // ---- one switch accounting for most of the file ----
  if (best && bytes && best.span / bytes >= 0.3) {
    signals.push({
      kind: "dispatch-dominates-file",
      detail: "the dispatch switch spans " + ((best.span / bytes) * 100).toFixed(0) +
        "% of the file",
      line: best.line,
    });
  }

  const kinds = new Set(signals.map((s) => s.kind));
  const hasMaskedDispatch = kinds.has("masked-switch-dispatch");
  const hasJumps = kinds.has("dense-numeric-jumps");
  const hasSlotPc = kinds.has("array-slot-program-counter");

  // Weights, not a probability: they exist so a reader can tell a two-signal
  // verdict from a five-signal one. The two core signals alone reach 70.
  const WEIGHT = {
    "masked-switch-dispatch": 40,
    "dense-numeric-jumps": 30,
    "array-slot-program-counter": 10,
    "numeric-constant-table": 10,
    "loop-switch-dispatch": 5,
    "single-line-bulk": 5,
    "dispatch-dominates-file": 5,
  };
  let score = 0;
  for (const kind of kinds) score += WEIGHT[kind] || 0;
  if (score > 100) score = 100;

  let verdict = "none";
  if (hasMaskedDispatch && hasJumps) {
    // Both halves of the interpreter fingerprint. Ordinary minified output does
    // not mask a dispatch value and then write constant addresses back into it
    // from most of its case bodies.
    verdict = "vm-obfuscated";
  } else if (hasMaskedDispatch) {
    verdict = "suspected";
  } else if (hasJumps && hasSlotPc) {
    // No mask, but the program counter is an array slot fed constant addresses.
    // Consistent with a VM that unpacks its opcode field elsewhere, and also
    // with an unusual generated state machine -- so it stays at suspected.
    verdict = "suspected";
  }

  return { verdict, score, signals };
}

// True when a multiplication feeds directly into a 32-bit coercion, meaning the
// product was computed in float64 first. Only the immediate parent counts: an
// extra layer of arithmetic in between changes the rounding story anyway.
function isTruncatedTo32(path) {
  const parent = path.parent;
  if (!parent) return false;
  if (parent.type === "BinaryExpression" && [">>>", "|", "&", ">>", "<<"].includes(parent.operator)) {
    return parent.left === path.node;
  }
  if (parent.type === "UnaryExpression" && parent.operator === "~") return true;
  return false;
}

function parseSource(code) {
  let lastErr;
  for (const sourceType of ["unambiguous", "script", "module"]) {
    try {
      return parse(code, {
        sourceType,
        allowReturnOutsideFunction: true,
        errorRecovery: true,
      });
    } catch (err) {
      lastErr = err;
    }
  }
  throw lastErr;
}

function preview(node, limit) {
  if (!node) return null;
  try {
    const out = generate(node, { concise: true, comments: false }).code;
    const max = limit || MAX_PREVIEW;
    return out.length > max ? out.slice(0, max) + " ..." : out;
  } catch (err) {
    return null;
  }
}

// Dotted path of a member expression, with computed parts marked.
function memberPath(node) {
  const parts = [];
  let cur = node;
  while (cur && (cur.type === "MemberExpression" || cur.type === "OptionalMemberExpression")) {
    if (!cur.computed && cur.property.type === "Identifier") {
      parts.unshift(cur.property.name);
    } else if (cur.property.type === "StringLiteral") {
      parts.unshift(cur.property.value);
    } else {
      parts.unshift("[computed]");
    }
    cur = cur.object;
  }
  if (!cur) return null;
  if (cur.type === "Identifier") parts.unshift(cur.name);
  else if (cur.type === "ThisExpression") parts.unshift("this");
  else return null;
  return parts.join(".");
}

function paramNames(node) {
  return (node.params || []).map((p, i) => {
    if (p.type === "Identifier") return p.name;
    if (p.type === "RestElement" && p.argument.type === "Identifier") return "..." + p.argument.name;
    if (p.type === "AssignmentPattern" && p.left.type === "Identifier") {
      return p.left.name + "=" + (preview(p.right, 30) || "?");
    }
    if (p.type === "ObjectPattern") return "{" + p.properties.length + " fields}";
    if (p.type === "ArrayPattern") return "[destructured]";
    return "arg" + i;
  });
}

// Best-effort name for a function-like node, from whatever context holds it.
function nameOf(path) {
  const n = path.node;
  if (n.id && n.id.name) return { name: n.id.name, kind: "function" };

  const parent = path.parent;
  if (!parent) return { name: null, kind: "anonymous" };

  if (parent.type === "VariableDeclarator" && parent.id.type === "Identifier") {
    return { name: parent.id.name, kind: n.type === "ArrowFunctionExpression" ? "arrow" : "function" };
  }
  if (parent.type === "ClassMethod" || parent.type === "ObjectMethod") {
    return { name: keyName(parent.key), kind: parent.kind || "method" };
  }
  if (parent.type === "ClassProperty" || parent.type === "ClassPrivateProperty") {
    return { name: keyName(parent.key), kind: "class-field" };
  }
  if (parent.type === "ObjectProperty") {
    return { name: keyName(parent.key), kind: "property" };
  }
  if (parent.type === "AssignmentExpression") {
    const p = parent.left.type === "Identifier" ? parent.left.name : memberPath(parent.left);
    if (p) return { name: p, kind: "assigned" };
  }
  if (parent.type === "CallExpression" && parent.callee === n) {
    return { name: null, kind: "iife" };
  }
  if (parent.type === "NewExpression" || parent.type === "CallExpression") {
    return { name: null, kind: "callback" };
  }
  return { name: null, kind: "anonymous" };
}

function keyName(key) {
  if (!key) return null;
  if (key.type === "Identifier") return key.name;
  if (key.type === "StringLiteral") return key.value;
  if (key.type === "PrivateName") return "#" + key.id.name;
  return null;
}


export function extractStructure(code) {
  const ast = parseSource(code);
  const lines = code.split("\n");

  const functions = [];
  const byNode = new Map();
  const classes = [];
  let idSeq = 0;

  // ---- pass 1: every function-like node becomes a symbol ----
  traverse(ast, {
    "FunctionDeclaration|FunctionExpression|ArrowFunctionExpression|ClassMethod|ObjectMethod"(path) {
      const n = path.node;
      const meta = n.type === "ClassMethod" || n.type === "ObjectMethod"
        ? { name: keyName(n.key), kind: n.kind === "constructor" ? "constructor" : (n.kind || "method") }
        : nameOf(path);

      const loc = n.loc;
      const entry = {
        id: "fn" + (idSeq++),
        name: meta.name,
        kind: meta.kind,
        async: !!n.async,
        generator: !!n.generator,
        static: !!n.static,
        params: paramNames(n),
        start_line: loc ? loc.start.line : null,
        end_line: loc ? loc.end.line : null,
        loc_lines: loc ? loc.end.line - loc.start.line + 1 : null,
        // column disambiguates anonymous siblings on one line: a minified call can
        // take several inline arrows that all start and end on the same line.
        start_col: loc ? loc.start.column : null,
        class: null,
        calls: [],
        globals: [],
        strings: [],
        numbers: [],
        algorithms: [],
        operators: [],
        // How the function does 32-bit multiplication. This is not cosmetic:
        // Math.imul(a,b) is an exact 32-bit product, while a*b>>>0 does a float64
        // product first and silently loses low bits above 2^53. A port has to
        // reproduce whichever one the source used, so record it as a fact.
        arith: { imul_calls: 0, truncated_multiplies: 0, multiply_style: null },
        control: { loops: 0, branches: 0, try_blocks: 0, switches: 0, max_depth: 0 },
        network: [],
        storage: [],
        throws: [],
        returns: [],
        awaits: 0,
        reads_this: [],
        writes_this: [],
      };
      functions.push(entry);
      byNode.set(n, entry);
    },
    ClassDeclaration(path) {
      recordClass(path, classes);
    },
    ClassExpression(path) {
      recordClass(path, classes);
    },
  });

  function recordClass(path, out) {
    const n = path.node;
    const name = (n.id && n.id.name) ||
      (path.parent && path.parent.type === "VariableDeclarator" && path.parent.id.type === "Identifier"
        ? path.parent.id.name : null);
    const members = { methods: [], getters: [], setters: [], fields: [], static: [] };
    for (const el of n.body.body) {
      const key = keyName(el.key);
      if (!key) continue;
      if (el.static) members.static.push(key);
      if (el.type === "ClassMethod") {
        if (el.kind === "get") members.getters.push(key);
        else if (el.kind === "set") members.setters.push(key);
        else members.methods.push(key);
      } else if (el.type === "ClassProperty" || el.type === "ClassPrivateProperty") {
        members.fields.push(key);
      }
    }
    out.push({
      name,
      superClass: n.superClass ? (memberPath(n.superClass) || preview(n.superClass, 40)) : null,
      start_line: n.loc ? n.loc.start.line : null,
      end_line: n.loc ? n.loc.end.line : null,
      ...members,
    });
  }

  // Nearest enclosing recorded function for any path.
  function ownerOf(path) {
    let p = path.parentPath;
    while (p) {
      if (byNode.has(p.node)) return byNode.get(p.node);
      p = p.parentPath;
    }
    return null;
  }

  function push(arr, value, cap) {
    if (value === null || value === undefined) return;
    if (arr.length >= (cap || 60)) return;
    if (!arr.includes(value)) arr.push(value);
  }

  // ---- attach the enclosing class to each method ----
  traverse(ast, {
    "ClassDeclaration|ClassExpression"(path) {
      const cname = (path.node.id && path.node.id.name) ||
        (path.parent && path.parent.type === "VariableDeclarator" && path.parent.id.type === "Identifier"
          ? path.parent.id.name : null);
      path.traverse({
        "ClassMethod|ClassProperty|ClassPrivateProperty"(inner) {
          const fnNode = inner.node.type === "ClassMethod"
            ? inner.node
            : (inner.node.value && byNode.has(inner.node.value) ? inner.node.value : null);
          const entry = fnNode && byNode.get(fnNode);
          if (entry) {
            entry.class = cname;
            if (inner.node.type !== "ClassMethod") entry.kind = "class-field";
            if (!entry.name) entry.name = keyName(inner.node.key);
          }
        },
      });
    },
  });

  // ---- pass 2: what each function does ----
  traverse(ast, {
    CallExpression(path) {
      const owner = ownerOf(path);
      if (!owner) return;
      const callee = path.node.callee;
      let target = null;
      if (callee.type === "Identifier") target = callee.name;
      else if (callee.type === "MemberExpression" || callee.type === "OptionalMemberExpression") {
        target = memberPath(callee);
      }
      if (target) push(owner.calls, target, 80);

      // network operations, with enough detail to replicate the request
      if (target === "fetch" || (target && target.endsWith(".fetch"))) {
        owner.network.push(describeFetch(path.node, path));
      } else if (target && /\.(open|send)$/.test(target)) {
        owner.network.push({ kind: "xhr", detail: preview(path.node, 120) });
      }
      if (target === "atob" || target === "btoa") {
        push(owner.operators, target === "atob" ? "base64-decode" : "base64-encode", 20);
      }
      if (target === "Math.imul") owner.arith.imul_calls += 1;
    },

    NewExpression(path) {
      const owner = ownerOf(path);
      if (!owner) return;
      const c = path.node.callee;
      const name = c.type === "Identifier" ? c.name : memberPath(c);
      if (name) push(owner.calls, "new " + name, 80);
      if (name === "XMLHttpRequest" || name === "WebSocket") {
        owner.network.push({ kind: name === "WebSocket" ? "websocket" : "xhr", detail: preview(path.node, 120) });
      }
    },

    MemberExpression(path) {
      const owner = ownerOf(path);
      if (!owner) return;
      const p = memberPath(path.node);
      if (!p) return;
      const root = p.split(".")[0];

      if (root === "this") {
        // distinguish reads from writes: writes define the object shape
        const parent = path.parent;
        const isWrite = parent && parent.type === "AssignmentExpression" && parent.left === path.node;
        push(isWrite ? owner.writes_this : owner.reads_this, p, 40);
        return;
      }
      if (!TRACKED_ROOTS.has(root)) return;
      // window.localStorage and localStorage are the same surface, and code
      // written for both browser and worker contexts mixes them freely. Drop the
      // global-object prefix so downstream matching sees one spelling.
      let norm = p;
      if (GLOBAL_ALIAS.has(root)) {
        const rest = p.slice(root.length + 1);
        if (rest && TRACKED_ROOTS.has(rest.split(".")[0])) norm = rest;
      }
      // only record the meaningful prefix, e.g. navigator.userAgent
      const parts = norm.split(".");
      push(owner.globals, parts.slice(0, 3).join("."), 50);
      if (STORAGE_PATH.test(norm)) {
        push(owner.storage, norm, 20);
      }
    },

    StringLiteral(path) {
      const owner = ownerOf(path);
      if (!owner) return;
      const v = path.node.value;
      if (!v || v.length > 160) return;
      push(owner.strings, v, MAX_STRINGS);
    },

    NumericLiteral(path) {
      const owner = ownerOf(path);
      if (!owner) return;
      const v = path.node.value;
      const algo = ALGO_BY_VALUE.get(v);
      if (algo) {
        const tag = algo.algo + " (" + algo.role + ")";
        push(owner.algorithms, tag, 12);
      }
      if (Math.abs(v) > 255 || algo) push(owner.numbers, v, MAX_NUMBERS);
    },

    BinaryExpression(path) {
      const owner = ownerOf(path);
      if (!owner) return;
      const op = path.node.operator;
      if (["^", "&", "|", "<<", ">>", ">>>", "%"].includes(op)) push(owner.operators, op, 20);
      // a * b >>> 0, a * b | 0, a * b & 0xFFFFFFFF: a float64 multiply that is
      // then truncated, which is not the same as an exact 32-bit multiply.
      if (op === "*" && isTruncatedTo32(path)) owner.arith.truncated_multiplies += 1;
    },

    AssignmentExpression(path) {
      const owner = ownerOf(path);
      if (!owner) return;
      const op = path.node.operator;
      if (["^=", "&=", "|=", "<<=", ">>=", ">>>="].includes(op)) push(owner.operators, op, 20);
    },

    AwaitExpression(path) {
      const owner = ownerOf(path);
      if (owner) owner.awaits += 1;
    },

    ThrowStatement(path) {
      const owner = ownerOf(path);
      if (owner) push(owner.throws, preview(path.node.argument, 80), 10);
    },

    ReturnStatement(path) {
      const owner = ownerOf(path);
      if (owner && path.node.argument) push(owner.returns, preview(path.node.argument, 100), 8);
    },

    "ForStatement|ForOfStatement|ForInStatement|WhileStatement|DoWhileStatement"(path) {
      const owner = ownerOf(path);
      if (owner) owner.control.loops += 1;
    },

    "IfStatement|ConditionalExpression"(path) {
      const owner = ownerOf(path);
      if (owner) owner.control.branches += 1;
    },

    TryStatement(path) {
      const owner = ownerOf(path);
      if (owner) owner.control.try_blocks += 1;
    },

    SwitchStatement(path) {
      const owner = ownerOf(path);
      if (owner) owner.control.switches += 1;
    },
  });


  // ---- follow a name back to the string it was assigned once ----
  // Only single-assignment bindings are followed. If a variable is written more
  // than once its value at the call site is a runtime question, and guessing one
  // of the writes would be worse than reporting the expression as-is.
  function resolveStringish(scopePath, node, hops) {
    const depth = hops || 0;
    if (!node || depth > MAX_RESOLVE_HOPS) return null;

    if (node.type === "StringLiteral") return node.value;

    if (node.type === "TemplateLiteral") {
      const out = [];
      const quasis = node.quasis || [];
      for (let i = 0; i < quasis.length; i++) {
        out.push(quasis[i].value.cooked != null ? quasis[i].value.cooked : quasis[i].value.raw);
        const ex = (node.expressions || [])[i];
        if (ex) {
          const sub = resolveStringish(scopePath, ex, depth + 1);
          out.push(sub != null ? sub : INTERP_MARK);
        }
      }
      return out.join("");
    }

    if (node.type === "BinaryExpression" && node.operator === "+") {
      const l = resolveStringish(scopePath, node.left, depth + 1);
      const r = resolveStringish(scopePath, node.right, depth + 1);
      if (l == null && r == null) return null;
      // A half-resolved endpoint is still worth showing: "https://host" + path
      // tells a reader the host even when the suffix is computed.
      return (l != null ? l : INTERP_MARK) + (r != null ? r : INTERP_MARK);
    }

    if (node.type !== "Identifier" || !scopePath || !scopePath.scope) return null;
    const binding = scopePath.scope.getBinding(node.name);
    if (!binding || !binding.constant) return null;
    const decl = binding.path;
    if (!decl) return null;
    if (decl.node.type === "VariableDeclarator" && decl.node.init) {
      return resolveStringish(decl, decl.node.init, depth + 1);
    }
    return null;
  }

  // ---- fetch call detail: URL, method, headers, body shape ----
  function describeFetch(node, scopePath) {
    const out = { kind: "fetch", url: null, method: null, headers: [], body: null, credentials: null };
    const args = node.arguments || [];
    if (args[0]) {
      if (args[0].type === "StringLiteral") out.url = args[0].value;
      else {
        out.url = preview(args[0], 120);
        // Endpoints are usually hoisted into a module constant, so the call site
        // holds only a name. A reader wants the address, so follow single-
        // assignment bindings back to the literal and keep the name alongside it.
        const resolved = resolveStringish(scopePath, args[0]);
        // A partial resolution is only an improvement when it recovered an actual
        // address. "${...}req" says less than the expression Zt + "req" it came
        // from, so in that case the expression stays as the answer.
        const informative = resolved && (!resolved.includes(INTERP_MARK) || HAS_URL.test(resolved));
        if (informative && resolved !== out.url) {
          out.url_expression = out.url;
          out.url = resolved;
        }
      }
    }
    const opts = args[1];
    if (opts && opts.type === "ObjectExpression") {
      for (const prop of opts.properties) {
        if (prop.type !== "ObjectProperty") continue;
        const key = keyName(prop.key);
        if (key === "method") {
          out.method = prop.value.type === "StringLiteral" ? prop.value.value : preview(prop.value, 40);
        } else if (key === "credentials") {
          out.credentials = prop.value.type === "StringLiteral" ? prop.value.value : preview(prop.value, 40);
        } else if (key === "body") {
          out.body = preview(prop.value, 160);
        } else if (key === "headers" && prop.value.type === "ObjectExpression") {
          for (const h of prop.value.properties) {
            if (h.type !== "ObjectProperty") continue;
            const hk = keyName(h.key);
            const hv = h.value.type === "StringLiteral" ? h.value.value : preview(h.value, 60);
            if (hk) out.headers.push(hk + ": " + hv);
          }
        }
      }
    }
    if (!out.method) out.method = "GET (default)";
    return out;
  }

  // ---- call graph over recorded symbols ----
  // Resolution is name-based, so it is approximate: same-named locals in
  // different scopes collapse together. Good enough to show reachability, and
  // marked as approximate in the output so nothing downstream over-trusts it.
  const named = new Map();
  for (const fn of functions) {
    if (!fn.name) continue;
    if (!named.has(fn.name)) named.set(fn.name, fn.id);
  }

  const edges = [];
  const seenEdge = new Set();
  for (const fn of functions) {
    for (const target of fn.calls) {
      // this.foo() and Class.foo() resolve on the last segment
      const short = target.replace(/^new /, "").split(".").pop();
      const to = named.get(short);
      if (!to || to === fn.id) continue;
      const key = fn.id + ">" + to;
      if (seenEdge.has(key)) continue;
      seenEdge.add(key);
      edges.push({ from: fn.id, to, via: target });
    }
  }

  const calleeCount = new Map();
  const callerCount = new Map();
  for (const e of edges) {
    calleeCount.set(e.from, (calleeCount.get(e.from) || 0) + 1);
    callerCount.set(e.to, (callerCount.get(e.to) || 0) + 1);
  }
  for (const fn of functions) {
    fn.calls_out = calleeCount.get(fn.id) || 0;
    fn.called_by = callerCount.get(fn.id) || 0;
  }

  // ---- resolve multiply_style per function ----
  // Only meaningful for functions that actually do 32-bit arithmetic. "mixed"
  // is reported rather than guessed, because a port then has to look at the
  // source line by line instead of trusting one rule.
  for (const fn of functions) {
    const a = fn.arith;
    if (a.imul_calls > 0 && a.truncated_multiplies > 0) a.multiply_style = "mixed";
    else if (a.imul_calls > 0) a.multiply_style = "imul";
    else if (a.truncated_multiplies > 0) a.multiply_style = "truncated-float";
  }

  // ---- module-level facts ----
  const exportsFound = [];
  const imports = [];
  const globalAssigns = [];
  traverse(ast, {
    ExportNamedDeclaration(path) {
      for (const s of path.node.specifiers || []) {
        if (s.exported) exportsFound.push(keyName(s.exported) || s.exported.name);
      }
      const decl = path.node.declaration;
      if (decl && decl.type === "FunctionDeclaration" && decl.id) exportsFound.push(decl.id.name);
      if (decl && decl.type === "VariableDeclaration") {
        for (const d of decl.declarations) if (d.id.type === "Identifier") exportsFound.push(d.id.name);
      }
    },
    ExportDefaultDeclaration() {
      exportsFound.push("default");
    },
    ImportDeclaration(path) {
      imports.push(path.node.source.value);
    },
    AssignmentExpression(path) {
      const p = memberPath(path.node.left);
      if (!p) return;
      // window.X / globalThis.X / module.exports.X define the public surface
      if (/^(window|globalThis|self|module\.exports|exports)\./.test(p) || p === "module.exports") {
        globalAssigns.push({ target: p, value: preview(path.node.right, 80) });
      }
    },
  });

  // ---- collect every URL and path literal in the file ----
  // URLs are matched anywhere inside a string, not just at its start: obfuscated
  // bundles routinely hide endpoints in error messages and concatenations.
  const urls = new Map();
  const paths = new Set();
  const noteUrl = (raw, line) => {
    for (const m of raw.matchAll(URL_ANYWHERE)) {
      const u = m[0].replace(TRAILING_PUNCT, "");
      if (u.length > 8 && !urls.has(u)) urls.set(u, { url: u, line });
    }
  };
  traverse(ast, {
    StringLiteral(path) {
      const v = path.node.value;
      const line = path.node.loc ? path.node.loc.start.line : null;
      noteUrl(v, line);
      if (!HAS_URL.test(v) && PATH_LIKE.test(v)) paths.add(v);
    },
    TemplateLiteral(path) {
      const raw = path.node.quasis.map((q) => q.value.cooked || "").join(INTERP_MARK);
      const line = path.node.loc ? path.node.loc.start.line : null;
      noteUrl(raw, line);
      if (!HAS_URL.test(raw) && PATH_LIKE.test(raw)) paths.add(raw);
    },
  });

  // strip the transient bookkeeping fields before emitting
  for (const fn of functions) {
    fn.control.max_depth = undefined;
    delete fn.control.max_depth;
  }

  return {
    lines: lines.length,
    bytes: Buffer.byteLength(code, "utf8"),
    functions,
    classes,
    call_graph: { edges, resolution: "name-based (approximate)" },
    module: {
      exports: [...new Set(exportsFound)],
      imports: [...new Set(imports)],
      global_assignments: globalAssigns.slice(0, 40),
    },
    literals: { urls: [...urls.values()], paths: [...paths] },
    // Whether the functions above describe the module's own logic at all, or
    // only a bytecode interpreter standing in front of it. Everything else in
    // this file is worthless if the verdict here is "vm-obfuscated".
    vm_signals: detectVmSignals(ast, code),
  };
}

function cli() {
  const [input, output] = process.argv.slice(2);
  if (!input || !output) {
    process.stderr.write("usage: structure.mjs <input.js> <output.json>\n");
    process.exit(2);
  }
  const code = fs.readFileSync(input, "utf8");
  let data;
  try {
    data = extractStructure(code);
  } catch (err) {
    process.stderr.write("structure extraction failed: " + (err && err.message) + "\n");
    process.exit(3);
  }
  data.source_file = input;
  fs.writeFileSync(output, JSON.stringify(data, null, 2));
  process.stdout.write(JSON.stringify({
    functions: data.functions.length,
    classes: data.classes.length,
    edges: data.call_graph.edges.length,
    urls: data.literals.urls.length,
    vm: data.vm_signals.verdict,
  }) + "\n");
}

if (import.meta.url === "file://" + process.argv[1]) cli();
