// Control-flow flattening residue, in the shape it reaches this pass.
//
// This is what a javascript-obfuscator file looks like *after* webcrack has
// decoded the string array but failed to inline the per-function control-flow
// storage object: the object literal survives, so webcrack's own
// control-flow-switch and dead-code passes no longer match anything and the
// flattening stays. Two patterns are present:
//
//   (a) a branch whose test is statically decided -- both operands of the
//       comparison resolve to the same storage property, routed through a pure
//       two-argument comparison helper, so one side is unreachable;
//   (b) a while/switch dispatcher driven by a split sequence constant, whose
//       case bodies are the original statements in shuffled order.
//
// Every observable effect goes through TRACE and is printed at the end, so a
// test can run this file before and after the transform and compare stdout.
// That is the check that matters: a deflattening bug produces valid JavaScript,
// so only running the code can tell the two apart.
var TRACE = [];

function record(label, value) {
  TRACE.push(label + "=" + value);
  return value;
}

// (b) plain dispatcher: five statements, executed in sequence order 3,1,4,0,2.
function assemble(words) {
  var STORE = {
    order: "3|1|4|0|2",
    prefix: "item",
    joiner: function (a, b) {
      return a + b;
    }
  };
  var steps = STORE.order.split("|");
  var cursor = 0;
  while (!![]) {
    switch (steps[cursor++]) {
      case "0":
        var total = 0;
        continue;
      case "1":
        var parts = [];
        continue;
      case "2":
        var index = 0;
        while (index < words.length) {
          parts.push(STORE.joiner(STORE.prefix + ":", words[index].toUpperCase()));
          total = total + words[index].length;
          index = index + 1;
        }
        continue;
      case "3":
        record("enter", words.length);
        continue;
      case "4":
        var separator = "/";
        continue;
    }
    break;
  }
  return record("assembled", parts.join(separator) + "#" + total);
}

// (b) dispatcher whose sequence ends on a return rather than a continue, and
// whose cursor is initialised through the arithmetic the obfuscator wraps
// constants in. Both are shapes the pass must still accept.
function summarize(values) {
  var STORE = {
    order: "2|0|1",
    label: "sum"
  };
  var steps = STORE.order.split("|");
  var cursor = -0x10 + 0x8 + 0x8;
  while (true) {
    switch (steps[cursor++]) {
      case "0":
        var acc = 0;
        var k = 0;
        while (k < values.length) {
          acc = acc + values[k];
          k = k + 1;
        }
        continue;
      case "1":
        return record(STORE.label, acc + "/" + seen);
      case "2":
        var seen = values.length;
        continue;
    }
    break;
  }
}

// (a) comparison helper reached through the storage object, both operands the
// same property: the test is decided, so the else branch is unreachable.
function classify(n) {
  var STORE = {
    token: "QkPnV",
    same: function (a, b) {
      return a === b;
    },
    differs: function (a, b) {
      return a !== b;
    }
  };
  if (STORE.same(STORE.token, STORE.token)) {
    // live: the two operands are the same storage property
    if (STORE.differs(STORE.token, STORE.token)) {
      return record("classify", "unreachable-inner");
    } else {
      return record("classify", "live:" + n);
    }
  } else {
    return record("classify", "dead:" + n);
  }
}

// (a) inline literal comparison with no else, and one whose live side is the
// alternate. Neither needs the storage object.
function describe(flag) {
  if ("aaaaa" !== "aaaaa") {
    record("describe", "never");
  }
  if ("aaaaa" === "bbbbb") {
    return record("describe", "dead");
  } else {
    return record("describe", "live:" + flag);
  }
}

// (a) + (b) together: a decided branch wrapping a dispatcher, so the pass has
// to drop the dead side and then flatten what the live side contains.
function combined(items) {
  var STORE = {
    key: "ZZtop",
    order: "1|0",
    eq: function (a, b) {
      return a == b;
    }
  };
  if (STORE.eq(STORE.key, STORE.key)) {
    var steps = STORE.order.split("|");
    var cursor = 0;
    while (!![]) {
      switch (steps[cursor++]) {
        case "0":
          return record("combined", head + ":" + items.length);
        case "1":
          var head = items.length ? items[0] : "none";
          continue;
      }
      break;
    }
  } else {
    return record("combined", "dead");
  }
}

assemble(["alpha", "beta", "gamma"]);
summarize([3, 5, 11]);
classify(7);
describe(true);
combined(["first", "second"]);
console.log(TRACE.join("|"));
