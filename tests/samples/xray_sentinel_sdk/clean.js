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
          const t = e.apply(n, arguments);
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
    return a.toString().search("(((.+)+)+)+$").toString().constructor(a).search("(((.+)+)+)+$");
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
          const t = e.apply(n, arguments);
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
    return g.toString().search("(((.+)+)+)+$").toString().constructor(g).search("(((.+)+)+)+$");
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
    randomUUID: typeof crypto !== "undefined" && crypto.randomUUID && crypto.randomUUID.bind(crypto)
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
          const t = e.apply(n, arguments);
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
    return S.toString().search("(((.+)+)+)+$").toString().constructor(S).search("(((.+)+)+)+$");
  });
  function k() {
    const t = ["toString", "(((.+)+)+)+$", "apply", "random", "UUID byte range ", "rng", "search", "constructor", "length", "randomUUID", "Random bytes length must be >= 16"];
    return (k = function () {
      return t;
    })();
  }
  function A(t, n, e) {
    const r = v;
    if (y.randomUUID && !n && !t) {
      return y.randomUUID();
    }
    const o = (t = t || {}).random ?? t.rng?.() ?? function () {
      const t = f;
      if (!l) {
        if (typeof crypto === "undefined" || !crypto.getRandomValues) {
          throw new Error("crypto.getRandomValues() not supported. See https://github.com/uuidjs/uuid#getrandomvalues-not-supported");
        }
        l = crypto.getRandomValues.bind(crypto);
      }
      return l(d);
    }();
    if (o.length < 16) {
      throw new Error("Random bytes length must be >= 16");
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
    answers = new Map();
    maxAttempts = 500000;
    requirementsSeed = function () {
      const t = C;
      const n = function () {
        let t = true;
        return function (n, e) {
          const r = t ? function () {
            if (e) {
              const t = e.apply(n, arguments);
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
        return e.toString().search("(((.+)+)+)+$").toString().constructor(e).search("(((.+)+)+)+$");
      });
      e();
      return "" + Math.random();
    }();
    sid = A();
    errorPrefix = "wQ8Lk5FbGpA2NcR9dShT6gYjU7VxZ4D";
    async initializeAndGatherData(t) {
      this._getAnswer(t);
    }
    async startEnforcement(t) {
      this._getAnswer(t);
    }
    getEnforcementTokenSync(t) {
      const n = C;
      const e = this._getAnswer(t);
      if (typeof e === "string") {
        return e;
      } else {
        return null;
      }
    }
    async getEnforcementToken(t, n) {
      const e = C;
      return this._getAnswer(t, n?.forceSync);
    }
    async getRequirementsToken() {
      const t = C;
      if (!this.answers.has(this.requirementsSeed)) {
        this.answers.set(this.requirementsSeed, this._generateAnswerAsync(this.requirementsSeed, "0"));
      }
      return "gAAAAAC" + (await this.answers.get(this.requirementsSeed));
    }
    getRequirementsTokenBlocking() {
      return "gAAAAAC" + this._generateRequirementsTokenAnswerBlocking();
    }
    _getAnswer(t, n = false) {
      const e = C;
      const r = "gAAAAAB";
      if (!t?.proofofwork?.required) {
        return null;
      }
      const {
        seed: o,
        difficulty: i
      } = t.proofofwork;
      if (typeof o != "string" || typeof i !== "string") {
        return null;
      }
      const c = this.answers.get(o);
      if (typeof c === "string") {
        return c;
      }
      if (n) {
        const t = this._generateAnswerSync(o, i);
        const n = r + t;
        this.answers.set(o, n);
        return n;
      }
      if (!this.answers.has(o)) {
        this.answers.set(o, this._generateAnswerAsync(o, i));
      }
      return Promise.resolve().then(async () => {
        const t = e;
        return r + (await this.answers.get(o));
      }).then(t => {
        const n = e;
        this.answers.set(o, t);
        return t;
      });
    }
    _runCheck = (t, n, e, r, o) => {
      const i = C;
      r[3] = o;
      r[9] = Math.round(performance.now() - t);
      const c = E(r);
      const s = function (t) {
        const n = O;
        let e = 2166136261;
        for (let r = 0; r < t.length; r++) {
          e ^= t.charCodeAt(r);
          e = Math.imul(e, 16777619) >>> 0;
        }
        e ^= e >>> 16;
        e = Math.imul(e, 2246822507) >>> 0;
        e ^= e >>> 13;
        e = Math.imul(e, 3266489909) >>> 0;
        e ^= e >>> 16;
        return (e >>> 0).toString(16).padStart(8, "0");
      }(n + c);
      if (s.substring(0, e.length) <= e) {
        return c + "~S";
      } else {
        return null;
      }
    };
    buildGenerateFailMessage(t) {
      return this.errorPrefix + E(String(t ?? "e"));
    }
    _generateAnswerSync(t, n) {
      const e = C;
      const r = performance.now();
      try {
        const o = this.getConfig();
        for (let i = 0; i < this.maxAttempts; i++) {
          const c = this._runCheck(r, t, n, o, i);
          if (c) {
            return c;
          }
        }
      } catch (t) {
        return this.buildGenerateFailMessage(t);
      }
      return this.buildGenerateFailMessage();
    }
    async _generateAnswerAsync(t, n) {
      const e = C;
      const r = performance.now();
      try {
        let o = null;
        const i = this.getConfig();
        for (let c = 0; c < this.maxAttempts; c++) {
          if (!o || o.timeRemaining() <= 0) {
            o = await new Promise(t => {
              const n = O;
              const e = window.requestIdleCallback || R;
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
      return this.buildGenerateFailMessage();
    }
    _generateRequirementsTokenAnswerBlocking() {
      const t = C;
      let n = "e";
      const e = performance.now();
      try {
        const n = this.getConfig();
        n[3] = 1;
        n[9] = performance.now() - e;
        return E(n);
      } catch (t) {
        n = E(String(t));
      }
      return this.errorPrefix + n;
    }
    getConfig() {
      const t = C;
      return [screen?.width + screen?.height, "" + new Date(), performance?.memory?.jsHeapSizeLimit, Math?.random(), navigator.userAgent, j(Array.from(document.scripts).map(n => n?.src).filter(t => t)), (Array.from(document.scripts || []).map(n => n?.src?.match("c/[^/]*/_")).filter(n => n?.length)[0] ?? [])[0] ?? document.documentElement.getAttribute("data-build"), navigator.language, navigator.languages?.join(","), Math?.random(), T(), j(Object.keys(document)), j(Object.keys(window)), performance.now(), this.sid, [...new URLSearchParams(window.location.search).keys()].join(","), navigator?.hardwareConcurrency, performance.timeOrigin];
    }
  }
  function j(t) {
    const n = C;
    return t[Math.floor(Math.random() * t.length)];
  }
  function T() {
    const t = C;
    const n = j(Object.keys(Object.getPrototypeOf(navigator)));
    try {
      return n + "−" + navigator[n].toString();
    } catch {
      return "" + n;
    }
  }
  function E(t) {
    const n = C;
    t = JSON.stringify(t);
    if (window.TextEncoder) {
      return btoa(String.fromCharCode(...new TextEncoder().encode(t)));
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
          const t = e.apply(n, arguments);
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
    return I.toString().search("(((.+)+)+)+$").toString().constructor(I).search("(((.+)+)+)+$");
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
          const t = e.apply(n, arguments);
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
    return $.toString().search("(((.+)+)+)+$").toString().constructor($).search("(((.+)+)+)+$");
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
  let St = Promise.resolve();
  function kt(t, n) {
    const e = _t();
    return (kt = function (t, n) {
      return e[t -= 0];
    })(t, n);
  }
  function At(t) {
    const n = N;
    const e = St.then(t, t);
    St = e.then(() => {}, () => {});
    return e;
  }
  async function Ct() {
    const t = N;
    while (vt.get(K).length > 0) {
      const [n, ...e] = vt.get(K).shift();
      const r = vt.get(n)(...e);
      if (r && typeof r.then === "function") {
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
      vt.set(J, t => {
        if (!o) {
          o = true;
          n(btoa("" + t));
        }
      });
      vt.set(z, t => {
        if (!o) {
          o = true;
          e(btoa("" + t));
        }
      });
      vt.set(mt, (t, n, e, r) => {
        const i = Array.isArray(r);
        const c = i ? e : [];
        const s = (i ? r : e) || [];
        vt.set(t, (...t) => {
          const e = kt;
          if (o) {
            return;
          }
          const r = [...vt.get(K)];
          if (i) {
            for (let n = 0; n < c.length; n++) {
              const e = c[n];
              const r = t[n];
              vt.set(e, r);
            }
          }
          vt.set(K, [...s]);
          return Ct().then(() => vt.get(n))["catch"](t => "" + t)["finally"](() => {
            vt.set(K, r);
          });
        });
      });
      try {
        vt.set(K, JSON.parse(Tt(atob(t), "" + vt.get(rt))));
        Ct()["catch"](t => {
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
        vt.clear();
        vt.set(L, Ot);
        vt.set(F, (n, e) => vt.set(n, Tt("" + vt.get(n), "" + vt.get(e))));
        vt.set(G, (n, e) => vt.set(n, e));
        vt.set(B, (n, e) => {
          const r = t;
          const o = vt.get(n);
          if (Array.isArray(o)) {
            o.push(vt.get(e));
          } else {
            vt.set(n, o + vt.get(e));
          }
        });
        vt.set(pt, (n, e) => {
          const r = t;
          const o = vt.get(n);
          if (Array.isArray(o)) {
            o.splice(o.indexOf(vt.get(e)), 1);
          } else {
            vt.set(n, o - vt.get(e));
          }
        });
        vt.set(gt, (n, e, r) => vt.set(n, vt.get(e) < vt.get(r)));
        vt.set(wt, (n, e, r) => {
          const o = t;
          const i = Number(vt.get(e));
          const c = Number(vt.get(r));
          vt.set(n, i * c);
        });
        vt.set(H, (n, e, r) => vt.set(n, vt.get(e)[vt.get(r)]));
        vt.set(W, (n, ...e) => vt.get(n)(...e.map(n => vt.get(n))));
        vt.set(ot, (n, e, ...r) => {
          const o = t;
          try {
            const t = vt.get(e)(...r.map(t => vt.get(t)));
            if (t && typeof t.then === "function") {
              return t.then(t => {
                vt.set(n, t);
              }).catch(t => {
                vt.set(n, "" + t);
              });
            }
            vt.set(n, t);
          } catch (t) {
            vt.set(n, "" + t);
          }
        });
        vt.set(tt, (n, e, ...r) => {
          const o = t;
          try {
            vt.get(e)(...r);
          } catch (t) {
            vt.set(n, "" + t);
          }
        });
        vt.set(Z, (n, e) => vt.set(n, vt.get(e)));
        vt.set(Q, window);
        vt.set(Y, (n, e) => vt.set(n, (Array.from(document.scripts || []).map(n => n?.src?.match(vt.get(e))).filter(t => t?.length)[0] ?? [])[0] ?? null));
        vt.set(X, n => vt.set(n, vt));
        vt.set(nt, (n, e) => vt.set(n, JSON.parse("" + vt.get(e))));
        vt.set(et, (n, e) => vt.set(n, JSON.stringify(vt.get(e))));
        vt.set(it, n => vt.set(n, atob("" + vt.get(n))));
        vt.set(ct, n => vt.set(n, btoa("" + vt.get(n))));
        vt.set(ut, (n, e, r, ...o) => vt.get(n) === vt.get(e) ? vt.get(r)(...o) : null);
        vt.set(at, (n, e, r, o, ...i) => Math.abs(vt.get(n) - vt.get(e)) > vt.get(r) ? vt.get(o)(...i) : null);
        vt.set(st, (n, e, ...r) => vt.get(n) !== undefined ? vt.get(e)(...r) : null);
        vt.set(V, (n, e, r) => vt.set(n, vt.get(e)[vt.get(r)].bind(vt.get(e))));
        vt.set(yt, (n, e) => {
          const r = t;
          try {
            const t = vt.get(e);
            return Promise.resolve(t).then(t => {
              vt.set(n, t);
            });
          } catch (t) {
            return;
          }
        });
        vt.set(ft, (n, e) => {
          const r = t;
          const o = [...vt.get(K)];
          vt.set(K, [...e]);
          return Ct()["catch"](t => {
            vt.set(n, "" + t);
          })["finally"](() => {
            vt.set(K, o);
          });
        });
        vt.set(ht, () => {});
        vt.set(dt, () => {});
        vt.set(lt, () => {});
      })();
      bt = 0;
      vt.set(rt, t);
      return null;
    });
  }
  function Tt(t, n) {
    const e = N;
    let r = "";
    for (let o = 0; o < t.length; o++) {
      r += String.fromCharCode(t.charCodeAt(o) ^ n.charCodeAt(o % n.length));
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
        var e = n.apply(t, arguments);
        n = null;
        return e;
      }
    } : function () {};
    Mt = false;
    return e;
  }
  var Dt = Nt(undefined, function () {
    var t = It;
    return Dt.toString().search("(((.+)+)+)+$").toString().constructor(Dt).search("(((.+)+)+)+$");
  });
  Dt();
  "use strict";
  Pt.parse = function (t, n) {
    var e = qt;
    if (typeof t != "string") {
      throw new TypeError("argument str must be a string");
    }
    var r = {};
    var o = n || {};
    for (var i = t.split(";"), c = o.decode || $t, s = 0; s < i.length; s++) {
      var u = i[s];
      var a = u.indexOf("=");
      if (!(a < 0)) {
        var f = u.substring(0, a).trim();
        if (r[f] == null) {
          var l = u.substring(a + 1, u.length).trim();
          if (l[0] === "\"") {
            l = l.slice(1, -1);
          }
          r[f] = Jt(l, c);
        }
      }
    }
    return r;
  };
  Pt.serialize = function (t, n, e) {
    var r = qt;
    var o = e || {};
    var i = o.encode || Lt;
    if (typeof i !== "function") {
      throw new TypeError("option encode is invalid");
    }
    if (!Ft.test(t)) {
      throw new TypeError("argument name is invalid");
    }
    var c = i(n);
    if (c && !Ft.test(c)) {
      throw new TypeError("argument val is invalid");
    }
    var s = t + "=" + c;
    if (o.maxAge != null) {
      var u = o.maxAge - 0;
      if (isNaN(u) || !isFinite(u)) {
        throw new TypeError("option maxAge is invalid");
      }
      s += "; Max-Age=" + Math.floor(u);
    }
    if (o.domain) {
      if (!Ft.test(o.domain)) {
        throw new TypeError("option domain is invalid");
      }
      s += "; Domain=" + o.domain;
    }
    if (o.path) {
      if (!Ft.test(o.path)) {
        throw new TypeError("option path is invalid");
      }
      s += "; Path=" + o.path;
    }
    if (o.expires) {
      if (typeof o.expires.toUTCString !== "function") {
        throw new TypeError("option expires is invalid");
      }
      s += "; Expires=" + o.expires.toUTCString();
    }
    if (o.httpOnly) {
      s += "; HttpOnly";
    }
    if (o.secure) {
      s += "; Secure";
    }
    if (o.sameSite) {
      switch (typeof o.sameSite === "string" ? o.sameSite.toLowerCase() : o.sameSite) {
        case true:
          s += "; SameSite=Strict";
          break;
        case "lax":
          s += "; SameSite=Lax";
          break;
        case "strict":
          s += "; SameSite=Strict";
          break;
        case "none":
          s += "; SameSite=None";
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
          var n = e.apply(t, arguments);
          e = null;
          return n;
        }
      } : function () {};
      n = false;
      return r;
    }
    var o = r(this, function () {
      var t = zt;
      return o.toString().search("(((.+)+)+)+$").toString().constructor(o).search("(((.+)+)+)+$");
    });
    o();
    var i = Et && Rt.commonjsGlobal.__assign || function () {
      var t = e;
      i = Object.assign || function (t) {
        var n;
        var e = zt;
        for (var r = 1, o = arguments.length; r < o; r++) {
          for (var i in n = arguments[r]) {
            if (Object.prototype.hasOwnProperty.call(n, i)) {
              t[i] = n[i];
            }
          }
        }
        return t;
      };
      return i.apply(this, arguments);
    };
    var c = Rt.commonjsGlobal && Rt.commonjsGlobal.__rest || function (t, n) {
      var r = e;
      var o = {};
      for (var i in t) {
        if (Object.prototype.hasOwnProperty.call(t, i) && n.indexOf(i) < 0) {
          o[i] = t[i];
        }
      }
      if (t != null && typeof Object.getOwnPropertySymbols === "function") {
        var c = 0;
        for (i = Object.getOwnPropertySymbols(t); c < i.length; c++) {
          if (n.indexOf(i[c]) < 0 && Object.prototype.propertyIsEnumerable.call(t, i[c])) {
            o[i[c]] = t[i[c]];
          }
        }
      }
      return o;
    };
    Object.defineProperty(t, "__esModule", {
      value: true
    });
    t.checkCookies = t.hasCookie = t.removeCookies = t.deleteCookie = t.setCookies = t.setCookie = t.getCookie = t.getCookies = undefined;
    var s = Pt;
    function u() {
      return typeof window !== "undefined";
    }
    function a(t) {
      var n = e;
      if (t === undefined) {
        t = "";
      }
      try {
        var r = JSON.stringify(t);
        if (/^[\{\[]/.test(r)) {
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
        n = t.req;
      }
      if (!u()) {
        if (n && n.cookies) {
          return n.cookies;
        } else if (n && n.headers && n.headers.cookie) {
          return (0, s.parse)(n.headers.cookie);
        } else {
          return {};
        }
      }
      var o = {};
      var i = document.cookie ? document.cookie.split("; ") : [];
      for (var c = 0, a = i.length; c < a; c++) {
        var f = i[c].split("=");
        var l = f.slice(1).join("=");
        o[f[0]] = l;
      }
      return o;
    };
    t.getCookie = function (n, r) {
      var o = (0, t.getCookies)(r)[n];
      if (o !== undefined) {
        return function (t) {
          var n = e;
          return t === "true" || t !== "false" && (t !== "undefined" ? t === "null" ? null : t : undefined);
        }(function (t) {
          if (t) {
            return t.replace(/(%[0-9A-Z]{2})+/g, decodeURIComponent);
          } else {
            return t;
          }
        }(o));
      }
    };
    t.setCookie = function (t, n, r) {
      var o;
      var f;
      var l;
      var d = e;
      if (r) {
        f = r.req;
        l = r.res;
        o = c(r, ["req", "res"]);
      }
      var p = (0, s.serialize)(t, a(n), i({
        path: "/"
      }, o));
      if (u()) {
        document.cookie = p;
      } else if (l && f) {
        var h = l.getHeader("Set-Cookie");
        if (!Array.isArray(h)) {
          h = h ? [String(h)] : [];
        }
        l.setHeader("Set-Cookie", h.concat(p));
        if (f && f.cookies) {
          var g = f.cookies;
          if (n === "") {
            delete g[t];
          } else {
            g[t] = a(n);
          }
        }
        if (f && f.headers && f.headers.cookie) {
          g = (0, s.parse)(f.headers.cookie);
          if (n === "") {
            delete g[t];
          } else {
            g[t] = a(n);
          }
          f.headers.cookie = Object.entries(g).reduce(function (t, n) {
            var e = d;
            return t.concat("".concat(n[0], "=").concat(n[1], ";"));
          }, "");
        }
      }
    };
    t.setCookies = function (n, r, o) {
      var i = e;
      console.warn("[WARN]: setCookies was deprecated. It will be deleted in the new version. Use setCookie instead.");
      return (0, t.setCookie)(n, r, o);
    };
    t.deleteCookie = function (n, e) {
      return (0, t.setCookie)(n, "", i(i({}, e), {
        maxAge: -1
      }));
    };
    t.removeCookies = function (n, r) {
      var o = e;
      console.warn("[WARN]: removeCookies was deprecated. It will be deleted in the new version. Use deleteCookie instead.");
      return (0, t.deleteCookie)(n, r);
    };
    t.hasCookie = function (n, r) {
      var o = e;
      return !!n && (0, t.getCookies)(r).hasOwnProperty(n);
    };
    t.checkCookies = function (n, r) {
      var o = e;
      console.warn("[WARN]: checkCookies was deprecated. It will be deleted in the new version. Use hasCookie instead.");
      return (0, t.hasCookie)(n, r);
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
  const Wt = "https://chatgpt.com/backend-api/sentinel/";
  const Zt = function () {
    const t = Ht;
    const n = function () {
      let t = true;
      return function (n, e) {
        const r = t ? function () {
          if (e) {
            const t = e.apply(n, arguments);
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
      return e.toString().search("(((.+)+)+)+$").toString().constructor(e).search("(((.+)+)+)+$");
    });
    e();
    if (typeof document !== "undefined") {
      const n = document.currentScript;
      if (n?.src) {
        try {
          const e = new URL(n.src);
          if (e.pathname.includes("/sentinel/")) {
            return e.origin + "/backend-api/sentinel/";
          }
        } catch {}
      }
    }
    return Wt;
  }();
  const Kt = new URL("frame.html", Zt);
  const Qt = (() => {
    const t = Ht;
    if (window.top === window) {
      return false;
    }
    try {
      const n = new URL(window.location.href);
      return Kt.pathname === n.pathname;
    } catch {
      return false;
    }
  })();
  const Yt = 5000;
  let Xt = null;
  let tn = null;
  let nn = 0;
  const en = t => t ? t.replace(/(%[0-9A-Z]{2})+/g, decodeURIComponent) : t;
  function rn(t, n) {
    const e = Ht;
    t.id = function () {
      const t = Ht;
      const n = xt.getCookies()["oai-did"];
      if (n === undefined) {
        return undefined;
      } else {
        return en(n);
      }
    }();
    t.flow = n;
    return JSON.stringify(t);
  }
  async function on(t, n) {
    const e = Ht;
    for (let r = 0; r < 3; r++) {
      try {
        const r = await fetch(Zt + "req", {
          method: "POST",
          body: rn({
            p: n
          }, t),
          credentials: "include"
        }).then(t => t.json());
        nn = Date.now();
        tn = r;
        return;
      } catch (o) {
        if (r >= 2) {
          return rn({
            e: o.message,
            p: n,
            a: r
          }, t);
        }
      }
    }
  }
  const cn = Kt.origin;
  let sn = null;
  let un = false;
  const an = new Map();
  let fn = 0;
  function ln() {
    const t = Ht;
    const n = document.createElement("iframe");
    n.style.display = "none";
    n.src = Kt.href;
    document.body.appendChild(n);
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
        sn?.contentWindow?.postMessage({
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
          sn.addEventListener("load", () => {
            un = true;
            c();
          });
        }
      } else {
        sn = ln();
        sn.addEventListener("load", () => {
          un = true;
          c();
        });
      }
    });
  }
  async function hn(t) {
    const n = Ht;
    if (Qt) {
      throw new Error("init() should not be called from within an iframe.");
    }
    const e = await x.getRequirementsToken();
    Xt = e;
    jt(Xt);
    return pn("init", t, {
      p: e
    });
  }
  async function gn(t) {
    const n = Ht;
    if (Qt) {
      throw new Error("token() should not be called from within an iframe.");
    }
    const e = Date.now();
    if (!tn || e - nn > 540000) {
      const e = await x.getRequirementsToken();
      Xt = e;
      jt(Xt);
      const r = await pn("token", t, {
        p: e
      });
      if (typeof r === "string") {
        return r;
      }
      tn = r.cachedChatReq;
      Xt = r.cachedProof;
    }
    try {
      const e = await x.getEnforcementToken(tn);
      const r = rn({
        p: e,
        t: tn?.turnstile?.dx ? await Ot(tn.turnstile.dx) : null,
        c: tn.token
      }, t);
      tn = null;
      setTimeout(async () => {
        const e = n;
        const r = t + "__auto";
        const o = await x.getRequirementsToken();
        Xt = o;
        jt(Xt);
        pn("init", r, {
          p: o
        });
      }, Yt);
      return r;
    } catch (e) {
      const r = rn({
        e: e.message,
        p: tn?.p
      }, t);
      tn = null;
      return r;
    }
  }
  if (Qt) {
    window.addEventListener("message", async t => {
      const n = Ht;
      if (t.source === window) {
        return;
      }
      const {
        type: e,
        flow: r,
        requestId: o,
        p: i
      } = t.data ?? {};
      if (e === "init" || e === "token") {
        try {
          let c;
          if (e === "init") {
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
          t.source?.postMessage({
            type: "response",
            requestId: o,
            result: c
          }, {
            targetOrigin: t.origin
          });
        } catch (e) {
          t.source?.postMessage({
            type: "response",
            requestId: o,
            error: e.message
          }, {
            targetOrigin: t.origin
          });
        }
      }
    });
  } else {
    (function () {
      const t = Ht;
      window.addEventListener("message", n => {
        const e = t;
        if (n.source === sn?.contentWindow) {
          const {
            type: t,
            requestId: r,
            result: o,
            error: i
          } = n.data;
          if (t === "response" && r && an.has(r)) {
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
        sn.addEventListener("load", () => {
          un = true;
        });
      }
    })();
  }
  (function () {
    const t = Ht;
    if (!window?.__sentinel_token_pending || window?.__sentinel_token_pending.length === 0) {
      window?.__sentinel_init_pending?.forEach(({
        args: n,
        resolve: e
      }) => {
        const r = t;
        hn.apply(null, n).then(e);
      });
      window.__sentinel_init_pending = [];
    }
    window?.__sentinel_token_pending?.forEach(({
      args: n,
      resolve: e
    }) => {
      const r = t;
      gn.apply(null, n).then(e);
    });
    window.__sentinel_token_pending = [];
  })();
  t.init = hn;
  t.token = gn;
  return t;
}({});