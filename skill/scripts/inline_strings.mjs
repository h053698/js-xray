#!/usr/bin/env node
// AST-based string-array inlining for residual decoders webcrack leaves behind.
//
// Why AST: files that declare one string array per IIFE scope reuse short alias
// names (t, e, i, C) across scopes. A textual pass cannot tell those apart and
// silently resolves indices against the wrong array. Babel gives us real scope
// bindings, so every decoder call resolves against the array actually in scope.
import fs from "node:fs";
import { parse } from "@babel/parser";
import _traverse from "@babel/traverse";
import _generate from "@babel/generator";

const traverse = _traverse.default || _traverse;
const generate = _generate.default || _generate;

const MIN_ARRAY = 3;

// Identifiers whose presence means the decoder does more than an index lookup
// (base64, RC4, char math). Resolving those by index would produce wrong strings.
const IMPURE = new Set([
  "atob", "btoa", "charCodeAt", "fromCharCode", "decodeURIComponent",
  "encodeURIComponent", "unescape", "escape", "String", "parseInt", "Buffer",
]);

const RESERVED = new Set([
  "break", "case", "catch", "class", "const", "continue", "debugger", "default",
  "delete", "do", "else", "enum", "export", "extends", "false", "finally", "for",
  "function", "if", "import", "in", "instanceof", "new", "null", "return", "super",
  "switch", "this", "throw", "true", "try", "typeof", "var", "void", "while",
  "with", "yield", "let", "static", "await", "implements", "interface", "package",
  "private", "protected", "public",
]);

const IDENT_RE = /^[A-Za-z_$][A-Za-z0-9_$]*$/;

function parseSource(code) {
  const modes = ["unambiguous", "script", "module"];
  let lastErr;
  for (const sourceType of modes) {
    try {
      return parse(code, { sourceType, allowReturnOutsideFunction: true });
    } catch (err) {
      lastErr = err;
    }
  }
  throw lastErr;
}

// An array literal made entirely of string literals, or null.
function stringArrayOf(node) {
  if (!node || node.type !== "ArrayExpression") return null;
  if (node.elements.length < MIN_ARRAY) return null;
  const out = [];
  for (const el of node.elements) {
    if (!el || el.type !== "StringLiteral") return null;
    out.push(el.value);
  }
  return out;
}

// Offset in  arr[i]  /  arr[i - 4]  /  arr[i -= 0x1f]
function offsetOf(prop) {
  if (!prop) return null;
  if (prop.type === "Identifier") return 0;
  if (prop.type === "NumericLiteral") return null; // constant index, not a decoder
  const isSub =
    (prop.type === "BinaryExpression" && prop.operator === "-") ||
    (prop.type === "AssignmentExpression" && prop.operator === "-=");
  if (!isSub) return null;
  const left = prop.left;
  const right = prop.right;
  if (!left || left.type !== "Identifier") return null;
  if (!right || right.type !== "NumericLiteral") return null;
  return right.value;
}

export function inlineStrings(code, opts = {}) {
  const normalizeMembers = opts.normalizeMembers !== false;
  const ast = parseSource(code);

  // binding -> string[]   for  var a = ["x","y","z"]
  const arrayBindings = new Map();
  // binding -> string[]   for  function h() { const a = [...]; return ...; }
  const holderBindings = new Map();

  traverse(ast, {
    VariableDeclarator(path) {
      const arr = stringArrayOf(path.node.init);
      if (!arr) return;
      if (path.node.id.type !== "Identifier") return;
      const binding = path.scope.getBinding(path.node.id.name);
      if (binding) arrayBindings.set(binding, arr);
    },
    Function(path) {
      const id = path.node.id;
      if (!id || path.node.params.length !== 0) return;
      const body = path.node.body;
      if (!body || body.type !== "BlockStatement") return;
      let found = null;
      for (const stmt of body.body) {
        if (stmt.type !== "VariableDeclaration") continue;
        for (const decl of stmt.declarations) {
          const arr = stringArrayOf(decl.init);
          if (arr) found = arr;
        }
      }
      if (!found) return;
      const binding = path.scope.getBinding(id.name) ||
        (path.parentPath && path.parentPath.scope.getBinding(id.name));
      if (binding) holderBindings.set(binding, found);
    },
  });

  // Resolve what array an identifier refers to inside a decoder body.
  function arrayForIdentifier(path, name) {
    const binding = path.scope.getBinding(name);
    if (!binding) return null;
    if (arrayBindings.has(binding)) return arrayBindings.get(binding);
    if (holderBindings.has(binding)) return holderBindings.get(binding);
    // local alias: const e = U();  or  const e = someArray;
    const init = binding.path && binding.path.node && binding.path.node.init;
    if (!init) return null;
    if (init.type === "CallExpression" && init.callee.type === "Identifier") {
      const target = binding.path.scope.getBinding(init.callee.name);
      if (target && holderBindings.has(target)) return holderBindings.get(target);
    }
    if (init.type === "Identifier") {
      const target = binding.path.scope.getBinding(init.name);
      if (target && arrayBindings.has(target)) return arrayBindings.get(target);
      if (target && holderBindings.has(target)) return holderBindings.get(target);
    }
    const direct = stringArrayOf(init);
    if (direct) return direct;
    return null;
  }

  // binding -> { array, offset, name }
  const resolvers = new Map();

  traverse(ast, {
    Function(path) {
      const id = path.node.id;
      if (!id) return;
      const binding = path.scope.getBinding(id.name) ||
        (path.parentPath && path.parentPath.scope.getBinding(id.name));
      if (!binding || holderBindings.has(binding) || resolvers.has(binding)) return;

      let impure = false;
      let hit = null;
      path.traverse({
        Identifier(inner) {
          if (IMPURE.has(inner.node.name)) impure = true;
        },
        MemberExpression(inner) {
          if (hit || !inner.node.computed) return;
          if (inner.node.object.type !== "Identifier") return;
          const offset = offsetOf(inner.node.property);
          if (offset === null) return;
          const arr = arrayForIdentifier(inner, inner.node.object.name);
          if (arr) hit = { array: arr, offset };
        },
      });
      if (impure || !hit) return;
      resolvers.set(binding, { array: hit.array, offset: hit.offset, name: id.name });
    },
  });

  // const C = O;  -> C resolves like O, scoped to C's own binding
  let aliasAdded = true;
  const aliases = [];
  while (aliasAdded) {
    aliasAdded = false;
    traverse(ast, {
      VariableDeclarator(path) {
        const { id, init } = path.node;
        if (!init || init.type !== "Identifier" || id.type !== "Identifier") return;
        const self = path.scope.getBinding(id.name);
        if (!self || resolvers.has(self)) return;
        const target = path.scope.getBinding(init.name);
        if (!target || !resolvers.has(target)) return;
        const spec = resolvers.get(target);
        resolvers.set(self, { ...spec, name: id.name, aliasOf: spec.name });
        aliases.push({ alias: id.name, of: spec.name });
        aliasAdded = true;
      },
    });
  }

  const stats = {
    arrays: arrayBindings.size + holderBindings.size,
    decoders: [],
    aliases,
    replaced: 0,
    unresolved: 0,
    members_normalized: 0,
    per_decoder: {},
  };
  const seen = new Set();
  for (const spec of resolvers.values()) {
    const key = spec.name + "/" + spec.offset;
    if (seen.has(key)) continue;
    seen.add(key);
    stats.decoders.push({
      name: spec.name,
      offset: spec.offset,
      array_size: spec.array.length,
      alias_of: spec.aliasOf || null,
    });
  }

  if (resolvers.size === 0) {
    return { code, stats, changed: false };
  }

  traverse(ast, {
    CallExpression(path) {
      const { callee, arguments: args } = path.node;
      if (callee.type !== "Identifier" || args.length !== 1) return;
      const arg = args[0];
      if (!arg || arg.type !== "NumericLiteral") return;
      const binding = path.scope.getBinding(callee.name);
      if (!binding || !resolvers.has(binding)) return;
      const spec = resolvers.get(binding);
      const idx = arg.value - spec.offset;
      if (!Number.isInteger(idx) || idx < 0 || idx >= spec.array.length) {
        stats.unresolved += 1;
        return;
      }
      path.replaceWith({ type: "StringLiteral", value: spec.array[idx] });
      stats.replaced += 1;
      stats.per_decoder[spec.name] = (stats.per_decoder[spec.name] || 0) + 1;
    },
  });

  if (normalizeMembers) {
    const canDot = (v) => IDENT_RE.test(v) && !RESERVED.has(v);
    traverse(ast, {
      "MemberExpression|OptionalMemberExpression"(path) {
        const n = path.node;
        if (!n.computed || !n.property || n.property.type !== "StringLiteral") return;
        if (!canDot(n.property.value)) return;
        n.property = { type: "Identifier", name: n.property.value };
        n.computed = false;
        stats.members_normalized += 1;
      },
      "ObjectProperty|ObjectMethod|ClassMethod|ClassProperty|ClassPrivateProperty"(path) {
        const n = path.node;
        if (!n.computed || !n.key || n.key.type !== "StringLiteral") return;
        if (!canDot(n.key.value)) return;
        n.key = { type: "Identifier", name: n.key.value };
        n.computed = false;
        stats.members_normalized += 1;
      },
    });
  }

  const out = generate(ast, {
    comments: true,
    jsescOption: { minimal: true },
  }).code;

  return { code: out, stats, changed: stats.replaced > 0 || stats.members_normalized > 0 };
}

function cli() {
  const [input, output, metaPath] = process.argv.slice(2);
  if (!input || !output) {
    process.stderr.write("usage: inline_strings.mjs <input.js> <output.js> [meta.json]\n");
    process.exit(2);
  }
  const code = fs.readFileSync(input, "utf8");
  let result;
  try {
    result = inlineStrings(code);
  } catch (err) {
    process.stderr.write("inline failed: " + (err && err.message) + "\n");
    process.exit(3);
  }

  // Verification gate: the rewritten source must still parse. If it does not,
  // emit the input untouched rather than handing downstream a broken file.
  let valid = true;
  let parseError = null;
  try {
    parseSource(result.code);
  } catch (err) {
    valid = false;
    parseError = (err && err.message) || String(err);
  }

  const meta = { ...result.stats, valid, parse_error: parseError, rolled_back: !valid };
  fs.writeFileSync(output, valid ? result.code : code);
  if (metaPath) fs.writeFileSync(metaPath, JSON.stringify(meta, null, 2));
  process.stdout.write(JSON.stringify(meta, null, 2) + "\n");
  process.exit(valid ? 0 : 4);
}

if (import.meta.url === "file://" + process.argv[1]) cli();
