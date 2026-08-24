// Fixture: one string array per IIFE scope, with short alias names reused
// across scopes for *different* arrays. A textual pass resolves the wrong
// array here; only real scope bindings get it right.
(function () {
  function HOLDER_A() {
    const t = ["alpha", "beta", "gamma", "substring"];
    HOLDER_A = function () {
      return t;
    };
    return t;
  }
  function DEC_A(a, b) {
    const e = HOLDER_A();
    return e[a - 0];
  }
  const i = DEC_A;
  globalThis.scopeA = function (s) {
    // i(3) must resolve to "substring" from HOLDER_A
    return s[i(3)](0, 2) + i(0);
  };
})();

(function () {
  function HOLDER_B() {
    const t = ["https://example.invalid/api", "toString", "delta", "epsilon"];
    HOLDER_B = function () {
      return t;
    };
    return t;
  }
  function DEC_B(a, b) {
    const e = HOLDER_B();
    return e[a - 0];
  }
  // same alias name `i`, different array
  const i = DEC_B;
  globalThis.scopeB = function () {
    // i(0) must resolve to the URL from HOLDER_B, not "alpha"
    return fetch(i(0));
  };
})();

// Offset form: arr[idx -= 5]
(function () {
  function HOLDER_C() {
    const t = ["zero", "one", "two", "charCodeAt"];
    HOLDER_C = function () {
      return t;
    };
    return t;
  }
  function DEC_C(a, b) {
    const e = HOLDER_C();
    return e[a -= 5];
  }
  globalThis.scopeC = function (s) {
    // DEC_C(8) -> index 3 -> "charCodeAt"
    return s[DEC_C(8)](0);
  };
})();

// A class using a computed method key and an `async` computed key. Converting
// these to dot notation naively produces `async .name() {}`, a syntax error.
(function () {
  function HOLDER_D() {
    const t = ["initialize", "run", "teardown", "value"];
    HOLDER_D = function () {
      return t;
    };
    return t;
  }
  function DEC_D(a, b) {
    const e = HOLDER_D();
    return e[a - 0];
  }
  class Worker {
    [DEC_D(0)]() {
      return 1;
    }
    async [DEC_D(1)]() {
      return 2;
    }
    static [DEC_D(2)]() {
      return 3;
    }
    get [DEC_D(3)]() {
      return 4;
    }
  }
  globalThis.Worker2 = Worker;
})();

// A decoder that does real work (base64) must NOT be resolved by index.
(function () {
  function HOLDER_E() {
    const t = ["YWxwaGE=", "YmV0YQ=="];
    HOLDER_E = function () {
      return t;
    };
    return t;
  }
  function DEC_E(a) {
    const e = HOLDER_E();
    return atob(e[a - 0]);
  }
  globalThis.scopeE = function () {
    return DEC_E(0);
  };
})();
