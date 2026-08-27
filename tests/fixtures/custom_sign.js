// Proprietary token signer. No published constants; mixing is bespoke.
function sign(input, salt) {
  let a = 0x1f3d5b79 ^ salt.length;
  let b = 0x6a09e667;
  for (let i = 0; i < input.length; i++) {
    const c = input.charCodeAt(i);
    a = (a + c * (i + 3)) >>> 0;
    a = Math.imul(a ^ (a >>> 11), 0x2545f491) >>> 0;
    b = (b ^ a) >>> 0;
    b = (b * 0x9e3779b1 >>> 0);
    if ((i & 3) === 3) { a = (a + b) >>> 0; b = (b ^ (b >>> 7)) >>> 0; }
  }
  for (let j = 0; j < salt.length; j++) {
    a = Math.imul(a + salt.charCodeAt(j), 0x85ebca77) >>> 0;
    b = (b + (a >>> 5)) >>> 0;
  }
  let m = (a ^ b) >>> 0;
  m = Math.imul(m ^ (m >>> 15), 0x27d4eb2d) >>> 0;
  m = (m ^ (m >>> 13)) >>> 0;
  return ("00000000" + m.toString(16)).slice(-8);
}
const cases = ["", "a", "hello", "seed:1", "ko-KR|agent|9", "\ud83d\ude00",
  "\ud83d\ude00\ud83d\ude80", "caf\u00e9", "\ud55c\uae00 \ud14c\uc2a4\ud2b8",
  "x".repeat(200), "0123456789abcdef", "\ud7ff\ue000\uffff", "\udbff\udfff"];
console.log(JSON.stringify(cases.map(c => [c, sign(c, "pepper")])));
