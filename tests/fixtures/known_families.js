// real implementations, to check each family still confirms
function md5Init() {
  var a = 1732584193, b = 4023233417, c = 2562383102, d = 271733878;
  for (var i = 0; i < 64; i++) { a = (a + Math.imul(b, 3614090360)) | 0; b ^= a >>> 7; }
  return [a, b, c, d].join('');
}
function crc32(s) {
  var c, crc = 0xFFFFFFFF;
  for (var i = 0; i < s.length; i++) {
    c = (crc ^ s.charCodeAt(i)) & 0xFF;
    for (var k = 0; k < 8; k++) c = c & 1 ? 3988292384 ^ (c >>> 1) : c >>> 1;
    crc = (crc >>> 8) ^ c;
  }
  return (crc ^ 0xFFFFFFFF) >>> 0;
}
function djb2(s) {
  var h = 5381;
  for (var i = 0; i < s.length; i++) h = ((h << 5) + h + s.charCodeAt(i)) >>> 0;
  return h;
}
function lcg(seed) {
  var state = seed;
  for (var i = 0; i < 4; i++) state = (Math.imul(state, 1664525) + 1013904223) >>> 0;
  return state;
}
function sha256ish(w) {
  var h0 = 1779033703, h1 = 3144134277, s = 0;
  for (var i = 0; i < 64; i++) { s = (h0 >>> 2) ^ (h1 << 3); h0 = (h0 + s) | 0; }
  return (h0 ^ h1) >>> 0;
}
function seedOnly(s) {
  var h = 1779033703;
  for (var i = 0; i < s.length; i++) h = Math.imul(h ^ s.charCodeAt(i), 2654435761) >>> 0;
  return h >>> 0;
}
export { md5Init, crc32, djb2, lcg, sha256ish, seedOnly };
