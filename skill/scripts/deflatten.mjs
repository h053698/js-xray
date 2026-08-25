#!/usr/bin/env node
// AST-based control-flow deflattening for javascript-obfuscator residue.
//
// Why this exists even though webcrack already ships control-flow-switch and
// dead-code passes: both of webcrack's matchers require the deciding value to
// be a literal in place. Its control-flow-switch wants a discriminant built
// from "2|4|3".split("|"), and its dead-code pass wants "abcde" === "abcde".
// javascript-obfuscator normally routes those values through a per-function
// "control flow storage" object instead:
//
//     const S = { VJuTL: "QkPnV", JsWMV: "4|5|1|3|0|2",
//                 YqrfQ: function (a, b) { return a === b; } };
//     if (S.YqrfQ(S.VJuTL, S.VJuTL)) { dead } else { live }
//     var seq = S.JsWMV.split("|");
//
// webcrack inlines that object first (control-flow-object) and then its two
// passes fire. When the inlining bails -- the object escapes, a property is
// written, a key is dynamic -- the object survives and both downstream passes
// silently stop matching. What reaches clean.js is then a file whose string
// array is fully decoded but half of whose lines are unreachable. This pass
// closes exactly that gap: it resolves the deciding value through the storage
// object, scope-correctly, and then does what webcrack would have done.
//
// The governing constraint is that a wrong decision here is invisible. Dropping
// the live branch instead of the dead one, or reordering cases that are not
// independent, still produces valid JavaScript -- so `node --check` and every
// later stage accept it and go on to explain code that never ran. Every rule
// below therefore refuses rather than guesses, and each refusal is counted in
// the meta so a partial result is visible instead of looking like a clean one.
import fs from "node:fs";
import { parse } from "@babel/parser";
import _traverse from "@babel/traverse";
import _generate from "@babel/generator";
import * as t from "@babel/types";

const traverse = _traverse.default || _traverse;
const generate = _generate.default || _generate;

// Equality operators only. Relational ones are not decidable from "both sides
// are the same value" in any way that helps here.
const EQ_OPS = new Set(["===", "!==", "==", "!="]);

const LOOP_TYPES = new Set([
  "ForStatement", "ForInStatement", "ForOfStatement",
  "WhileStatement", "DoWhileStatement",
]);

const FUNCTION_TYPES = new Set([
  "FunctionDeclaration", "FunctionExpression", "ArrowFunctionExpression",
  "ObjectMethod", "ClassMethod", "ClassPrivateMethod",
]);

const MAX_PASSES = 6;
const SEQ_RE = /^[0-9]+([|][0-9]+)*$/;
const LABEL_RE = /^[0-9]+$/;

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

function bump(map, key) {
  map[key] = (map[key] || 0) + 1;
}

// ---------------------------------------------------------------------------
// static value resolution
// ---------------------------------------------------------------------------

// The property name in  o.x  /  o["x"]  /  o[0], or null when it is dynamic.
function memberKeyOf(node) {
  if (!node.property) return null;
  if (node.computed) {
    if (node.property.type === "StringLiteral") return node.property.value;
    if (node.property.type === "NumericLiteral") return String(node.property.value);
    return null;
  }
  if (node.property.type === "Identifier") return node.property.name;
  return null;
}

// The object literal behind an identifier, but only when that binding is a
// closed book: never reassigned, and every reference to it a plain property
// read under a statically known key. One bare mention of the identifier is
// enough to disqualify it, because handing the object to anything else means
// some other code could have rewritten the property we are about to trust.
// This is the check whose absence would let a wrong branch be dropped.
function safeObjectLiteral(path, name) {
  const binding = path.scope.getBinding(name);
  if (!binding) return null;
  if (binding.kind === "param") return null;
  if (binding.constantViolations && binding.constantViolations.length) return null;
  const decl = binding.path;
  if (!decl || !decl.node || decl.node.type !== "VariableDeclarator") return null;
  const init = decl.node.init;
  if (!init || init.type !== "ObjectExpression") return null;

  for (const ref of binding.referencePaths || []) {
    const parent = ref.parentPath;
    if (!parent || !parent.node) return null;
    const pn = parent.node;
    if (pn.type !== "MemberExpression" && pn.type !== "OptionalMemberExpression") return null;
    if (pn.object !== ref.node) return null;         // used as a key, not the object
    if (memberKeyOf(pn) === null) return null;       // dynamic key: unknowable
    const gp = parent.parentPath;
    if (gp && gp.node) {
      const gn = gp.node;
      if (gn.type === "AssignmentExpression" && gn.left === pn) return null;  // o.x = ...
      if (gn.type === "UpdateExpression" && gn.argument === pn) return null;  // o.x++
      if (gn.type === "UnaryExpression" && gn.operator === "delete") return null;
      if (gn.type === "ForOfStatement" && gn.left === pn) return null;
      if (gn.type === "ForInStatement" && gn.left === pn) return null;
    }
  }
  return init;
}

// The value node for one key of an object literal. Returns undefined when the
// literal cannot be read with certainty -- a spread, a dynamic key, a method,
// or a duplicate key all mean "do not trust this lookup".
function propertyValue(objNode, key) {
  let found;
  let hits = 0;
  for (const prop of objNode.properties) {
    if (prop.type === "SpreadElement") return undefined;
    if (prop.type === "ObjectMethod") {
      // a getter could return anything; only bail if it could be our key
      const mk = prop.computed
        ? (prop.key.type === "StringLiteral" ? prop.key.value : null)
        : (prop.key.type === "Identifier" ? prop.key.name
          : prop.key.type === "StringLiteral" ? prop.key.value : null);
      if (mk === null || mk === key) return undefined;
      continue;
    }
    if (prop.type !== "ObjectProperty") return undefined;
    const pk = prop.computed
      ? (prop.key.type === "StringLiteral" ? prop.key.value
        : prop.key.type === "NumericLiteral" ? String(prop.key.value) : null)
      : (prop.key.type === "Identifier" ? prop.key.name
        : prop.key.type === "StringLiteral" ? prop.key.value
        : prop.key.type === "NumericLiteral" ? String(prop.key.value) : null);
    if (pk === null) return undefined;   // dynamic key: could be the one we want
    if (pk === key) { found = prop.value; hits += 1; }
  }
  if (hits !== 1) return undefined;
  return found;
}

// One step of indirection: the node a  storage.PROP  read resolves to.
function memberTarget(path, node) {
  if (!node) return undefined;
  if (node.type !== "MemberExpression" && node.type !== "OptionalMemberExpression") return undefined;
  if (node.object.type !== "Identifier") return undefined;
  const key = memberKeyOf(node);
  if (key === null) return undefined;
  const obj = safeObjectLiteral(path, node.object.name);
  if (!obj) return undefined;
  return propertyValue(obj, key);
}

function literalValue(node) {
  if (!node) return undefined;
  switch (node.type) {
    case "StringLiteral":
    case "NumericLiteral":
    case "BooleanLiteral":
      return { value: node.value };
    case "NullLiteral":
      return { value: null };
    default:
      return undefined;
  }
}

// A primitive value for an expression, or undefined. Deliberately shallow: a
// literal, a never-reassigned binding initialised to a literal, or a property of
// a closed storage object. No literal can be NaN, which is what makes the
// comparison in decideTest() safe to evaluate in the host.
function staticPrimitive(path, node, depth) {
  const d = depth || 0;
  if (!node || d > 3) return undefined;
  const direct = literalValue(node);
  if (direct) return direct;

  if (node.type === "Identifier") {
    const binding = path.scope.getBinding(node.name);
    if (!binding || binding.kind === "param") return undefined;
    if (binding.constantViolations && binding.constantViolations.length) return undefined;
    const decl = binding.path;
    if (!decl || !decl.node || decl.node.type !== "VariableDeclarator") return undefined;
    return staticPrimitive(decl, decl.node.init, d + 1);
  }

  const target = memberTarget(path, node);
  if (target === undefined) return undefined;
  return literalValue(target);
}

function staticString(path, node) {
  const prim = staticPrimitive(path, node);
  if (!prim || typeof prim.value !== "string") return null;
  return prim.value;
}

// Fold the small arithmetic javascript-obfuscator wraps constants in, so that
// `let i = -0x1a70 + 0x93d + 0x275 * 0x7` is recognisable as zero.
function staticNumber(node, depth) {
  const d = depth || 0;
  if (!node || d > 12) return null;
  if (node.type === "NumericLiteral") return node.value;
  if (node.type === "UnaryExpression") {
    const inner = staticNumber(node.argument, d + 1);
    if (inner === null) return null;
    if (node.operator === "-") return -inner;
    if (node.operator === "+") return inner;
    return null;
  }
  if (node.type === "BinaryExpression") {
    const l = staticNumber(node.left, d + 1);
    const r = staticNumber(node.right, d + 1);
    if (l === null || r === null) return null;
    switch (node.operator) {
      case "+": return l + r;
      case "-": return l - r;
      case "*": return l * r;
      case "/": return r === 0 ? null : l / r;
      case "%": return r === 0 ? null : l % r;
      default: return null;
    }
  }
  return null;
}

// Truthiness of a constant test, or null when it is not constant. Covers the
// obfuscator spellings of an infinite loop: while (true), while (!![]), while (!0).
function staticTruthiness(node, depth) {
  const d = depth || 0;
  if (!node || d > 6) return null;
  switch (node.type) {
    case "BooleanLiteral": return node.value;
    case "NumericLiteral": return node.value !== 0;
    case "StringLiteral": return node.value.length > 0;
    case "NullLiteral": return false;
    case "ArrayExpression":
    case "ObjectExpression":
    case "FunctionExpression":
    case "ArrowFunctionExpression":
      return true;
    case "UnaryExpression": {
      if (node.operator === "void") return false;
      if (node.operator !== "!") return null;
      const inner = staticTruthiness(node.argument, d + 1);
      return inner === null ? null : !inner;
    }
    default: return null;
  }
}

// ---------------------------------------------------------------------------
// (a) statically decidable branches
// ---------------------------------------------------------------------------

// The operator of a pure two-argument comparison helper, or null.
//
// Purity is enforced structurally rather than guessed at: the body must be a
// single `return p0 OP p1` over two plain identifier parameters. A function
// shaped like that cannot observe or change anything, so routing a comparison
// through it is equivalent to writing the operator inline. Anything else -- a
// second statement, a default or destructured parameter, an operand that is not
// one of the parameters -- returns null and the branch is left alone.
function comparisonOperatorOf(fnNode) {
  if (!fnNode) return null;
  if (fnNode.type !== "FunctionExpression" && fnNode.type !== "ArrowFunctionExpression") return null;
  if (fnNode.async || fnNode.generator) return null;
  const params = fnNode.params;
  if (params.length !== 2) return null;
  if (params[0].type !== "Identifier" || params[1].type !== "Identifier") return null;
  const a = params[0].name;
  const b = params[1].name;
  if (a === b) return null;

  let expr = fnNode.body;
  if (expr && expr.type === "BlockStatement") {
    const body = expr.body;
    if (body.length !== 1 || body[0].type !== "ReturnStatement") return null;
    expr = body[0].argument;
  }
  if (!expr || expr.type !== "BinaryExpression") return null;
  if (!EQ_OPS.has(expr.operator)) return null;
  if (expr.left.type !== "Identifier" || expr.right.type !== "Identifier") return null;
  const names = [expr.left.name, expr.right.name];
  // equality operators are symmetric, so either parameter order is fine
  if (!(names.indexOf(a) >= 0 && names.indexOf(b) >= 0)) return null;
  return expr.operator;
}

function resolveFunctionNode(path, callee) {
  if (!callee) return null;
  if (callee.type === "FunctionExpression" || callee.type === "ArrowFunctionExpression") return callee;
  if (callee.type === "Identifier") {
    const binding = path.scope.getBinding(callee.name);
    if (!binding) return null;
    if (binding.constantViolations && binding.constantViolations.length) return null;
    const decl = binding.path;
    if (!decl || !decl.node) return null;
    if (decl.node.type === "VariableDeclarator") return decl.node.init || null;
    return null;
  }
  const target = memberTarget(path, callee);
  return target === undefined ? null : target;
}

// true / false when the test is statically decided, null otherwise.
function decideTest(path, node, depth) {
  const d = depth || 0;
  if (!node || d > 4) return null;

  if (node.type === "UnaryExpression" && node.operator === "!") {
    const inner = decideTest(path, node.argument, d + 1);
    return inner === null ? null : !inner;
  }

  let op = null;
  let left = null;
  let right = null;

  if (node.type === "BinaryExpression" && EQ_OPS.has(node.operator)) {
    op = node.operator;
    left = node.left;
    right = node.right;
  } else if (node.type === "CallExpression" && node.arguments.length === 2) {
    op = comparisonOperatorOf(resolveFunctionNode(path, node.callee));
    if (!op) return null;
    left = node.arguments[0];
    right = node.arguments[1];
    if (left.type === "SpreadElement" || right.type === "SpreadElement") return null;
  } else {
    return null;
  }

  const lv = staticPrimitive(path, left);
  const rv = staticPrimitive(path, right);
  if (!lv || !rv) return null;

  switch (op) {
    case "===": return lv.value === rv.value;
    case "!==": return lv.value !== rv.value;
    // Loose equality only where it cannot coerce: same type makes == agree with
    // ===  for primitives, and no literal can be NaN.
    case "==": return typeof lv.value === typeof rv.value ? lv.value === rv.value : null;
    case "!=": return typeof lv.value === typeof rv.value ? lv.value !== rv.value : null;
    default: return null;
  }
}

function isInside(inner, outer) {
  let cur = inner;
  while (cur) {
    if (cur === outer) return true;
    cur = cur.parentPath;
  }
  return false;
}

// Names a subtree contributes to the enclosing function scope: var declarations
// and function declarations, both of which hoist out of the branch they are
// written in. Nested functions are skipped -- their vars belong to them.
function hoistedNames(path) {
  const names = [];
  const collectId = (id) => {
    if (!id) return;
    if (id.type === "Identifier") { names.push(id.name); return; }
    const keys = t.VISITOR_KEYS[id.type] || [];
    for (const key of keys) {
      const child = id[key];
      if (Array.isArray(child)) child.forEach((c) => c && collectId(c));
      else if (child && typeof child.type === "string") collectId(child);
    }
  };
  if (path.isVariableDeclaration() && path.node.kind === "var") {
    path.node.declarations.forEach((decl) => collectId(decl.id));
  }
  if (path.isFunctionDeclaration() && path.node.id) names.push(path.node.id.name);
  path.traverse({
    Function(inner) { inner.skip(); },
    VariableDeclaration(inner) {
      if (inner.node.kind !== "var") return;
      inner.node.declarations.forEach((decl) => collectId(decl.id));
    },
    FunctionDeclaration(inner) {
      if (inner.node.id) names.push(inner.node.id.name);
    },
  });
  return names;
}

// A dead branch is only safe to delete when nothing outside it can observe the
// declarations it hoists. `if (false) { var x = 1; } ... use(x)` reads undefined
// today; deleting the branch turns that into a ReferenceError, and no syntax
// check would catch it.
function deadBranchIsIsolated(deadPath) {
  const names = hoistedNames(deadPath);
  for (const name of names) {
    const binding = deadPath.scope.getBinding(name);
    if (!binding) return false;
    const uses = (binding.referencePaths || []).concat(binding.constantViolations || []);
    for (const use of uses) {
      if (!isInside(use, deadPath)) return false;
    }
  }
  return true;
}

// Splicing a block into its parent is only safe when the block introduces no
// lexical bindings of its own -- those are scoped to the block, and lifting them
// out could collide with, or leak into, the parent.
function blockIsSpliceable(blockNode) {
  for (const stmt of blockNode.body) {
    if (stmt.type === "VariableDeclaration" && stmt.kind !== "var") return false;
    if (stmt.type === "ClassDeclaration") return false;
    if (stmt.type === "FunctionDeclaration") return false;
  }
  return true;
}

function parentHoldsStatementList(path) {
  const parent = path.parentPath;
  if (!parent) return false;
  return parent.isBlockStatement() || parent.isProgram() ||
    parent.isSwitchCase() || parent.isStaticBlock();
}

function dropDeadBranches(ast, stats) {
  let changed = 0;
  traverse(ast, {
    IfStatement: {
      exit(path) {
        const verdict = decideTest(path, path.node.test);
        if (verdict === null) return;

        stats.dead_branches_examined += 1;

        const livePath = verdict ? path.get("consequent") : path.get("alternate");
        const deadPath = verdict ? path.get("alternate") : path.get("consequent");

        if (deadPath && deadPath.node && !deadBranchIsIsolated(deadPath)) {
          bump(stats.dead_branch_skips, "dead branch hoists a name used outside it");
          return;
        }

        if (!livePath || !livePath.node) {
          // `if (false) dead;` with no else: the whole statement goes
          path.remove();
          stats.dead_branches_dropped += 1;
          changed += 1;
          return;
        }

        if (livePath.isBlockStatement() && blockIsSpliceable(livePath.node) &&
            parentHoldsStatementList(path)) {
          const body = livePath.node.body;
          if (body.length === 0) path.remove();
          else path.replaceWithMultiple(body);
        } else {
          path.replaceWith(livePath.node);
        }
        stats.dead_branches_dropped += 1;
        changed += 1;
      },
    },
  });
  return changed;
}
// ---------------------------------------------------------------------------
// (b) split-sequence switch dispatchers
// ---------------------------------------------------------------------------

// Walk a statement list looking for jumps that would target the dispatcher loop
// or switch, which is what makes a case body non-relocatable. Jumps inside a
// nested loop or switch belong to that construct and are fine; a jump that would
// escape into the dispatcher is not, because linearising it would need a goto
// that JavaScript does not have.
function jumpEscapes(nodes) {
  let reason = null;

  const walk = (node, loopDepth, switchDepth) => {
    if (reason || !node || typeof node.type !== "string") return;
    if (FUNCTION_TYPES.has(node.type)) return;   // jumps cannot cross a function

    if (node.type === "LabeledStatement") {
      reason = "labeled statement in a case body";
      return;
    }
    if (node.type === "BreakStatement") {
      if (node.label) reason = "labeled break in a case body";
      else if (loopDepth === 0 && switchDepth === 0) reason = "break would exit the dispatcher";
      return;
    }
    if (node.type === "ContinueStatement") {
      if (node.label) reason = "labeled continue in a case body";
      else if (loopDepth === 0) reason = "conditional continue inside a case body";
      return;
    }

    const nextLoop = loopDepth + (LOOP_TYPES.has(node.type) ? 1 : 0);
    const nextSwitch = switchDepth + (node.type === "SwitchStatement" ? 1 : 0);
    const keys = t.VISITOR_KEYS[node.type] || [];
    for (const key of keys) {
      const child = node[key];
      if (Array.isArray(child)) {
        for (const c of child) walk(c, nextLoop, nextSwitch);
      } else if (child && typeof child.type === "string") {
        walk(child, nextLoop, nextSwitch);
      }
      if (reason) return;
    }
  };

  for (const node of nodes) {
    walk(node, 0, 0);
    if (reason) return reason;
  }
  return null;
}

function isTerminator(node) {
  return !!node && (node.type === "ReturnStatement" || node.type === "ThrowStatement");
}

function isPlainContinue(node) {
  return !!node && node.type === "ContinueStatement" && !node.label;
}

// Recognise the trio starting at index i:
//     var seq = <static "3|1|2">.split("|");
//     var idx = 0;
//     while (true) { switch (seq[idx++]) { ... } break; }
// Returns a shape-matched candidate (semantics unchecked) or null.
function matchDispatcherShape(bodyPaths, i) {
  const seqDeclPath = bodyPaths[i];
  const idxDeclPath = bodyPaths[i + 1];
  const loopPath = bodyPaths[i + 2];
  if (!seqDeclPath || !idxDeclPath || !loopPath) return null;

  if (!seqDeclPath.isVariableDeclaration() || seqDeclPath.node.declarations.length !== 1) return null;
  const seqDecl = seqDeclPath.node.declarations[0];
  if (!seqDecl.id || seqDecl.id.type !== "Identifier") return null;
  const call = seqDecl.init;
  if (!call || call.type !== "CallExpression" || call.arguments.length !== 1) return null;
  const sep = call.arguments[0];
  if (!sep || sep.type !== "StringLiteral" || sep.value !== "|") return null;
  const callee = call.callee;
  if (!callee) return null;
  if (callee.type !== "MemberExpression" && callee.type !== "OptionalMemberExpression") return null;
  if (memberKeyOf(callee) !== "split") return null;

  if (!idxDeclPath.isVariableDeclaration() || idxDeclPath.node.declarations.length !== 1) return null;
  const idxDecl = idxDeclPath.node.declarations[0];
  if (!idxDecl.id || idxDecl.id.type !== "Identifier") return null;

  let loopBodyPath = null;
  if (loopPath.isWhileStatement()) {
    if (staticTruthiness(loopPath.node.test) !== true) return null;
    loopBodyPath = loopPath.get("body");
  } else if (loopPath.isForStatement()) {
    const n = loopPath.node;
    if (n.init || n.update) return null;
    if (n.test && staticTruthiness(n.test) !== true) return null;
    loopBodyPath = loopPath.get("body");
  } else {
    return null;
  }
  if (!loopBodyPath || !loopBodyPath.isBlockStatement()) return null;

  const inner = loopBodyPath.get("body");
  if (inner.length !== 2) return null;
  if (!inner[0].isSwitchStatement()) return null;
  if (!inner[1].isBreakStatement() || inner[1].node.label) return null;

  const switchPath = inner[0];
  const disc = switchPath.node.discriminant;
  if (!disc || disc.type !== "MemberExpression" || !disc.computed) return null;
  if (disc.object.type !== "Identifier" || disc.object.name !== seqDecl.id.name) return null;
  const upd = disc.property;
  if (!upd || upd.type !== "UpdateExpression" || upd.operator !== "++" || upd.prefix) return null;
  if (!upd.argument || upd.argument.type !== "Identifier") return null;
  if (upd.argument.name !== idxDecl.id.name) return null;

  return { seqDeclPath, seqDecl, callee, idxDeclPath, idxDecl, loopPath, switchPath };
}

// Everything that has to hold before the case bodies may be reordered.
// Returns { statements, ... } on success or { reason } on refusal.
function validateDispatcher(c) {
  const seqText = staticString(c.seqDeclPath, c.callee.object);
  if (seqText === null) return { reason: "sequence string not statically known" };
  if (!SEQ_RE.test(seqText)) return { reason: "sequence is not a plain index list" };

  const start = staticNumber(c.idxDecl.init);
  if (start !== 0) return { reason: "cursor does not provably start at 0" };

  // Both dispatcher variables must be private to the dispatcher: one read each,
  // from the discriminant. Anything else reading them means the sequence is
  // observable and reordering could be noticed.
  const seqBinding = c.seqDeclPath.scope.getBinding(c.seqDecl.id.name);
  const idxBinding = c.idxDeclPath.scope.getBinding(c.idxDecl.id.name);
  if (!seqBinding || !idxBinding) return { reason: "dispatcher bindings not resolvable" };
  if (seqBinding.path.node !== c.seqDecl || idxBinding.path.node !== c.idxDecl) {
    return { reason: "dispatcher names shadowed by another binding" };
  }
  if ((seqBinding.referencePaths || []).length !== 1) return { reason: "sequence variable read elsewhere" };
  if ((idxBinding.referencePaths || []).length !== 1) return { reason: "cursor variable read elsewhere" };
  if ((seqBinding.constantViolations || []).length !== 0) return { reason: "sequence variable reassigned" };
  // the ++ in the discriminant is the cursor's only legitimate write
  if ((idxBinding.constantViolations || []).length > 1) return { reason: "cursor written outside the dispatcher" };

  const cases = c.switchPath.node.cases;
  if (!cases.length) return { reason: "empty switch" };

  const byLabel = new Map();
  for (const cs of cases) {
    if (!cs.test) return { reason: "switch has a default clause" };
    if (cs.test.type !== "StringLiteral" || !LABEL_RE.test(cs.test.value)) {
      return { reason: "case label is not a numeric string" };
    }
    if (byLabel.has(cs.test.value)) return { reason: "duplicate case label" };
    if (!cs.consequent.length) return { reason: "empty case body (fallthrough)" };

    const last = cs.consequent[cs.consequent.length - 1];
    let body;
    if (isPlainContinue(last)) {
      body = cs.consequent.slice(0, -1);
    } else if (isTerminator(last)) {
      body = cs.consequent.slice();
    } else {
      return { reason: "case body does not end in continue/return/throw" };
    }

    const escape = jumpEscapes(body);
    if (escape) return { reason: escape };

    for (const stmt of body) {
      if (stmt.type === "VariableDeclaration" && stmt.kind !== "var") {
        return { reason: "case body declares a lexical binding" };
      }
      if (stmt.type === "ClassDeclaration") return { reason: "case body declares a class" };
    }
    byLabel.set(cs.test.value, body);
  }

  const order = seqText.split("|");
  if (new Set(order).size !== order.length) return { reason: "sequence repeats an index" };
  if (order.length !== byLabel.size) return { reason: "sequence does not cover every case exactly once" };

  const statements = [];
  for (const label of order) {
    if (!byLabel.has(label)) return { reason: "sequence references a missing case" };
    statements.push.apply(statements, byLabel.get(label));
  }
  return { statements, order, cases: byLabel.size };
}

// Try every position in one statement list, applying at most one dispatcher per
// call so the paths stay coherent; the caller loops until nothing applies.
function lineariseInList(listPath, getBody, spliceBody, stats) {
  for (let guard = 0; guard < 64; guard += 1) {
    const bodyPaths = getBody();
    if (!Array.isArray(bodyPaths)) return 0;
    let applied = 0;
    for (let i = 0; i + 2 < bodyPaths.length; i += 1) {
      const candidate = matchDispatcherShape(bodyPaths, i);
      if (!candidate) continue;
      stats.switch_sequences_examined += 1;
      const verdict = validateDispatcher(candidate);
      if (verdict.reason) {
        bump(stats.switch_skips, verdict.reason);
        continue;
      }
      spliceBody(i, verdict.statements);
      stats.switch_sequences_linearised += 1;
      stats.statements_linearised += verdict.statements.length;
      listPath.scope.crawl();
      applied = 1;
      break;
    }
    if (!applied) return guard;
  }
  return 64;
}

function lineariseDispatchers(ast, stats) {
  let changed = 0;

  const handleBlock = (path) => {
    changed += lineariseInList(path,
      () => path.get("body"),
      (i, statements) => path.node.body.splice.apply(path.node.body, [i, 3].concat(statements)),
      stats);
  };

  traverse(ast, {
    // exit order is bottom-up, so a dispatcher nested inside a case body is
    // flattened before the dispatcher that contains it
    BlockStatement: { exit: handleBlock },
    Program: { exit: handleBlock },
    StaticBlock: { exit: handleBlock },
    SwitchCase: {
      exit(path) {
        changed += lineariseInList(path,
          () => path.get("consequent"),
          (i, statements) => path.node.consequent.splice.apply(
            path.node.consequent, [i, 3].concat(statements)),
          stats);
      },
    },
  });

  return changed;
}

// ---------------------------------------------------------------------------

export function deflatten(code, opts) {
  const options = opts || {};
  const maxPasses = options.maxPasses || MAX_PASSES;
  const stats = {
    passes: 0,
    dead_branches_dropped: 0,
    dead_branches_examined: 0,
    dead_branch_skips: {},
    switch_sequences_linearised: 0,
    switch_sequences_examined: 0,
    switch_skips: {},
    statements_linearised: 0,
    lines_before: code.split("\n").length,
    lines_after: code.split("\n").length,
  };

  let current = code;
  let total = 0;
  let firstPassSkips = null;

  for (let pass = 0; pass < maxPasses; pass += 1) {
    // A fresh parse per pass keeps scope information exact. The transforms above
    // read bindings to decide what is safe to delete, and reading a binding that
    // an earlier edit invalidated is precisely how a wrong branch gets dropped.
    const ast = parseSource(current);
    let touched = 0;
    touched += dropDeadBranches(ast, stats);
    touched += lineariseDispatchers(ast, stats);
    stats.passes = pass + 1;
    if (pass === 0) {
      // Later passes re-walk nodes the first pass already refused, which would
      // inflate the refusal counts. Report the first pass's view.
      firstPassSkips = {
        dead: Object.assign({}, stats.dead_branch_skips),
        sw: Object.assign({}, stats.switch_skips),
        deadExamined: stats.dead_branches_examined,
        swExamined: stats.switch_sequences_examined,
      };
    }
    if (!touched) break;
    total += touched;
    current = generate(ast, { comments: true, jsescOption: { minimal: true } }).code;
  }

  if (firstPassSkips) {
    stats.dead_branch_skips = firstPassSkips.dead;
    stats.switch_skips = firstPassSkips.sw;
    stats.dead_branches_examined = firstPassSkips.deadExamined;
    stats.switch_sequences_examined = firstPassSkips.swExamined;
  }
  if (total > 0) stats.lines_after = current.split("\n").length;

  return { code: current, stats, changed: total > 0 };
}

function cli() {
  const argv = process.argv.slice(2);
  const input = argv[0];
  const output = argv[1];
  const metaPath = argv[2];
  if (!input || !output) {
    process.stderr.write("usage: deflatten.mjs <input.js> <output.js> [meta.json]\n");
    process.exit(2);
  }
  const code = fs.readFileSync(input, "utf8");
  let result;
  try {
    result = deflatten(code);
  } catch (err) {
    process.stderr.write("deflatten failed: " + (err && err.message) + "\n");
    process.exit(3);
  }

  // Same gate as the inlining pass: the rewrite must still parse, or the input
  // goes downstream untouched. Note that parsing is necessary but nowhere near
  // sufficient here -- see the header comment; the real guard is that each
  // transform refuses anything it cannot prove.
  let valid = true;
  let parseError = null;
  try {
    parseSource(result.code);
  } catch (err) {
    valid = false;
    parseError = (err && err.message) || String(err);
  }

  const meta = Object.assign({}, result.stats,
    { valid, parse_error: parseError, rolled_back: !valid });
  fs.writeFileSync(output, valid ? result.code : code);
  if (metaPath) fs.writeFileSync(metaPath, JSON.stringify(meta, null, 2));
  process.stdout.write(JSON.stringify(meta, null, 2) + "\n");
  process.exit(valid ? 0 : 4);
}

if (import.meta.url === "file://" + process.argv[1]) cli();
