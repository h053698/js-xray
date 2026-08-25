// Pure call forwarders routed through a control-flow storage object, plus the
// look-alikes that must survive untouched.
//
// javascript-obfuscator turns  fetch(url, opts)  into
//
//     const S = { DmnGW: function (a, b, c) { return a(b, c); } };
//     S.DmnGW(fetch, url, opts);
//
// which is behaviourally the same call and textually a different one. The cost
// is paid downstream: explain.py classifies functions by matching call text
// against markers (fetch, JSON.stringify, crypto.subtle, atob), so every real
// call hidden behind a forwarder is a function that reports as "(unclassified)".
//
// The functions named keep* below are the negative half of the fixture. Each one
// looks like a forwarder but carries something that makes the rewrite unsound,
// and a wrong rewrite there would be *worse* than leaving the wrapper alone: the
// output is still valid JavaScript, so nothing downstream can tell, and explain
// would go on to report a call that never happened.
//
// As in fixtures/flattened.js every observable effect is appended to TRACE and
// printed at the end, so the transform can be checked by running the file before
// and after and comparing stdout. That is the check that matters here -- both
// versions parse, so only execution separates a correct rewrite from a wrong one.
var TRACE = [];

function record(label, value) {
  TRACE.push(label + "=" + value);
  return value;
}

// Stand-ins for the platform APIs explain.py looks for, so the fixture runs
// under plain node while still producing the call text the classifier matches.
function fetch(url, opts) {
  TRACE.push("fetch:" + url + ":" + (opts && opts.method));
  return "response(" + url + ")";
}

function atob(s) {
  TRACE.push("atob:" + s);
  return "decoded(" + s + ")";
}

// INLINE: the shape this pass exists for. Two forwarders of different arity in
// one storage object, hiding a fetch and a JSON.stringify.
function sendBeacon(url, payload) {
  var STORE = {
    DmnGW: function (a, b, c) {
      return a(b, c);
    },
    kQrTz: function (a, b) {
      return a(b);
    }
  };
  var body = STORE.kQrTz(JSON.stringify, payload);
  var res = STORE.DmnGW(fetch, url, {
    method: "POST",
    body: body
  });
  return record("sendBeacon", res + "/" + body.length);
}

// INLINE: a zero-argument forwarder, and one reached through a const-bound
// function expression rather than a storage object.
function readClock() {
  var STORE = {
    nUlla: function (a) {
      return a();
    }
  };
  var direct = function (a, b) {
    return a(b);
  };
  var stamp = STORE.nUlla(Date.now);
  var decoded = direct(atob, "cGF5bG9hZA==");
  return record("readClock", (typeof stamp) + "/" + decoded);
}

// INLINE: the wrapper is invoked more than once, and the storage object also
// carries unrelated properties. Neither should stop the rewrite.
function parseAll(rawA, rawB) {
  var STORE = {
    label: "parse",
    xxKwe: function (a, b) {
      return a(b);
    }
  };
  var one = STORE.xxKwe(JSON.parse, rawA);
  var two = STORE.xxKwe(JSON.parse, rawB);
  return record("parseAll", STORE.label + ":" + one.a + two.b);
}

// KEEP: the wrapper swaps its arguments. `a(c, b)` is not `a(b, c)`, and a pass
// matching only on "body is a single return of a call" would silently reverse
// the argument order here.
function keepSwapped() {
  var STORE = {
    swap: function (a, b, c) {
      return a(c, b); // KEEP_SWAPPED_ARGS
    }
  };
  var join = function (x, y) {
    return x + "|" + y;
  };
  return record("keepSwapped", STORE.swap(join, "first", "second"));
}

// KEEP: the wrapper binds a receiver. `a.call(x, b)` runs a with `this === x`;
// rewriting it to `a(b)` would lose that, and any method reading `this` would
// then see undefined.
function keepThisBinding() {
  var STORE = {
    bound: function (a, b, c) {
      return a.call(b, c); // KEEP_THIS_BINDING
    }
  };
  var owner = { tag: "owner" };
  var describe = function (suffix) {
    return this.tag + "-" + suffix;
  };
  return record("keepThisBinding", STORE.bound(describe, owner, "x"));
}

// KEEP: the wrapper does something besides forward. Rewriting it would delete
// the recorded side effect, which is observable in TRACE.
function keepSideEffect() {
  var STORE = {
    logged: function (a, b) {
      TRACE.push("wrapper-ran"); // KEEP_SIDE_EFFECT
      return a(b);
    }
  };
  return record("keepSideEffect", STORE.logged(atob, "eA=="));
}

// KEEP: the property holding the wrapper is reassigned, so what the call reaches
// at runtime is not what the object literal says. This is the case the existing
// closed-object judgement already refuses.
function keepReassigned() {
  var STORE = {
    pick: function (a, b) {
      return a(b);
    }
  };
  STORE.pick = function (a, b) {
    return a(b) + "!"; // KEEP_REASSIGNED_PROP
  };
  var wrap = function (s) {
    return "[" + s + "]";
  };
  return record("keepReassigned", STORE.pick(wrap, "v"));
}

// KEEP: parameter count and argument count disagree. The wrapper forwards
// undefined for the missing parameter; `a(b)` with one argument does not, and
// arguments.length differs either way.
function keepArityMismatch() {
  var STORE = {
    three: function (a, b, c) {
      return a(b, c); // KEEP_ARITY_MISMATCH
    }
  };
  var count = function () {
    return arguments.length + ":" + String(arguments[1]);
  };
  return record("keepArityMismatch", STORE.three(count, "only"));
}

// KEEP: the forwarded callee is a member expression. `W(obj.m, x)` calls m with
// no receiver; `obj.m(x)` calls it with obj. The two differ whenever m reads
// `this`, and nothing downstream could detect the substitution.
function keepMemberCallee() {
  var STORE = {
    via: function (a, b) {
      return a(b);
    }
  };
  var holder = {
    tag: "holder",
    method: function (s) {
      return (this && this.tag ? this.tag : "no-this") + "/" + s; // KEEP_MEMBER_CALLEE
    }
  };
  return record("keepMemberCallee", STORE.via(holder.method, "m"));
}

// KEEP: the wrapper adds a literal of its own, so the argument list it builds is
// not the one the call site supplied.
function keepExtraArgument() {
  var STORE = {
    padded: function (a, b) {
      return a(b, "injected"); // KEEP_EXTRA_ARG
    }
  };
  var pair = function (x, y) {
    return x + "+" + String(y);
  };
  return record("keepExtraArgument", STORE.padded(pair, "given"));
}

// KEEP: the storage object is handed to another function, so the property this
// pass would read could have been rewritten before the call runs. The existing
// closed-object judgement refuses it, which is why nothing is recorded here as a
// wrapper refusal -- the property never resolves in the first place.
function keepEscapingStore() {
  var STORE = {
    via: function (a, b) {
      return a(b);
    }
  };
  var tamper = function (obj) {
    obj.via = function (a, b) {
      return "tampered:" + a(b); // KEEP_ESCAPING_STORE
    };
    return obj;
  };
  tamper(STORE);
  var wrap = function (s) {
    return "<" + s + ">";
  };
  return record("keepEscapingStore", STORE.via(wrap, "e"));
}

// KEEP: `JSON` here is a local object, not the global namespace, so the
// this-free-statics exception must not fire on the name alone.
function keepShadowedNamespace() {
  var JSON = {
    stringify: function (v) {
      return "shadowed:" + v.id; // KEEP_SHADOWED_NAMESPACE
    }
  };
  var STORE = {
    conv: function (a, b) {
      return a(b);
    }
  };
  return record("keepShadowedNamespace", STORE.conv(JSON.stringify, { id: 3 }));
}

sendBeacon("https://example.test/collect", { id: 7 });
readClock();
parseAll('{"a":1}', '{"b":2}');
keepSwapped();
keepThisBinding();
keepSideEffect();
keepReassigned();
keepArityMismatch();
keepMemberCallee();
keepExtraArgument();
keepEscapingStore();
keepShadowedNamespace();
console.log(TRACE.join("|"));
