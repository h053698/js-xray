var SentinelSDK = function (t) {
  "use strict";

  const i = [];
  for (let t = 0; t < 256; ++t) {
    i.push((t + 256).toString(16).slice(1));
  }
  function s() {
    const t = ["bind", "undefined", "apply", "search", "toString", "getRandomValues", "(((.+)+)+)+$", "constructor"];
    return (s = function () {
      return t;
    })();
  }
  const u = function () {
    let t = true;
    return function (n, e) {
      const r = t ? function () {
        if (e) {
          const t = e[f(2)](n, arguments);
          e = null;
          return t;
        }
      } : function () {};
      t = false;
      return r;
    };
  }();
  const a = u(undefined, function () {
    const t = f;
    return a[t(4)]().search("(((.+)+)+)+$")[t(4)]()[t(7)](a)[t(3)](t(6));
  });
  function f(t, n) {
    const e = s();
    return (f = function (t, n) {
      return e[t -= 0];
    })(t, n);
  }
  let l;
  a();
  const d = new Uint8Array(16);
  const p = w;
  const h = function () {
    let t = true;
    return function (n, e) {
      const r = t ? function () {
        if (e) {
          const t = e[w(4)](n, arguments);
          e = null;
          return t;
        }
      } : function () {};
      t = false;
      return r;
    };
  }();
  const g = h(undefined, function () {
    const t = w;
    return g[t(5)]()[t(3)](t(1)).toString().constructor(g)[t(3)](t(1));
  });
  function m() {
    const t = ["bind", "(((.+)+)+)+$", "undefined", "search", "apply", "toString", "randomUUID"];
    return (m = function () {
      return t;
    })();
  }
  function w(t, n) {
    const e = m();
    return (w = function (t, n) {
      return e[t -= 0];
    })(t, n);
  }
  g();
  var y = {
    randomUUID: typeof crypto !== p(2) && crypto[p(6)] && crypto.randomUUID[p(0)](crypto)
  };
  function v(t, n) {
    const e = k();
    return (v = function (t, n) {
      return e[t -= 0];
    })(t, n);
  }
  const b = function () {
    let t = true;
    return function (n, e) {
      const r = t ? function () {
        if (e) {
          const t = e[v(2)](n, arguments);
          e = null;
          return t;
        }
      } : function () {};
      t = false;
      return r;
    };
  }();
  const S = b(undefined, function () {
    const t = v;
    return S[t(0)]()[t(6)](t(1))[t(0)]()[t(7)](S)[t(6)](t(1));
  });
  function k() {
    const t = ["toString", "(((.+)+)+)+$", "apply", "random", "UUID byte range ", "rng", "search", "constructor", "length", "randomUUID", "Random bytes length must be >= 16"];
    return (k = function () {
      return t;
    })();
  }
  function A(t, n, e) {
    const r = v;
    if (y[r(9)] && !n && !t) {
      return y.randomUUID();
    }
    const o = (t = t || {})[r(3)] ?? t[r(5)]?.() ?? function () {
      const t = f;
      if (!l) {
        if (typeof crypto === t(1) || !crypto[t(5)]) {
          throw new Error("crypto.getRandomValues() not supported. See https://github.com/uuidjs/uuid#getrandomvalues-not-supported");
        }
        l = crypto.getRandomValues[t(0)](crypto);
      }
      return l(d);
    }();
    if (o[r(8)] < 16) {
      throw new Error(r(10));
    }
    o[6] = o[6] & 15 | 64;
    o[8] = o[8] & 63 | 128;
    return function (t, n = 0) {
      return (i[t[n + 0]] + i[t[n + 1]] + i[t[n + 2]] + i[t[n + 3]] + "-" + i[t[n + 4]] + i[t[n + 5]] + "-" + i[t[n + 6]] + i[t[n + 7]] + "-" + i[t[n + 8]] + i[t[n + 9]] + "-" + i[t[n + 10]] + i[t[n + 11]] + i[t[n + 12]] + i[t[n + 13]] + i[t[n + 14]] + i[t[n + 15]]).toLowerCase();
    }(o);
  }
  S();
  const C = O;
  function O(t, n) {
    const e = U();
    return (O = function (t, n) {
      return e[t -= 0];
    })(t, n);
  }
  class _ {
    [C(7)] = new Map();
    [C(18)] = 500000;
    requirementsSeed = function () {
      const t = C;
      const n = function () {
        let t = true;
        return function (n, e) {
          const r = t ? function () {
            if (e) {
              const t = e[O(45)](n, arguments);
              e = null;
              return t;
            }
          } : function () {};
          t = false;
          return r;
        };
      }();
      const e = n(this, function () {
        const t = O;
        return e.toString()[t(54)](t(35)).toString().constructor(e)[t(54)](t(35));
      });
      e();
      return "" + Math[t(12)]();
    }();
    [C(57)] = A();
    [C(53)] = "wQ8Lk5FbGpA2NcR9dShT6gYjU7VxZ4D";
    async [C(14)](t) {
      this[C(0)](t);
    }
    async [C(36)](t) {
      this[C(0)](t);
    }
    [C(32)](t) {
      const n = C;
      const e = this._getAnswer(t);
      if (typeof e === n(9)) {
        return e;
      } else {
        return null;
      }
    }
    async [C(39)](t, n) {
      const e = C;
      return this[e(0)](t, n?.[e(2)]);
    }
    async [C(8)]() {
      const t = C;
      if (!this[t(7)][t(13)](this.requirementsSeed)) {
        this[t(7)].set(this[t(22)], this._generateAnswerAsync(this[t(22)], "0"));
      }
      return t(49) + (await this[t(7)][t(41)](this[t(22)]));
    }
    getRequirementsTokenBlocking() {
      return "gAAAAAC" + this[C(37)]();
    }
    [C(0)](t, n = false) {
      const e = C;
      const r = e(43);
      if (!t?.[e(17)]?.[e(63)]) {
        return null;
      }
      const {
        seed: o,
        difficulty: i
      } = t[e(17)];
      if (typeof o != "string" || typeof i !== e(9)) {
        return null;
      }
      const c = this[e(7)].get(o);
      if (typeof c === e(9)) {
        return c;
      }
      if (n) {
        const t = this[e(58)](o, i);
        const n = r + t;
        this[e(7)][e(15)](o, n);
        return n;
      }
      if (!this.answers[e(13)](o)) {
        this[e(7)][e(15)](o, this[e(60)](o, i));
      }
      return Promise.resolve()[e(26)](async () => {
        const t = e;
        return r + (await this[t(7)][t(41)](o));
      })[e(26)](t => {
        const n = e;
        this[n(7)][n(15)](o, t);
        return t;
      });
    }
    [C(4)] = (t, n, e, r, o) => {
      const i = C;
      r[3] = o;
      r[9] = Math.round(performance[i(62)]() - t);
      const c = E(r);
      const s = function (t) {
        const n = O;
        let e = 2166136261;
        for (let r = 0; r < t[n(5)]; r++) {
          e ^= t[n(40)](r);
          e = Math.imul(e, 16777619) >>> 0;
        }
        e ^= e >>> 16;
        e = Math[n(46)](e, 2246822507) >>> 0;
        e ^= e >>> 13;
        e = Math[n(46)](e, 3266489909) >>> 0;
        e ^= e >>> 16;
        return (e >>> 0)[n(55)](16)[n(30)](8, "0");
      }(n + c);
      if (s[i(47)](0, e[i(5)]) <= e) {
        return c + "~S";
      } else {
        return null;
      }
    };
    [C(19)](t) {
      return this[C(53)] + E(String(t ?? "e"));
    }
    [C(58)](t, n) {
      const e = C;
      const r = performance[e(62)]();
      try {
        const o = this[e(34)]();
        for (let i = 0; i < this[e(18)]; i++) {
          const c = this[e(4)](r, t, n, o, i);
          if (c) {
            return c;
          }
        }
      } catch (t) {
        return this[e(19)](t);
      }
      return this[e(19)]();
    }
    async [C(60)](t, n) {
      const e = C;
      const r = performance[e(62)]();
      try {
        let o = null;
        const i = this[e(34)]();
        for (let c = 0; c < this.maxAttempts; c++) {
          if (!o || o[e(48)]() <= 0) {
            o = await new Promise(t => {
              const n = O;
              const e = window[n(3)] || R;
              e(n => {
                t(n);
              }, {
                timeout: 10
              });
            });
          }
          const s = this._runCheck(r, t, n, i, c);
          if (s) {
            return s;
          }
        }
      } catch (t) {
        return this.buildGenerateFailMessage(t);
      }
      return this[e(19)]();
    }
    _generateRequirementsTokenAnswerBlocking() {
      const t = C;
      let n = "e";
      const e = performance[t(62)]();
      try {
        const n = this[t(34)]();
        n[3] = 1;
        n[9] = performance.now() - e;
        return E(n);
      } catch (t) {
        n = E(String(t));
      }
      return this[t(53)] + n;
    }
    [C(34)]() {
      const t = C;
      return [screen?.[t(1)] + screen?.[t(44)], "" + new Date(), performance?.memory?.[t(20)], Math?.random(), navigator[t(51)], j(Array[t(25)](document[t(29)])[t(11)](n => n?.[t(24)]).filter(t => t)), (Array[t(25)](document[t(29)] || [])[t(11)](n => n?.[t(24)]?.match(t(23)))[t(33)](n => n?.[t(5)])[0] ?? [])[0] ?? document[t(28)][t(52)]("data-build"), navigator[t(10)], navigator[t(38)]?.join(","), Math?.[t(12)](), T(), j(Object.keys(document)), j(Object[t(61)](window)), performance.now(), this[t(57)], [...new URLSearchParams(window[t(27)].search)[t(61)]()][t(50)](","), navigator?.[t(42)], performance[t(21)]];
    }
  }
  function j(t) {
    const n = C;
    return t[Math[n(16)](Math[n(12)]() * t.length)];
  }
  function T() {
    const t = C;
    const n = j(Object[t(61)](Object[t(6)](navigator)));
    try {
      return n + "−" + navigator[n][t(55)]();
    } catch {
      return "" + n;
    }
  }
  function E(t) {
    const n = C;
    t = JSON[n(31)](t);
    if (window[n(59)]) {
      return btoa(String.fromCharCode(...new TextEncoder()[n(56)](t)));
    } else {
      return btoa(unescape(encodeURIComponent(t)));
    }
  }
  function U() {
    const t = ["_getAnswer", "width", "forceSync", "requestIdleCallback", "_runCheck", "length", "getPrototypeOf", "answers", "getRequirementsToken", "string", "language", "map", "random", "has", "initializeAndGatherData", "set", "floor", "proofofwork", "maxAttempts", "buildGenerateFailMessage", "jsHeapSizeLimit", "timeOrigin", "requirementsSeed", "c/[^/]*/_", "src", "from", "then", "location", "documentElement", "scripts", "padStart", "stringify", "getEnforcementTokenSync", "filter", "getConfig", "(((.+)+)+)+$", "startEnforcement", "_generateRequirementsTokenAnswerBlocking", "languages", "getEnforcementToken", "charCodeAt", "get", "hardwareConcurrency", "gAAAAAB", "height", "apply", "imul", "substring", "timeRemaining", "gAAAAAC", "join", "userAgent", "getAttribute", "errorPrefix", "search", "toString", "encode", "sid", "_generateAnswerSync", "TextEncoder", "_generateAnswerAsync", "keys", "now", "required"];
    return (U = function () {
      return t;
    })();
  }
  function R(t) {
    setTimeout(() => {
      t({
        timeRemaining: () => 1,
        didTimeout: false
      });
    }, 0);
    return 0;
  }
  var x = new _();
  const P = function () {
    let t = true;
    return function (n, e) {
      const r = t ? function () {
        if (e) {
          const t = e[q(2)](n, arguments);
          e = null;
          return t;
        }
      } : function () {};
      t = false;
      return r;
    };
  }();
  const I = P(undefined, function () {
    const t = q;
    return I[t(0)]()[t(5)](t(1))[t(0)]().constructor(I)[t(5)](t(1));
  });
  function M() {
    const t = ["toString", "(((.+)+)+)+$", "apply", "get", "set", "search"];
    return (M = function () {
      return t;
    })();
  }
  function q(t, n) {
    const e = M();
    return (q = function (t, n) {
      return e[t -= 0];
    })(t, n);
  }
  I();
  const N = kt;
  const D = function () {
    let t = true;
    return function (n, e) {
      const r = t ? function () {
        if (e) {
          const t = e[kt(7)](n, arguments);
          e = null;
          return t;
        }
      } : function () {};
      t = false;
      return r;
    };
  }();
  const $ = D(undefined, function () {
    const t = kt;
    return $[t(22)]()[t(1)](t(13))[t(22)]()[t(17)]($)[t(1)](t(13));
  });
  $();
  const L = 0;
  const F = 1;
  const G = 2;
  const J = 3;
  const z = 4;
  const B = 5;
  const H = 6;
  const V = 24;
  const W = 7;
  const Z = 8;
  const K = 9;
  const Q = 10;
  const Y = 11;
  const X = 12;
  const tt = 13;
  const nt = 14;
  const et = 15;
  const rt = 16;
  const ot = 17;
  const it = 18;
  const ct = 19;
  const st = 23;
  const ut = 20;
  const at = 21;
  const ft = 22;
  const lt = 25;
  const dt = 26;
  const pt = 27;
  const ht = 28;
  const gt = 29;
  const mt = 30;
  const wt = 33;
  const yt = 34;
  const vt = new Map();
  let bt = 0;
  let St = Promise[N(19)]();
  function kt(t, n) {
    const e = _t();
    return (kt = function (t, n) {
      return e[t -= 0];
    })(t, n);
  }
  function At(t) {
    const n = N;
    const e = St[n(28)](t, t);
    St = e[n(28)](() => {}, () => {});
    return e;
  }
  async function Ct() {
    const t = N;
    while (vt[t(23)](K)[t(5)] > 0) {
      const [n, ...e] = vt[t(23)](K)[t(25)]();
      const r = vt[t(23)](n)(...e);
      if (r && typeof r.then === t(9)) {
        await r;
      }
      bt++;
    }
  }
  function Ot(t) {
    return At(() => new Promise((n, e) => {
      const r = kt;
      let o = false;
      setTimeout(() => {
        o = true;
        n("" + bt);
      }, 500);
      vt[r(27)](J, t => {
        if (!o) {
          o = true;
          n(btoa("" + t));
        }
      });
      vt[r(27)](z, t => {
        if (!o) {
          o = true;
          e(btoa("" + t));
        }
      });
      vt[r(27)](mt, (t, n, e, r) => {
        const i = Array.isArray(r);
        const c = i ? e : [];
        const s = (i ? r : e) || [];
        vt.set(t, (...t) => {
          const e = kt;
          if (o) {
            return;
          }
          const r = [...vt[e(23)](K)];
          if (i) {
            for (let n = 0; n < c[e(5)]; n++) {
              const e = c[n];
              const r = t[n];
              vt.set(e, r);
            }
          }
          vt[e(27)](K, [...s]);
          return Ct()[e(28)](() => vt[e(23)](n))[e(26)](t => "" + t)[e(16)](() => {
            vt[e(27)](K, r);
          });
        });
      });
      try {
        vt[r(27)](K, JSON.parse(Tt(atob(t), "" + vt[r(23)](rt))));
        Ct()[r(26)](t => {
          n(btoa(bt + ": " + t));
        });
      } catch (t) {
        n(btoa(bt + ": " + t));
      }
    }));
  }
  function _t() {
    const t = ["match", "search", "filter", "push", "charCodeAt", "length", "map", "apply", "clear", "function", "from", "scripts", "fromCharCode", "(((.+)+)+)+$", "stringify", "abs", "finally", "constructor", "isArray", "resolve", "splice", "bind", "toString", "get", "indexOf", "shift", "catch", "set", "then"];
    return (_t = function () {
      return t;
    })();
  }
  function jt(t) {
    At(async () => {
      const n = kt;
      (function () {
        const t = N;
        vt[t(8)]();
        vt.set(L, Ot);
        vt[t(27)](F, (n, e) => vt[t(27)](n, Tt("" + vt[t(23)](n), "" + vt.get(e))));
        vt[t(27)](G, (n, e) => vt[t(27)](n, e));
        vt[t(27)](B, (n, e) => {
          const r = t;
          const o = vt[r(23)](n);
          if (Array.isArray(o)) {
            o[r(3)](vt[r(23)](e));
          } else {
            vt.set(n, o + vt[r(23)](e));
          }
        });
        vt[t(27)](pt, (n, e) => {
          const r = t;
          const o = vt[r(23)](n);
          if (Array[r(18)](o)) {
            o[r(20)](o[r(24)](vt[r(23)](e)), 1);
          } else {
            vt[r(27)](n, o - vt[r(23)](e));
          }
        });
        vt[t(27)](gt, (n, e, r) => vt[t(27)](n, vt[t(23)](e) < vt[t(23)](r)));
        vt[t(27)](wt, (n, e, r) => {
          const o = t;
          const i = Number(vt[o(23)](e));
          const c = Number(vt.get(r));
          vt[o(27)](n, i * c);
        });
        vt[t(27)](H, (n, e, r) => vt.set(n, vt[t(23)](e)[vt[t(23)](r)]));
        vt.set(W, (n, ...e) => vt[t(23)](n)(...e[t(6)](n => vt[t(23)](n))));
        vt.set(ot, (n, e, ...r) => {
          const o = t;
          try {
            const t = vt[o(23)](e)(...r[o(6)](t => vt[o(23)](t)));
            if (t && typeof t[o(28)] === o(9)) {
              return t[o(28)](t => {
                vt[o(27)](n, t);
              }).catch(t => {
                vt[o(27)](n, "" + t);
              });
            }
            vt[o(27)](n, t);
          } catch (t) {
            vt[o(27)](n, "" + t);
          }
        });
        vt.set(tt, (n, e, ...r) => {
          const o = t;
          try {
            vt.get(e)(...r);
          } catch (t) {
            vt[o(27)](n, "" + t);
          }
        });
        vt[t(27)](Z, (n, e) => vt.set(n, vt[t(23)](e)));
        vt[t(27)](Q, window);
        vt.set(Y, (n, e) => vt.set(n, (Array[t(10)](document[t(11)] || []).map(n => n?.src?.[t(0)](vt[t(23)](e)))[t(2)](t => t?.length)[0] ?? [])[0] ?? null));
        vt.set(X, n => vt[t(27)](n, vt));
        vt[t(27)](nt, (n, e) => vt[t(27)](n, JSON.parse("" + vt.get(e))));
        vt[t(27)](et, (n, e) => vt[t(27)](n, JSON[t(14)](vt[t(23)](e))));
        vt.set(it, n => vt[t(27)](n, atob("" + vt.get(n))));
        vt[t(27)](ct, n => vt[t(27)](n, btoa("" + vt[t(23)](n))));
        vt[t(27)](ut, (n, e, r, ...o) => vt.get(n) === vt[t(23)](e) ? vt.get(r)(...o) : null);
        vt.set(at, (n, e, r, o, ...i) => Math[t(15)](vt.get(n) - vt[t(23)](e)) > vt.get(r) ? vt[t(23)](o)(...i) : null);
        vt[t(27)](st, (n, e, ...r) => vt.get(n) !== undefined ? vt[t(23)](e)(...r) : null);
        vt[t(27)](V, (n, e, r) => vt.set(n, vt[t(23)](e)[vt.get(r)][t(21)](vt[t(23)](e))));
        vt.set(yt, (n, e) => {
          const r = t;
          try {
            const t = vt[r(23)](e);
            return Promise[r(19)](t)[r(28)](t => {
              vt[r(27)](n, t);
            });
          } catch (t) {
            return;
          }
        });
        vt[t(27)](ft, (n, e) => {
          const r = t;
          const o = [...vt.get(K)];
          vt[r(27)](K, [...e]);
          return Ct()[r(26)](t => {
            vt[r(27)](n, "" + t);
          })[r(16)](() => {
            vt[r(27)](K, o);
          });
        });
        vt.set(ht, () => {});
        vt[t(27)](dt, () => {});
        vt[t(27)](lt, () => {});
      })();
      bt = 0;
      vt[n(27)](rt, t);
      return null;
    });
  }
  function Tt(t, n) {
    const e = N;
    let r = "";
    for (let o = 0; o < t[e(5)]; o++) {
      r += String[e(12)](t[e(4)](o) ^ n[e(4)](o % n[e(5)]));
    }
    return r;
  }
  var Et = typeof globalThis != "undefined" ? globalThis : typeof window != "undefined" ? window : typeof global != "undefined" ? global : typeof self != "undefined" ? self : {};
  function Ut(t) {
    if (t && t.__esModule && Object.prototype.hasOwnProperty.call(t, "default")) {
      return t.default;
    } else {
      return t;
    }
  }
  var Rt = Object.freeze({
    __proto__: null,
    commonjsGlobal: Et,
    getAugmentedNamespace: function (t) {
      if (t.__esModule) {
        return t;
      }
      var n = t.default;
      if (typeof n == "function") {
        var e = function t() {
          if (this instanceof t) {
            var e = [null];
            e.push.apply(e, arguments);
            return new (Function.bind.apply(n, e))();
          }
          return n.apply(this, arguments);
        };
        e.prototype = n.prototype;
      } else {
        e = {};
      }
      Object.defineProperty(e, "__esModule", {
        value: true
      });
      Object.keys(t).forEach(function (n) {
        var r = Object.getOwnPropertyDescriptor(t, n);
        Object.defineProperty(e, n, r.get ? r : {
          enumerable: true,
          get: function () {
            return t[n];
          }
        });
      });
      return e;
    },
    getDefaultExportFromCjs: Ut,
    getDefaultExportFromNamespaceIfNotNamed: function (t) {
      if (t && Object.prototype.hasOwnProperty.call(t, "default") && Object.keys(t).length === 1) {
        return t.default;
      } else {
        return t;
      }
    },
    getDefaultExportFromNamespaceIfPresent: function (t) {
      if (t && Object.prototype.hasOwnProperty.call(t, "default")) {
        return t.default;
      } else {
        return t;
      }
    }
  });
  var xt = {};
  var Pt = {};
  function It(t, n) {
    var e = Gt();
    return (It = function (t, n) {
      return e[t -= 0];
    })(t, n);
  }
  var Mt;
  var qt = It;
  Mt = true;
  function Nt(t, n) {
    var e = Mt ? function () {
      if (n) {
        var e = n[It(8)](t, arguments);
        n = null;
        return e;
      }
    } : function () {};
    Mt = false;
    return e;
  }
  var Dt = Nt(undefined, function () {
    var t = It;
    return Dt.toString().search(t(28))[t(32)]().constructor(Dt).search("(((.+)+)+)+$");
  });
  Dt();
  qt(26);
  Pt.parse = function (t, n) {
    var e = qt;
    if (typeof t != "string") {
      throw new TypeError(e(17));
    }
    var r = {};
    var o = n || {};
    for (var i = t.split(";"), c = o[e(9)] || $t, s = 0; s < i[e(0)]; s++) {
      var u = i[s];
      var a = u[e(23)]("=");
      if (!(a < 0)) {
        var f = u[e(12)](0, a)[e(19)]();
        if (r[f] == null) {
          var l = u[e(12)](a + 1, u[e(0)])[e(19)]();
          if (l[0] === "\"") {
            l = l[e(1)](1, -1);
          }
          r[f] = Jt(l, c);
        }
      }
    }
    return r;
  };
  Pt[qt(27)] = function (t, n, e) {
    var r = qt;
    var o = e || {};
    var i = o[r(33)] || Lt;
    if (typeof i !== r(24)) {
      throw new TypeError(r(30));
    }
    if (!Ft.test(t)) {
      throw new TypeError(r(35));
    }
    var c = i(n);
    if (c && !Ft.test(c)) {
      throw new TypeError(r(31));
    }
    var s = t + "=" + c;
    if (o[r(7)] != null) {
      var u = o[r(7)] - 0;
      if (isNaN(u) || !isFinite(u)) {
        throw new TypeError(r(5));
      }
      s += "; Max-Age=" + Math[r(14)](u);
    }
    if (o[r(13)]) {
      if (!Ft[r(34)](o[r(13)])) {
        throw new TypeError(r(10));
      }
      s += r(25) + o[r(13)];
    }
    if (o[r(21)]) {
      if (!Ft.test(o[r(21)])) {
        throw new TypeError(r(3));
      }
      s += r(37) + o[r(21)];
    }
    if (o[r(29)]) {
      if (typeof o.expires[r(6)] !== r(24)) {
        throw new TypeError(r(20));
      }
      s += "; Expires=" + o.expires.toUTCString();
    }
    if (o[r(36)]) {
      s += r(16);
    }
    if (o[r(18)]) {
      s += "; Secure";
    }
    if (o.sameSite) {
      switch (typeof o[r(2)] === r(4) ? o[r(2)].toLowerCase() : o.sameSite) {
        case true:
          s += "; SameSite=Strict";
          break;
        case r(15):
          s += "; SameSite=Lax";
          break;
        case r(11):
          s += r(22);
          break;
        case "none":
          s += r(38);
          break;
        default:
          throw new TypeError("option sameSite is invalid");
      }
    }
    return s;
  };
  var $t = decodeURIComponent;
  var Lt = encodeURIComponent;
  var Ft = /^[\u0009\u0020-\u007e\u0080-\u00ff]+$/;
  function Gt() {
    var t = ["length", "slice", "sameSite", "option path is invalid", "string", "option maxAge is invalid", "toUTCString", "maxAge", "apply", "decode", "option domain is invalid", "strict", "substring", "domain", "floor", "lax", "; HttpOnly", "argument str must be a string", "secure", "trim", "option expires is invalid", "path", "; SameSite=Strict", "indexOf", "function", "; Domain=", "use strict", "serialize", "(((.+)+)+)+$", "expires", "option encode is invalid", "argument val is invalid", "toString", "encode", "test", "argument name is invalid", "httpOnly", "; Path=", "; SameSite=None"];
    return (Gt = function () {
      return t;
    })();
  }
  function Jt(t, n) {
    try {
      return n(t);
    } catch (n) {
      return t;
    }
  }
  function zt(t, n) {
    var e = Bt();
    return (zt = function (t, n) {
      return e[t -= 0];
    })(t, n);
  }
  function Bt() {
    var t = ["length", "__esModule", "req", "split", "hasCookie", "removeCookies", "toString", "res", "hasOwnProperty", "true", "setHeader", "(((.+)+)+)+$", "getOwnPropertySymbols", "propertyIsEnumerable", "replace", "indexOf", "concat", "undefined", "constructor", "commonjsGlobal", "test", "headers", "[WARN]: setCookies was deprecated. It will be deleted in the new version. Use setCookie instead.", "call", "__assign", "getCookie", "reduce", "search", "function", "setCookies", "cookies", "slice", "apply", "setCookie", "deleteCookie", "checkCookies", "[WARN]: removeCookies was deprecated. It will be deleted in the new version. Use deleteCookie instead.", "warn", "cookie", "stringify", "defineProperty", "prototype", "getHeader", "Set-Cookie", "false", "getCookies", "parse"];
    return (Bt = function () {
      return t;
    })();
  }
  (function (t) {
    var n;
    var e = zt;
    n = true;
    function r(t, e) {
      var r = n ? function () {
        if (e) {
          var n = e[zt(32)](t, arguments);
          e = null;
          return n;
        }
      } : function () {};
      n = false;
      return r;
    }
    var o = r(this, function () {
      var t = zt;
      return o[t(6)]()[t(27)](t(11))[t(6)]()[t(18)](o).search("(((.+)+)+)+$");
    });
    o();
    var i = Et && Rt[e(19)][e(24)] || function () {
      var t = e;
      i = Object.assign || function (t) {
        var n;
        var e = zt;
        for (var r = 1, o = arguments.length; r < o; r++) {
          for (var i in n = arguments[r]) {
            if (Object[e(41)].hasOwnProperty.call(n, i)) {
              t[i] = n[i];
            }
          }
        }
        return t;
      };
      return i[t(32)](this, arguments);
    };
    var c = Rt[e(19)] && Rt[e(19)].__rest || function (t, n) {
      var r = e;
      var o = {};
      for (var i in t) {
        if (Object[r(41)][r(8)][r(23)](t, i) && n.indexOf(i) < 0) {
          o[i] = t[i];
        }
      }
      if (t != null && typeof Object[r(12)] === r(28)) {
        var c = 0;
        for (i = Object[r(12)](t); c < i[r(0)]; c++) {
          if (n[r(15)](i[c]) < 0 && Object[r(41)][r(13)].call(t, i[c])) {
            o[i[c]] = t[i[c]];
          }
        }
      }
      return o;
    };
    Object[e(40)](t, e(1), {
      value: true
    });
    t[e(35)] = t[e(4)] = t[e(5)] = t[e(34)] = t[e(29)] = t[e(33)] = t[e(25)] = t[e(45)] = undefined;
    var s = Pt;
    function u() {
      return typeof window !== e(17);
    }
    function a(t) {
      var n = e;
      if (t === undefined) {
        t = "";
      }
      try {
        var r = JSON[n(39)](t);
        if (/^[\{\[]/[n(20)](r)) {
          return r;
        } else {
          return t;
        }
      } catch (n) {
        return t;
      }
    }
    t.getCookies = function (t) {
      var n;
      var r = e;
      if (t) {
        n = t[r(2)];
      }
      if (!u()) {
        if (n && n[r(30)]) {
          return n[r(30)];
        } else if (n && n[r(21)] && n[r(21)][r(38)]) {
          return (0, s.parse)(n[r(21)][r(38)]);
        } else {
          return {};
        }
      }
      var o = {};
      var i = document[r(38)] ? document[r(38)][r(3)]("; ") : [];
      for (var c = 0, a = i.length; c < a; c++) {
        var f = i[c].split("=");
        var l = f[r(31)](1).join("=");
        o[f[0]] = l;
      }
      return o;
    };
    t[e(25)] = function (n, r) {
      var o = (0, t[e(45)])(r)[n];
      if (o !== undefined) {
        return function (t) {
          var n = e;
          return t === n(9) || t !== n(44) && (t !== n(17) ? t === "null" ? null : t : undefined);
        }(function (t) {
          if (t) {
            return t[e(14)](/(%[0-9A-Z]{2})+/g, decodeURIComponent);
          } else {
            return t;
          }
        }(o));
      }
    };
    t[e(33)] = function (t, n, r) {
      var o;
      var f;
      var l;
      var d = e;
      if (r) {
        f = r[d(2)];
        l = r[d(7)];
        o = c(r, ["req", d(7)]);
      }
      var p = (0, s.serialize)(t, a(n), i({
        path: "/"
      }, o));
      if (u()) {
        document[d(38)] = p;
      } else if (l && f) {
        var h = l[d(42)](d(43));
        if (!Array.isArray(h)) {
          h = h ? [String(h)] : [];
        }
        l[d(10)](d(43), h.concat(p));
        if (f && f[d(30)]) {
          var g = f.cookies;
          if (n === "") {
            delete g[t];
          } else {
            g[t] = a(n);
          }
        }
        if (f && f.headers && f.headers[d(38)]) {
          g = (0, s[d(46)])(f.headers.cookie);
          if (n === "") {
            delete g[t];
          } else {
            g[t] = a(n);
          }
          f[d(21)][d(38)] = Object.entries(g)[d(26)](function (t, n) {
            var e = d;
            return t.concat(""[e(16)](n[0], "=")[e(16)](n[1], ";"));
          }, "");
        }
      }
    };
    t.setCookies = function (n, r, o) {
      var i = e;
      console.warn(i(22));
      return (0, t[i(33)])(n, r, o);
    };
    t[e(34)] = function (n, e) {
      return (0, t.setCookie)(n, "", i(i({}, e), {
        maxAge: -1
      }));
    };
    t[e(5)] = function (n, r) {
      var o = e;
      console[o(37)](o(36));
      return (0, t[o(34)])(n, r);
    };
    t.hasCookie = function (n, r) {
      var o = e;
      return !!n && (0, t.getCookies)(r)[o(8)](n);
    };
    t[e(35)] = function (n, r) {
      var o = e;
      console[o(37)]("[WARN]: checkCookies was deprecated. It will be deleted in the new version. Use hasCookie instead.");
      return (0, t[o(4)])(n, r);
    };
  })(xt);
  Ut(xt);
  const Ht = Vt;
  function Vt(t, n) {
    const e = dn();
    return (Vt = function (t, n) {
      return e[t -= 0];
    })(t, n);
  }
  const Wt = Ht(47);
  const Zt = function () {
    const t = Ht;
    const n = function () {
      let t = true;
      return function (n, e) {
        const r = t ? function () {
          if (e) {
            const t = e[Vt(14)](n, arguments);
            e = null;
            return t;
          }
        } : function () {};
        t = false;
        return r;
      };
    }();
    const e = n(this, function () {
      const t = Vt;
      return e[t(5)]()[t(48)](t(27)).toString().constructor(e).search(t(27));
    });
    e();
    if (typeof document !== t(38)) {
      const n = document[t(23)];
      if (n?.[t(8)]) {
        try {
          const e = new URL(n[t(8)]);
          if (e[t(37)][t(31)](t(24))) {
            return e.origin + t(32);
          }
        } catch {}
      }
    }
    return Wt;
  }();
  const Kt = new URL(Ht(9), Zt);
  const Qt = (() => {
    const t = Ht;
    if (window.top === window) {
      return false;
    }
    try {
      const n = new URL(window[t(11)].href);
      return Kt[t(37)] === n[t(37)];
    } catch {
      return false;
    }
  })();
  const Yt = 5000;
  let Xt = null;
  let tn = null;
  let nn = 0;
  const en = t => t ? t[Ht(44)](/(%[0-9A-Z]{2})+/g, decodeURIComponent) : t;
  function rn(t, n) {
    const e = Ht;
    t.id = function () {
      const t = Ht;
      const n = xt.getCookies()[t(6)];
      if (n === undefined) {
        return undefined;
      } else {
        return en(n);
      }
    }();
    t[e(43)] = n;
    return JSON[e(17)](t);
  }
  async function on(t, n) {
    const e = Ht;
    for (let r = 0; r < 3; r++) {
      try {
        const r = await fetch(Zt + e(22), {
          method: "POST",
          body: rn({
            p: n
          }, t),
          credentials: "include"
        })[e(26)](t => t.json());
        nn = Date.now();
        tn = r;
        return;
      } catch (o) {
        if (r >= 2) {
          return rn({
            e: o[e(36)],
            p: n,
            a: r
          }, t);
        }
      }
    }
  }
  const cn = Kt[Ht(46)];
  let sn = null;
  let un = false;
  const an = new Map();
  let fn = 0;
  function ln() {
    const t = Ht;
    const n = document[t(30)]("iframe");
    n[t(4)][t(19)] = t(39);
    n[t(8)] = Kt.href;
    document[t(21)][t(12)](n);
    return n;
  }
  function dn() {
    const t = ["cachedProof", "response", "turnstile", "source", "style", "toString", "oai-did", "__sentinel_token_pending", "src", "frame.html", "contentWindow", "location", "appendChild", "length", "apply", "__auto", "__sentinel_init_pending", "stringify", "postMessage", "display", "token", "body", "req", "currentScript", "/sentinel/", "data", "then", "(((.+)+)+)+$", "init() should not be called from within an iframe.", "load", "createElement", "includes", "/backend-api/sentinel/", "init", "forEach", "addEventListener", "message", "pathname", "undefined", "none", "getRequirementsToken", "token() should not be called from within an iframe.", "has", "flow", "replace", "string", "origin", "https://chatgpt.com/backend-api/sentinel/", "search"];
    return (dn = function () {
      return t;
    })();
  }
  function pn(t, n, e) {
    return new Promise((r, o) => {
      const i = Vt;
      function c() {
        const i = Vt;
        const c = "req_" + ++fn;
        an.set(c, {
          resolve: r,
          reject: o
        });
        sn?.[i(10)]?.[i(18)]({
          type: t,
          flow: n,
          requestId: c,
          ...e
        }, cn);
      }
      if (sn) {
        if (un) {
          c();
        } else {
          sn[i(35)](i(29), () => {
            un = true;
            c();
          });
        }
      } else {
        sn = ln();
        sn.addEventListener(i(29), () => {
          un = true;
          c();
        });
      }
    });
  }
  async function hn(t) {
    const n = Ht;
    if (Qt) {
      throw new Error(n(28));
    }
    const e = await x.getRequirementsToken();
    Xt = e;
    jt(Xt);
    return pn(n(33), t, {
      p: e
    });
  }
  async function gn(t) {
    const n = Ht;
    if (Qt) {
      throw new Error(n(41));
    }
    const e = Date.now();
    if (!tn || e - nn > 540000) {
      const e = await x[n(40)]();
      Xt = e;
      jt(Xt);
      const r = await pn(n(20), t, {
        p: e
      });
      if (typeof r === n(45)) {
        return r;
      }
      tn = r.cachedChatReq;
      Xt = r[n(0)];
    }
    try {
      const e = await x.getEnforcementToken(tn);
      const r = rn({
        p: e,
        t: tn?.[n(2)]?.dx ? await Ot(tn[n(2)].dx) : null,
        c: tn[n(20)]
      }, t);
      tn = null;
      setTimeout(async () => {
        const e = n;
        const r = t + e(15);
        const o = await x[e(40)]();
        Xt = o;
        jt(Xt);
        pn(e(33), r, {
          p: o
        });
      }, Yt);
      return r;
    } catch (e) {
      const r = rn({
        e: e[n(36)],
        p: tn?.p
      }, t);
      tn = null;
      return r;
    }
  }
  if (Qt) {
    window[Ht(35)](Ht(36), async t => {
      const n = Ht;
      if (t[n(3)] === window) {
        return;
      }
      const {
        type: e,
        flow: r,
        requestId: o,
        p: i
      } = t[n(25)] ?? {};
      if (e === n(33) || e === n(20)) {
        try {
          let c;
          if (e === n(33)) {
            c = await on(r, i);
          } else if (e === "token") {
            c = await async function (t, n) {
              const e = Date.now();
              if (!tn || e - nn > 540000) {
                const e = await Promise.race([on(t, n), new Promise(e => setTimeout(() => e(rn({
                  e: "elapsed",
                  p: n
                }, t)), 4000))]);
                if (e != null) {
                  return e;
                }
              }
              nn = 0;
              return {
                cachedChatReq: tn,
                cachedProof: Xt
              };
            }(r, i);
          }
          t[n(3)]?.postMessage({
            type: n(1),
            requestId: o,
            result: c
          }, {
            targetOrigin: t.origin
          });
        } catch (e) {
          t.source?.[n(18)]({
            type: "response",
            requestId: o,
            error: e[n(36)]
          }, {
            targetOrigin: t.origin
          });
        }
      }
    });
  } else {
    (function () {
      const t = Ht;
      window[t(35)](t(36), n => {
        const e = t;
        if (n[e(3)] === sn?.[e(10)]) {
          const {
            type: t,
            requestId: r,
            result: o,
            error: i
          } = n[e(25)];
          if (t === e(1) && r && an[e(42)](r)) {
            const {
              resolve: t,
              reject: n
            } = an.get(r);
            if (i) {
              n(i);
            } else {
              t(o);
            }
            an.delete(r);
          }
        }
      });
      if (!sn) {
        sn = ln();
        sn[t(35)]("load", () => {
          un = true;
        });
      }
    })();
  }
  (function () {
    const t = Ht;
    if (!window?.[t(7)] || window?.__sentinel_token_pending[t(13)] === 0) {
      window?.[t(16)]?.[t(34)](({
        args: n,
        resolve: e
      }) => {
        const r = t;
        hn[r(14)](null, n)[r(26)](e);
      });
      window[t(16)] = [];
    }
    window?.[t(7)]?.[t(34)](({
      args: n,
      resolve: e
    }) => {
      const r = t;
      gn[r(14)](null, n)[r(26)](e);
    });
    window.__sentinel_token_pending = [];
  })();
  t.init = hn;
  t.token = gn;
  return t;
}({});
