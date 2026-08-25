// Synthetic JSVMP-style sample: a bytecode interpreter, hand-written small.
//
// It carries the two signals that identify the shape -- a dispatch switch whose
// discriminant is a bitmasked register slot, and case bodies that write constant
// addresses back into that same slot -- plus a numeric constant table read by
// index. The original logic of a real sample would live entirely in B below; here
// B is short, because the point of the fixture is the interpreter's shape and not
// what it computes.
!function () {
  var U = void 0, y = parseInt, E0 = Function;
  // constant pool: opcode operands index into this
  var C = [[0, 1, 2, 3, 5, 8, 13, 21, 34, 55], ["a", "b", "c", "d", "e"]];
  // bytecode: (opcode | operand << 5) words
  var B = [33, 65, 130, 3, 196, 260, 7, 324, 388, 11, 452, 516, 15, 580, 644, 19,
           708, 772, 23, 836, 900, 27, 964, 1028, 31, 1092, 1156, 35, 1220, 1284, 4];

  function run(input) {
    // d[7] is the program counter, d[0..6] the operand registers
    var d = [0, 0, 0, 0, 0, 0, 0, 0], s = [], out = "";
    while (d[7] < B.length) {
      d[6] = B[d[7]];
      switch (d[6] & 31) {
        case 0:
          s.push(C[0][(d[6] >> 5) % 10]);
          d[7] = 1;
          break;
        case 1:
          s.push(C[1][(d[6] >> 5) % 5]);
          d[7] = 2;
          break;
        case 2:
          d[0] = s.pop();
          d[7] = 3;
          break;
        case 3:
          d[1] = s.pop();
          s.push(d[1] + d[0]);
          d[7] = 4;
          break;
        case 4:
          d[1] = s.pop();
          s.push(d[1] - d[0]);
          d[7] = 5;
          break;
        case 5:
          d[1] = s.pop();
          s.push(d[1] ^ d[0]);
          d[7] = 6;
          break;
        case 6:
          d[2] = s.pop();
          s.push(d[2] >>> 3);
          d[7] = 7;
          break;
        case 7:
          d[2] = s.pop();
          s.push(d[2] << 3);
          d[7] = 8;
          break;
        case 8:
          d[3] = s[s.length - 1];
          d[7] = d[3] ? 12 : 9;
          break;
        case 9:
          d[4] = s.pop();
          out += String(d[4]);
          d[7] = 10;
          break;
        case 10:
          d[5] = C[0][(d[6] >> 5) % 10];
          s.push(d[5]);
          d[7] = 11;
          break;
        case 11:
          s.push(String(input).length);
          d[7] = 12;
          break;
        case 12:
          d[0] = s.pop();
          d[1] = s.pop();
          s.push(d[0] > d[1] ? 1 : 0);
          d[7] = 13;
          break;
        case 13:
          d[7] = y(String(C[0][3]), 10) ? 14 : 20;
          break;
        case 14:
          s.push(C[1][(d[6] >> 5) % 5] + out);
          d[7] = 15;
          break;
        case 15:
          out = String(s.pop());
          d[7] = 16;
          break;
        case 16:
          s.push(out.length);
          d[7] = 17;
          break;
        case 17:
          d[0] = s.pop();
          s.push(d[0] % C[0][6]);
          d[7] = 18;
          break;
        case 18:
          d[7] = s.length ? 19 : 20;
          break;
        case 19:
          out += String(s.pop());
          d[7] = 20;
          break;
        case 20:
          d[7] = B.length;
          break;
        default:
          d[7] = B.length;
          break;
      }
    }
    return out === U ? "" : out;
  }

  globalThis.vmpEntry = function (x) {
    return run(x);
  };
  void E0;
}();
