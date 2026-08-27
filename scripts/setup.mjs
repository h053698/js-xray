#!/usr/bin/env bun

import {
  access,
  chmod,
  lstat,
  mkdir,
  readlink,
  realpath,
  rm,
  symlink,
} from "node:fs/promises";
import { createHash } from "node:crypto";
import { homedir } from "node:os";
import { basename, dirname, join, resolve } from "node:path";

const NODE_VERSION = process.env.JSXRAY_NODE_VERSION || "24.19.0";
const args = new Set(process.argv.slice(2));
const dryRun = args.has("--dry-run");
const repoRoot = await realpath(join(import.meta.dir, ".."));
const home = process.env.HOME || homedir();
const binDir = process.env.JSXRAY_BIN_DIR || join(home, ".local", "bin");
const codexHome = process.env.CODEX_HOME || join(home, ".codex");
const skillLink = join(codexHome, "skills", "js-xray");
const runtimeRoot = join(repoRoot, ".runtime");
const python = process.env.JSXRAY_PYTHON || Bun.which("python3");

function say(message) {
  process.stdout.write(`js-xray setup: ${message}\n`);
}

function fail(message) {
  process.stderr.write(`js-xray setup: ERROR: ${message}\n`);
  process.exit(1);
}

async function exists(path) {
  try {
    await lstat(path);
    return true;
  } catch (error) {
    if (error?.code === "ENOENT") return false;
    throw error;
  }
}

async function run(command, options = {}) {
  const proc = Bun.spawn(command, {
    cwd: options.cwd || repoRoot,
    env: options.env || process.env,
    stdout: options.quiet ? "pipe" : "inherit",
    stderr: options.quiet ? "pipe" : "inherit",
  });
  const code = await proc.exited;
  if (code !== 0 && !options.allowFailure) {
    throw new Error(`${command.join(" ")} exited ${code}`);
  }
  const stdout = options.quiet ? await new Response(proc.stdout).text() : "";
  const stderr = options.quiet ? await new Response(proc.stderr).text() : "";
  return { code, stdout, stderr };
}

function ownedLinkTarget(kind, target) {
  const normalized = target.replaceAll("\\", "/");
  if (kind === "xq") return normalized.endsWith("/skill/scripts/xq.py");
  if (kind === "js-xray") return normalized.endsWith("/skill/scripts/xray.py");
  if (kind === "skill") return normalized.endsWith("/skill");
  return false;
}

async function installLink(kind, source, destination) {
  const absoluteSource = await realpath(source);
  if (await exists(destination)) {
    const stat = await lstat(destination);
    if (!stat.isSymbolicLink()) {
      throw new Error(`${destination} already exists and is not a symlink; refusing to replace it`);
    }
    const raw = await readlink(destination);
    const current = resolve(dirname(destination), raw);
    if (current === absoluteSource) {
      say(`${kind} already installed: ${destination}`);
      return;
    }
    if (!ownedLinkTarget(kind, current)) {
      throw new Error(`${destination} belongs to another tool (${raw}); refusing to replace it`);
    }
    if (dryRun) {
      say(`would repoint ${destination} -> ${absoluteSource}`);
      return;
    }
    await rm(destination);
    await symlink(absoluteSource, destination, kind === "skill" && process.platform === "win32" ? "junction" : "file");
    say(`repointed ${destination} -> ${absoluteSource}`);
    return;
  }

  if (dryRun) {
    say(`would link ${destination} -> ${absoluteSource}`);
    return;
  }
  await mkdir(dirname(destination), { recursive: true });
  await symlink(absoluteSource, destination, kind === "skill" && process.platform === "win32" ? "junction" : "file");
  say(`linked ${destination} -> ${absoluteSource}`);
}

async function compatibleNode() {
  if (!python) return null;
  const result = await run([python, join(repoRoot, "skill", "scripts", "node_env.py"), "--json"], {
    quiet: true,
    allowFailure: true,
  });
  try {
    const parsed = JSON.parse(result.stdout);
    return parsed.ok ? parsed : null;
  } catch {
    return null;
  }
}

async function installWithManager() {
  const fnm = Bun.which("fnm");
  if (fnm) {
    say("no compatible Node found; installing Node 24 with fnm");
    if (!dryRun) await run([fnm, "install", "24"]);
    return true;
  }
  const volta = Bun.which("volta");
  if (volta) {
    say("no compatible Node found; installing Node 24 with Volta");
    if (!dryRun) await run([volta, "install", "node@24"]);
    return true;
  }
  return false;
}

function nodeDistribution() {
  const platform = process.platform;
  const arch = process.arch;
  if (!["darwin", "linux"].includes(platform) || !["arm64", "x64"].includes(arch)) {
    throw new Error(
      `automatic portable Node installation supports macOS/Linux arm64/x64; got ${platform}/${arch}`,
    );
  }
  const folder = `node-v${NODE_VERSION}-${platform}-${arch}`;
  return {
    folder,
    filename: `${folder}.tar.gz`,
    node: join(runtimeRoot, folder, "bin", "node"),
  };
}

async function sha256(path) {
  const bytes = await Bun.file(path).arrayBuffer();
  return createHash("sha256").update(Buffer.from(bytes)).digest("hex");
}

async function installPortableNode() {
  const dist = nodeDistribution();
  if (await exists(dist.node)) {
    say(`portable Node already installed: ${dist.node}`);
    return;
  }
  if (dryRun) {
    say(`would download portable Node v${NODE_VERSION} into ${runtimeRoot}`);
    return;
  }

  await mkdir(runtimeRoot, { recursive: true });
  const base = `https://nodejs.org/dist/v${NODE_VERSION}`;
  say(`downloading portable Node v${NODE_VERSION} for ${process.platform}/${process.arch}`);
  const [sumsResponse, archiveResponse] = await Promise.all([
    fetch(`${base}/SHASUMS256.txt`),
    fetch(`${base}/${dist.filename}`),
  ]);
  if (!sumsResponse.ok) throw new Error(`failed to download SHASUMS256.txt: HTTP ${sumsResponse.status}`);
  if (!archiveResponse.ok) throw new Error(`failed to download ${dist.filename}: HTTP ${archiveResponse.status}`);

  const sums = await sumsResponse.text();
  const expected = sums
    .split("\n")
    .map((line) => line.trim().split(/\s+/))
    .find((parts) => parts[1] === dist.filename)?.[0];
  if (!expected) throw new Error(`${dist.filename} is missing from Node's SHASUMS256.txt`);

  const archive = join(runtimeRoot, dist.filename);
  await Bun.write(archive, archiveResponse);
  const actual = await sha256(archive);
  if (actual !== expected) {
    await rm(archive, { force: true });
    throw new Error(`SHA-256 mismatch for ${dist.filename}`);
  }

  const tar = Bun.which("tar");
  if (!tar) throw new Error("tar is required to extract the portable Node runtime");
  await run([tar, "-xzf", archive, "-C", runtimeRoot]);
  await rm(archive, { force: true });
  if (!(await exists(dist.node))) throw new Error("portable Node extraction completed without a node binary");
  say(`installed portable Node: ${dist.node}`);
}

async function ensureRuntime() {
  let node = await compatibleNode();
  if (node) {
    say(`compatible Node found: ${node.version} (${node.node})`);
    return;
  }

  const managerUsed = await installWithManager();
  if (dryRun && managerUsed) return;
  if (!dryRun && managerUsed) node = await compatibleNode();
  if (node) {
    say(`compatible Node ready: ${node.version} (${node.node})`);
    return;
  }

  await installPortableNode();
  if (dryRun) return;
  node = await compatibleNode();
  if (!node) throw new Error("Node installation finished, but js-xray could not resolve the runtime");
  say(`compatible Node ready: ${node.version} (${node.node})`);
}

async function ensureDependencies() {
  const webcrack = join(repoRoot, "node_modules", "webcrack", "dist", "cli.js");
  if (await exists(webcrack)) {
    say("pinned dependencies already installed");
    return;
  }
  if (dryRun) {
    say("would install pinned Bun dependencies");
    return;
  }
  say("installing pinned Bun dependencies");
  await run([process.execPath, "install", "--ignore-scripts"], { cwd: repoRoot });
  if (!(await exists(webcrack))) {
    throw new Error("bun install completed without the WebCrack CLI");
  }
}

async function main() {
  if (args.has("--help") || args.has("-h")) {
    process.stdout.write(`usage: bun run setup [--dry-run]\n\n`);
    process.stdout.write(`Environment: JSXRAY_BIN_DIR, CODEX_HOME, JSXRAY_PYTHON, JSXRAY_NODE_VERSION\n`);
    return;
  }
  if (!python) fail("python3 is required but was not found on PATH");

  const version = await run([python, "--version"], { quiet: true, allowFailure: true });
  if (version.code !== 0) fail("python3 could not be executed");
  say(version.stdout.trim() || version.stderr.trim());

  try {
    await ensureRuntime();
    await ensureDependencies();
    const xqSource = join(repoRoot, "skill", "scripts", "xq.py");
    const xraySource = join(repoRoot, "skill", "scripts", "xray.py");
    if (!dryRun) {
      await chmod(xqSource, 0o755);
      await chmod(xraySource, 0o755);
    }
    await installLink("xq", xqSource, join(binDir, "xq"));
    await installLink("js-xray", xraySource, join(binDir, "js-xray"));
    await installLink("skill", join(repoRoot, "skill"), skillLink);
  } catch (error) {
    fail(error?.message || String(error));
  }

  const pathEntries = (process.env.PATH || "").split(process.platform === "win32" ? ";" : ":");
  if (!pathEntries.includes(binDir)) {
    say(`WARNING: ${binDir} is not on PATH`);
    say(`add this to your shell profile: export PATH="${binDir}:$PATH"`);
  }
  if (dryRun) {
    say("dry run complete; nothing was written");
  } else {
    say("installation complete");
    say("restart Codex, then run: js-xray path/to/file.js");
    say("query the result with: xq path/to/file.xrayjs summary");
  }
}

await main();
