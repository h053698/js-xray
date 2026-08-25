import { decode } from "@toon-format/toon";
let input = "";
process.stdin.setEncoding("utf-8");
process.stdin.on("data", (chunk) => { input += chunk; });
process.stdin.on("end", () => {
  try {
    const value = decode(input, { strict: true });
    process.stdout.write(JSON.stringify(value));
  } catch (err) {
    process.stderr.write(String(err && err.stack || err));
    process.exit(1);
  }
});
