// Benign lookalike: the false-positive guard for the "anti-analysis scaffolding"
// role (RSK-007). Nothing in this file is obfuscator scaffolding, but every
// individual behaviour the role keys on appears here in its legitimate form:
//
//   * installLogger wraps console.log/warn/error, which is what a logging
//     library does. It hooks three methods, not the seven-method sweep
//     (including console.exception and console.table) that disableConsoleOutput
//     emits, so it stays below CONSOLE_HOOK_MIN.
//   * timeOperation measures elapsed time with performance.now(). Timing is a
//     debugger-detection signal in the wild, which is exactly why timing alone
//     is not a required condition: profiling code like this would be relabelled
//     as boilerplate.
//   * validateRecord throws on bad input and must keep its validation/error
//     path role. This is the finding the role must not eat.
//   * describeFunction calls toString() on a function and matches it with a
//     regex -- a source self-check in form. It is not tagged because the
//     pattern is an ordinary one, not one of the obfuscator's literal
//     signatures.
//   * retryWithBackoff recurses. Self-recursion is corroborating only, never
//     sufficient.
//
// If this file ever gains an "anti-analysis scaffolding" role, the detector has
// started deleting findings rather than adding one.

function installLogger(prefix) {
  var target = typeof console !== "undefined" ? console : {};
  var wrapped = {};
  ["log", "warn", "error"].forEach(function (level) {
    var original = target[level];
    wrapped[level] = function () {
      var args = Array.prototype.slice.call(arguments);
      args.unshift(prefix);
      if (typeof original === "function") {
        original.apply(target, args);
      }
    };
    target[level] = wrapped[level];
  });
  return wrapped;
}

function timeOperation(label, fn) {
  var started = performance.now();
  var result = fn();
  var elapsed = performance.now() - started;
  if (elapsed > 16) {
    console.warn(label + " took " + elapsed.toFixed(2) + "ms");
  }
  return result;
}

function validateRecord(record) {
  if (!record || typeof record !== "object") {
    throw new TypeError("record must be an object");
  }
  if (!record.id) {
    throw new Error("record.id is required");
  }
  return record;
}

function describeFunction(fn) {
  var source = fn.toString();
  var signature = /^\s*(?:async\s+)?function\s*([A-Za-z0-9_$]*)\s*\(([^)]*)\)/;
  var match = signature.exec(source);
  if (!match) {
    return { name: null, arity: fn.length };
  }
  return { name: match[1] || null, arity: match[2].split(",").length };
}

function retryWithBackoff(task, attempt, limit) {
  if (attempt >= limit) {
    return null;
  }
  var outcome = task(attempt);
  if (outcome) {
    return outcome;
  }
  return retryWithBackoff(task, attempt + 1, limit);
}

module.exports = {
  installLogger: installLogger,
  timeOperation: timeOperation,
  validateRecord: validateRecord,
  describeFunction: describeFunction,
  retryWithBackoff: retryWithBackoff
};

