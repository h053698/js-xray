// Negative fixture: a hand-written state machine with a large switch inside a
// loop, the shape most likely to be mistaken for a VM dispatch loop. It is
// ordinary code -- a tokenizer -- and its state lives in a named variable that
// is assigned named constants, not in a masked array slot fed numeric addresses.
// Detection must report verdict "none" for this file.
const S_START = 0, S_WORD = 1, S_NUM = 2, S_STR = 3, S_ESC = 4, S_COMMENT = 5,
      S_SLASH = 6, S_OP = 7, S_WS = 8, S_DONE = 9, S_ERROR = 10, S_EOF = 11,
      S_DOT = 12, S_EXP = 13;

export function tokenize(src) {
  const tokens = [];
  let state = S_START;
  let buf = "";
  let i = 0;
  while (state !== S_DONE && state !== S_ERROR) {
    const ch = i < src.length ? src[i] : "";
    switch (state) {
      case S_START:
        if (!ch) state = S_EOF;
        else if (/\s/.test(ch)) state = S_WS;
        else if (/[A-Za-z_$]/.test(ch)) state = S_WORD;
        else if (/[0-9]/.test(ch)) state = S_NUM;
        else if (ch === '"') { i++; state = S_STR; }
        else if (ch === "/") state = S_SLASH;
        else state = S_OP;
        break;
      case S_WS:
        while (i < src.length && /\s/.test(src[i])) i++;
        state = S_START;
        break;
      case S_WORD:
        buf = "";
        while (i < src.length && /[A-Za-z0-9_$]/.test(src[i])) buf += src[i++];
        tokens.push({ type: "word", value: buf });
        state = S_START;
        break;
      case S_NUM:
        buf = "";
        while (i < src.length && /[0-9]/.test(src[i])) buf += src[i++];
        state = src[i] === "." ? S_DOT : (src[i] === "e" ? S_EXP : S_START);
        if (state === S_START) tokens.push({ type: "num", value: Number(buf) });
        break;
      case S_DOT:
        buf += src[i++];
        while (i < src.length && /[0-9]/.test(src[i])) buf += src[i++];
        tokens.push({ type: "num", value: Number(buf) });
        state = S_START;
        break;
      case S_EXP:
        buf += src[i++];
        if (src[i] === "+" || src[i] === "-") buf += src[i++];
        while (i < src.length && /[0-9]/.test(src[i])) buf += src[i++];
        tokens.push({ type: "num", value: Number(buf) });
        state = S_START;
        break;
      case S_STR:
        buf = "";
        while (i < src.length && src[i] !== '"') {
          if (src[i] === "\\") { state = S_ESC; break; }
          buf += src[i++];
        }
        if (state === S_STR) {
          i++;
          tokens.push({ type: "str", value: buf });
          state = S_START;
        }
        break;
      case S_ESC:
        i++;
        buf += src[i] === "n" ? "\n" : src[i];
        i++;
        state = S_STR;
        break;
      case S_SLASH:
        state = src[i + 1] === "/" ? S_COMMENT : S_OP;
        break;
      case S_COMMENT:
        while (i < src.length && src[i] !== "\n") i++;
        state = S_START;
        break;
      case S_OP:
        tokens.push({ type: "op", value: src[i++] });
        state = S_START;
        break;
      case S_EOF:
        tokens.push({ type: "eof" });
        state = S_DONE;
        break;
      default:
        state = S_ERROR;
        break;
    }
  }
  if (state === S_ERROR) throw new Error("tokenizer stuck at offset " + i);
  return tokens;
}
