// Flattening-shaped code the deflatten pass must refuse to touch.
//
// Everything here *looks* like the patterns deflatten.mjs handles, but each case
// carries a property that makes the rewrite unsound. The point of the fixture is
// the negative: a wrong transform here would still produce valid JavaScript, so
// `node --check` cannot catch it and every later stage would go on to explain
// code that never ran. The test asserts these constructs survive verbatim.
//
// Like fixtures/flattened.js, every effect goes through TRACE and is printed at
// the end, so before/after execution can be compared.
var TRACE = [];

function record(label, value) {
  TRACE.push(label + "=" + value);
  return value;
}

// REFUSE (b): the sequence is computed at runtime, so the execution order is
// not knowable statically. KEEP_RUNTIME_SEQ marks it for the test.
function runtimeSequence(pick) {
  var order = pick ? "1|0" : "0|1";
  var steps = order.split("|"); // KEEP_RUNTIME_SEQ
  var cursor = 0;
  while (!![]) {
    switch (steps[cursor++]) {
      case "0":
        var first = "A";
        continue;
      case "1":
        var second = "B";
        continue;
    }
    break;
  }
  return record("runtimeSequence", String(first) + String(second));
}

// REFUSE (b): a case body breaks out of the dispatcher instead of continuing.
// Linearising it would drop the early exit, changing what runs.
function earlyBreak(flag) {
  var STORE = { order: "0|1|2" };
  var out = "";
  var steps = STORE.order.split("|"); // KEEP_EARLY_BREAK
  var cursor = 0;
  while (!![]) {
    switch (steps[cursor++]) {
      case "0":
        out = out + "a";
        continue;
      case "1":
        if (flag) {
          break;
        }
        out = out + "b";
        continue;
      case "2":
        out = out + "c";
        continue;
    }
    break;
  }
  return record("earlyBreak", out);
}

// REFUSE (b): the cursor is read by code outside the dispatcher, so how far the
// sequence advanced is observable and reordering it would be visible.
function observedCursor() {
  var STORE = { order: "1|0" };
  var steps = STORE.order.split("|"); // KEEP_OBSERVED_CURSOR
  var cursor = 0;
  while (!![]) {
    switch (steps[cursor++]) {
      case "0":
        var tail = "z";
        continue;
      case "1":
        var head = "y";
        continue;
    }
    break;
  }
  return record("observedCursor", head + tail + cursor);
}

// REFUSE (b): the storage object has a property written after it is declared,
// so the sequence string read from it cannot be trusted.
function mutatedStore() {
  var STORE = { order: "0|1" };
  STORE.order = "1|0";
  var steps = STORE.order.split("|"); // KEEP_MUTATED_STORE
  var cursor = 0;
  while (!![]) {
    switch (steps[cursor++]) {
      case "0":
        var one = "p";
        continue;
      case "1":
        var two = "q";
        continue;
    }
    break;
  }
  return record("mutatedStore", String(one) + String(two));
}

// REFUSE (a): the two operands are same-named variables from *different*
// scopes holding different values, so the comparison is not decided. A pass
// that matched on the name alone would drop a live branch here.
var token = "outer";
function shadowedScopes() {
  var token = "inner";
  var probe = function (a, b) {
    return a === b;
  };
  if (probe(token, globalThis.__jsxrayToken)) {
    return record("shadowedScopes", "equal"); // KEEP_SHADOWED
  } else {
    return record("shadowedScopes", "different");
  }
}

// REFUSE (a): the "comparison helper" also records a side effect, so routing
// the comparison through it is not equivalent to writing the operator inline --
// dropping either branch would delete an observable call.
function impureHelper() {
  var STORE = {
    token: "same",
    check: function (a, b) {
      TRACE.push("helper-ran"); // KEEP_IMPURE_HELPER
      return a === b;
    }
  };
  if (STORE.check(STORE.token, STORE.token)) {
    return record("impureHelper", "yes");
  } else {
    return record("impureHelper", "no");
  }
}

// REFUSE (a): the test is decided, but the dead branch declares a var that code
// after the branch reads. Today that read yields undefined; deleting the branch
// would make it a ReferenceError.
function hoistedFromDeadBranch() {
  if ("aaaaa" === "bbbbb") {
    var leaked = "set"; // KEEP_HOISTED_VAR
  }
  return record("hoistedFromDeadBranch", String(leaked));
}

globalThis.__jsxrayToken = "outer";
runtimeSequence(true);
earlyBreak(false);
observedCursor();
mutatedStore();
shadowedScopes();
impureHelper();
hoistedFromDeadBranch();
console.log(TRACE.join("|"));
