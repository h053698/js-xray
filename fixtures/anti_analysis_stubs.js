// Anti-analysis scaffolding that survived webcrack -- the positive fixture for
// explain.py's "anti-analysis scaffolding" role.
//
// HOW THIS FILE WAS MADE
// ----------------------
// Generated with the repo's own javascript-obfuscator (4.1.1, a devDependency)
// from a small SDK-shaped source: an FNV-1a token hash, a navigator/screen
// fingerprint collector, a throwing validator, a fetch reporter, a
// localStorage persister and a window.* boot entry point. Options:
//
//     selfDefending: true, debugProtection: true,
//     debugProtectionInterval: 4000, disableConsoleOutput: true,
//     stringArray: false, identifierNamesGenerator: "hexadecimal"
//
// Then two shape perturbations were applied, both behaviour-preserving:
//
//   1. a trailing "0;" statement appended to the debug-protection function body
//   2. a "var _padN = 0;" declaration inserted into each self-defending IIFE body
//
// WHY PERTURB IT
// --------------
// webcrack removes these stubs when it recognises them, and on pristine
// obfuscator output it always does -- so pristine output makes a worthless
// fixture for this role: nothing reaches explain.py. Its matchers require an
// exact AST shape (a two-statement function body; an IIFE body that is exactly
// [VariableDeclaration, ReturnStatement]), so one extra statement is enough for
// them to miss. That is not a contrived failure: it is what any pass running
// after the obfuscator -- a bundler, a minifier, a re-obfuscation -- does, and
// it is the case a user hit, where webcrack reported nothing removed while the
// stubs were plainly still in the file.
//
// Note that webcrack.json's "self-defending, debug-protection, jsx, jsx-new"
// number is a grouped pass counter and reads the same whether or not anything
// was removed, so it cannot be used to tell those two situations apart.
//
// WHAT SHOULD BE TAGGED (4 functions)
// -----------------------------------
//   * the self-defending toString() check that matches its own body against
//     the catastrophic-backtracking pattern                    -> high
//   * the debug-protection assertion over the two source-shape regexes -> medium
//   * the disableConsoleOutput override of all 7 console methods -> medium
//   * the recursive debugger trap built from the "debugger" and
//     "while (true) {}" literals                               -> high
//
// WHAT MUST NOT BE TAGGED
// -----------------------
// The 6 real functions: the hash, the fingerprinter, the validator (which
// throws, and must keep its validation/error path role), the fetch reporter,
// the persister and the boot entry point. Nor the enclosing IIFEs -- see
// rollup_child_roles: this role is never inherited upwards, because these stubs
// sit as siblings of the real logic and the nearest enclosing function is
// usually the bundle wrapper spanning the whole file.

var _0x4a2e0b = function () {
    var _0x5d7f8f = !![];
    var _pad0 = 0;
    return function (_0x1cbc31, _0x4952db) {
      var _0x55f435 = _0x5d7f8f ? function () {
        if (_0x4952db) {
          var _0xcedd46 = _0x4952db['apply'](_0x1cbc31, arguments);
          return _0x4952db = null, _0xcedd46;
        }
      } : function () {};
      return _0x5d7f8f = ![], _0x55f435;
    };
  }(),
  _0x368d04 = _0x4a2e0b(this, function () {
    return _0x368d04['toString']()['search']('(((.+)+)+)+$')['toString']()['constructor'](_0x368d04)['search']('(((.+)+)+)+$');
  });
_0x368d04();
var _0x4dd2fc = function () {
  var _0x13a86c = !![];
  var _pad1 = 0;
  return function (_0xda1e0c, _0x22314b) {
    var _0x981f0f = _0x13a86c ? function () {
      if (_0x22314b) {
        var _0x45f1a8 = _0x22314b['apply'](_0xda1e0c, arguments);
        return _0x22314b = null, _0x45f1a8;
      }
    } : function () {};
    return _0x13a86c = ![], _0x981f0f;
  };
}();
(function () {
  _0x4dd2fc(this, function () {
    var _0x49f831 = new RegExp('function\x20*\x5c(\x20*\x5c)'),
      _0x303b7a = new RegExp('\x5c+\x5c+\x20*(?:[a-zA-Z_$][0-9a-zA-Z_$]*)', 'i'),
      _0x503ac1 = _0x4677c2('init');
    !_0x49f831['test'](_0x503ac1 + 'chain') || !_0x303b7a['test'](_0x503ac1 + 'input') ? _0x503ac1('0') : _0x4677c2();
  })();
})();
var _0x30b530 = function () {
    var _0x2ab716 = !![];
    var _pad2 = 0;
    return function (_0x238b74, _0x3751e5) {
      var _0x2d4d95 = _0x2ab716 ? function () {
        if (_0x3751e5) {
          var _0x2452b3 = _0x3751e5['apply'](_0x238b74, arguments);
          return _0x3751e5 = null, _0x2452b3;
        }
      } : function () {};
      return _0x2ab716 = ![], _0x2d4d95;
    };
  }(),
  _0x2e7c91 = _0x30b530(this, function () {
    var _0x3e54bd = function () {
        var _0x2c40c1;
        try {
          _0x2c40c1 = Function('return\x20(function()\x20' + '{}.constructor(\x22return\x20this\x22)(\x20)' + ');')();
        } catch (_0x33a66f) {
          _0x2c40c1 = window;
        }
        return _0x2c40c1;
      },
      _0x1ed40b = _0x3e54bd(),
      _0x516f30 = _0x1ed40b['console'] = _0x1ed40b['console'] || {},
      _0xe72652 = ['log', 'warn', 'info', 'error', 'exception', 'table', 'trace'];
    for (var _0x2ae7b1 = 0x0; _0x2ae7b1 < _0xe72652['length']; _0x2ae7b1++) {
      var _0x56ee4f = _0x30b530['constructor']['prototype']['bind'](_0x30b530),
        _0x48db7e = _0xe72652[_0x2ae7b1],
        _0x45b104 = _0x516f30[_0x48db7e] || _0x56ee4f;
      _0x56ee4f['__proto__'] = _0x30b530['bind'](_0x30b530), _0x56ee4f['toString'] = _0x45b104['toString']['bind'](_0x45b104), _0x516f30[_0x48db7e] = _0x56ee4f;
    }
  });
_0x2e7c91();
function computeToken(_0x7c379, _0x446be4) {
  var _0x26c64e = 0x811c9dc5,
    _0x26bb82 = String(_0x7c379) + ':' + String(_0x446be4);
  for (var _0x292e5f = 0x0; _0x292e5f < _0x26bb82['length']; _0x292e5f++) {
    _0x26c64e ^= _0x26bb82['charCodeAt'](_0x292e5f), _0x26c64e = _0x26c64e * 0x1000193 >>> 0x0;
  }
  return _0x26c64e['toString'](0x10);
}
function collectProfile() {
  return {
    'ua': navigator['userAgent'],
    'lang': navigator['language'],
    'w': screen['width'],
    'h': screen['height'],
    'tz': new Date()['getTimezoneOffset']()
  };
}
function validateProfile(_0x2d4c8b) {
  if (!_0x2d4c8b || typeof _0x2d4c8b !== 'object') throw new Error('profile\x20must\x20be\x20an\x20object');
  if (!_0x2d4c8b['ua']) throw new TypeError('missing\x20user\x20agent');
  return !![];
}
async function report(_0x525b7f, _0x3f0fe3) {
  validateProfile(_0x3f0fe3);
  var _0x51e5f8 = JSON['stringify'](_0x3f0fe3),
    _0x21ab4a = computeToken(_0x51e5f8, 'v1'),
    _0x53ad28 = await fetch(_0x525b7f + '/collect', {
      'method': 'POST',
      'headers': {
        'content-type': 'application/json',
        'x-token': _0x21ab4a
      },
      'body': _0x51e5f8
    });
  return _0x53ad28['json']();
}
function persist(_0x17edbb, _0x83273e) {
  try {
    localStorage['setItem'](_0x17edbb, JSON['stringify'](_0x83273e));
  } catch (_0x330468) {
    console['warn']('persist\x20failed', _0x330468);
  }
}
window['sdkBoot'] = function (_0x7036a6) {
  var _0x2fc50f = collectProfile();
  return persist('sdk.profile', _0x2fc50f), report(_0x7036a6, _0x2fc50f);
}, function () {
  var _0x44b979;
  try {
    var _0x599b9b = Function('return\x20(function()\x20' + '{}.constructor(\x22return\x20this\x22)(\x20)' + ');');
    _0x44b979 = _0x599b9b();
  } catch (_0x603a7f) {
    _0x44b979 = window;
  }
  _0x44b979['setInterval'](_0x4677c2, 0xfa0);
}();
function _0x4677c2(_0x2af3a3) {
  function _0x76251b(_0x33a8fc) {
    if (typeof _0x33a8fc === 'string') return function (_0x5d3c39) {}['constructor']('while\x20(true)\x20{}')['apply']('counter');else ('' + _0x33a8fc / _0x33a8fc)['length'] !== 0x1 || _0x33a8fc % 0x14 === 0x0 ? function () {
      return !![];
    }['constructor']('debu' + 'gger')['call']('action') : function () {
      return ![];
    }['constructor']('debu' + 'gger')['apply']('stateObject');
    _0x76251b(++_0x33a8fc);
  }
  try {
    if (_0x2af3a3) return _0x76251b;else _0x76251b(0x0);
  } catch (_0x377f3c) {}
  0;
}