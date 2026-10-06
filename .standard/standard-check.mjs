#!/usr/bin/env bun
// @bun
// standard-check-version: 1.1.2

// scripts/standard-check.ts
import { resolve, join as join3 } from "path";
import { existsSync as existsSync3, statSync as statSync3, readFileSync as readFileSync3 } from "fs";

// scripts/lib/version.ts
var EMBEDDED_VERSION = "1.1.2";

// scripts/lib/common.ts
import { existsSync, readFileSync, readdirSync, statSync } from "fs";
import { join } from "path";
var RULES = {
  S1: "\xA73, \xA74",
  S2: "\xA73",
  S3: "\xA73, \xA712",
  S4: "\xA73, \xA712",
  S5: "\xA712",
  S6: "\xA74",
  S7: "\xA74",
  S8: "\xA74",
  S9: "\xA711, \xA712",
  B1: "\xA73, \xA78",
  B2: "\xA76",
  B3: "\xA77",
  B4: "\xA76",
  B5: "\xA73, \xA76",
  B6: "\xA78, \xA79",
  B7: "\xA76",
  H1: "\xA712"
};
var TIERS = ["minimal", "standard", "full"];

class Project {
  root;
  findings;
  constructor(root, findings = []) {
    this.root = root;
    this.findings = findings;
  }
  path(rel) {
    return join(this.root, rel);
  }
  exists(rel) {
    return existsSync(this.path(rel));
  }
  read(rel) {
    return this.exists(rel) ? readFileSync(this.path(rel), "utf8") : "";
  }
  lines(rel) {
    return countLines(this.read(rel));
  }
  add(file, line, rule, level, msg) {
    this.findings.push({ file, line, rule, level, msg });
  }
  walk(rel) {
    const abs = this.path(rel);
    if (!existsSync(abs) || !statSync(abs).isDirectory())
      return [];
    return readdirSync(abs, { withFileTypes: true }).flatMap((e) => {
      const p = join(rel, e.name);
      if (e.isDirectory())
        return e.name.startsWith(".") && e.name !== ".claude" ? [] : this.walk(p);
      return [p];
    });
  }
}
function countLines(text) {
  if (text === "")
    return 0;
  const n = text.split(`
`).length;
  return text.endsWith(`
`) ? n - 1 : n;
}
function parseHeader(text) {
  const lines = text.split(`
`);
  for (let i = 0;i < Math.min(lines.length, 12); i++) {
    const m = lines[i].match(/^<!--\s*((?:layer|standard):.*?)\s*-->/);
    if (!m)
      continue;
    const fields = {};
    for (const part of m[1].split("\xB7")) {
      const kv = part.trim().match(/^([a-z]+):\s*(.*)$/i);
      if (kv)
        fields[kv[1].toLowerCase()] = kv[2].trim();
    }
    return { fields, line: i + 1 };
  }
  return null;
}
function readDeclaration(p) {
  const docsText = p.read("docs/README.md");
  const kv = parseDeclLine(docsText);
  const f = parseHeader(p.read("AGENTS.md"))?.fields ?? {};
  const agentsTier = f.tier?.toLowerCase();
  const docsTier = kv?.tier;
  const flag = (a) => a === "yes" || a === "no" ? a : undefined;
  const lc = (a) => a?.toLowerCase();
  return {
    tier: docsTier ?? agentsTier,
    version: kv?.version ?? f.standard,
    source: kv ? "docs/README.md" : "AGENTS.md",
    ui: flag(kv?.ui ?? lc(f.ui)),
    db: flag(kv?.db ?? lc(f.db)),
    agentsTier,
    docsTier,
    docsUi: flag(kv?.ui),
    docsDb: flag(kv?.db),
    agentsUi: flag(lc(f.ui)),
    agentsDb: flag(lc(f.db)),
    docsMalformed: !kv && docsText !== ""
  };
}
function parseDeclLine(text) {
  for (const line of text.split(`
`)) {
    if (!/^\s*standard:\s*house-standard\s/i.test(line))
      continue;
    const kv = {};
    for (const part of line.split(/[\u00B7|,]/)) {
      const m = part.trim().match(/^([a-z]+):\s*(.*)$/i);
      if (m)
        kv[m[1].toLowerCase()] = m[2].trim();
    }
    const version = kv.standard?.match(/^house-standard\s+(\S+)/i)?.[1];
    if (!version || !kv.tier)
      return null;
    return { version, tier: kv.tier.toLowerCase().split(/\s/)[0], ui: kv.ui?.toLowerCase(), db: kv.db?.toLowerCase() };
  }
  return null;
}

// scripts/lib/structure.ts
import { readFileSync as readFileSync2, existsSync as existsSync2 } from "fs";
import { join as join2 } from "path";
var MINIMAL = ["README.md", "AGENTS.md", "CLAUDE.md", "STATE.md"];
var STANDARD = [
  "CHANGELOG.md",
  "docs/README.md",
  "docs/OWNER-QUEUE.md",
  "docs/roadmap.md",
  "docs/workflow.md",
  "docs/inbox.md",
  "docs/lessons.md",
  "docs/product/brief.md",
  "docs/architecture/overview.md",
  "docs/decisions/",
  "docs/slices/",
  "docs/records/",
  ".claude/"
];
var FULL = ["docs/architecture/code-map.md", "docs/runbooks/"];
var UI_FILES = { minimal: [], standard: ["DESIGN.md"], full: ["DESIGN.md", "docs/product/flows.md", "docs/design/"] };
var DB_FILES = { minimal: [], standard: ["docs/architecture/schema.md"], full: ["docs/architecture/schema.md"] };
var RETIRED = ["HANDOVER.md", "workflow-state.md", "AGENT_TEAM.md", "risky_areas.md", "GATES.md", "docs/backlog.md"];
var LAYERS = ["state", "knowledge", "records"];
var STATUSES = ["living", "frozen", "record", "archived"];
function required(tier, ui, db) {
  const set = [...MINIMAL, ...tier === "minimal" ? [] : STANDARD, ...tier === "full" ? FULL : []];
  return [...set, ...ui === "yes" ? UI_FILES[tier] : [], ...db === "yes" ? DB_FILES[tier] : []];
}
function layerFor(rel) {
  if (/^docs\/(OWNER-QUEUE|roadmap|inbox)\.md$/.test(rel))
    return "state";
  if (/^docs\/slices\/.*\/gates\.md$/.test(rel))
    return "records";
  if (rel === "STATE.md")
    return "state";
  if (rel === "CHANGELOG.md")
    return "records";
  return "knowledge";
}
function structure(p) {
  const dec = readDeclaration(p);
  const known = (t) => !!t && TIERS.includes(t);
  let tier = "minimal";
  if (!dec.tier)
    p.add(dec.source, 1, "S8", "FAIL", "no tier declared (docs/README.md declaration line, or the AGENTS.md header at Minimal)");
  else if (!known(dec.tier))
    p.add(dec.source, 1, "S6", "FAIL", `tier must be one of ${TIERS.join(", ")} (got "${dec.tier}")`);
  else
    tier = dec.tier;
  if (dec.docsTier && dec.agentsTier && dec.docsTier !== dec.agentsTier)
    p.add("docs/README.md", 1, "S7", "FAIL", `tier "${dec.docsTier}" here but "${dec.agentsTier}" in the AGENTS.md header`);
  for (const [k, a, b] of [["UI", dec.docsUi, dec.agentsUi], ["DB", dec.docsDb, dec.agentsDb]])
    if (a && b && a !== b)
      p.add("docs/README.md", 1, "S7", "FAIL", `${k} "${a}" here but "${b}" in the AGENTS.md header`);
  if (dec.docsMalformed && dec.agentsTier && dec.agentsTier !== "minimal")
    p.add("docs/README.md", 1, "S6", "FAIL", "declaration line missing or malformed (Standard: house-standard X \xB7 Tier: Y \xB7 UI: yes|no \xB7 DB: yes|no)");
  for (const f of required(tier, dec.ui, dec.db)) {
    if (!p.exists(f.replace(/\/$/, "")))
      p.add(f, 1, "S1", "FAIL", `required at ${tier} tier${/DESIGN|flows|design\/|schema/.test(f) ? " with this UI/DB declaration" : ""} but missing`);
  }
  if (tier !== "minimal") {
    for (const [k, v] of [["UI", dec.ui], ["DB", dec.db]])
      if (v !== "yes" && v !== "no")
        p.add(dec.source, 1, "S1", "WARN", `${k}: yes|no not declared`);
  }
  if (!p.exists("LICENSE"))
    p.add("LICENSE", 1, "S1", "WARN", "LICENSE missing (required if the repo is public; visibility is not machine-readable)");
  for (const r of RETIRED)
    if (p.exists(r))
      p.add(r, 1, "S2", "FAIL", "retired path (STANDARD.md \xA73 'Not in the map')");
  const ver = dec.version?.match(/^(\d+)\.(\d+)\.\d+$/);
  const vfile = process.env.STANDARD_VERSION_FILE ?? (EMBEDDED_VERSION ? "" : join2(import.meta.dir, "../../VERSION"));
  const plugin = EMBEDDED_VERSION && !process.env.STANDARD_VERSION_FILE ? EMBEDDED_VERSION.match(/^(\d+)\.(\d+)\./) : existsSync2(vfile) ? readFileSync2(vfile, "utf8").trim().match(/^(\d+)\.(\d+)\./) : null;
  if (!ver)
    p.add(dec.source, 1, "S5", "FAIL", `standard version missing or not x.y.z (got "${dec.version ?? ""}")`);
  else if (!plugin)
    p.add(dec.source, 1, "S5", "FAIL", "plugin VERSION file missing or unreadable; cannot compare");
  else if (ver[1] !== plugin[1] || Math.abs(+ver[2] - +plugin[2]) > 1)
    p.add(dec.source, 1, "S5", "FAIL", `standard ${dec.version} is more than one minor from the plugin (${plugin[1]}.${plugin[2]})`);
  if (p.exists(".standard/standard-check.mjs")) {
    const head = p.read(".standard/standard-check.mjs").split(`
`).slice(0, 5).join(`
`);
    const bv = head.match(/^\/\/ standard-check-version:\s*(\d+)\.(\d+)\.\d+\s*$/m);
    if (!bv)
      p.add(".standard/standard-check.mjs", 1, "S9", "FAIL", "vendored bundle has no `// standard-check-version: x.y.z` comment in its first lines");
    else if (!ver)
      p.add(".standard/standard-check.mjs", 1, "S9", "FAIL", "cannot compare the vendored bundle: declared standard version missing or not x.y.z");
    else if (bv[1] !== ver[1] || Math.abs(+bv[2] - +ver[2]) > 1)
      p.add(".standard/standard-check.mjs", 1, "S9", "FAIL", `vendored bundle ${bv[0].match(/\d+\.\d+\.\d+/)[0]} is more than one minor from the declared standard ${dec.version}; recopy dist/standard-check.mjs`);
  }
  const hdrFiles = ["AGENTS.md", "STATE.md", "DESIGN.md", "CLAUDE.md", "CHANGELOG.md"].filter((f) => p.exists(f));
  for (const rel of [...hdrFiles, ...p.walk("docs").filter((f) => f.endsWith(".md"))]) {
    if (/^docs\/(records|_archive)\//.test(rel) || /\/_/.test(rel))
      continue;
    const h = parseHeader(p.read(rel));
    const isRoot = !rel.includes("/");
    if (!h) {
      if (!isRoot || rel === "AGENTS.md" || rel === "STATE.md")
        p.add(rel, 1, "S3", "FAIL", "no header comment");
      continue;
    }
    const f = h.fields;
    if (rel === "STATE.md" && !/^\d{4}-\d\d-\d\d$/.test(f.verified ?? "") && !/^verified:\s*\d{4}-\d\d-\d\d/m.test(p.read(rel)))
      p.add(rel, h.line, "S3", "FAIL", "STATE.md needs a `verified: YYYY-MM-DD` line");
    if (rel === "AGENTS.md") {
      if (!f.standard || !/^\d{4}-\d\d-\d\d$/.test(f.verified ?? ""))
        p.add(rel, h.line, "S3", "FAIL", "header needs standard and verified (YYYY-MM-DD); tier is checked by S6/S8");
      continue;
    }
    const layer = f.layer?.split(/\s/)[0], status = f.status?.split(/\s/)[0];
    if (!LAYERS.includes(layer) || !STATUSES.includes(status))
      p.add(rel, h.line, "S3", "FAIL", `layer/status invalid (layer=${f.layer}, status=${f.status})`);
    else if (layer !== "records" && rel.startsWith("docs/") && !/^\d{4}-\d\d-\d\d$/.test(f.verified ?? ""))
      p.add(rel, h.line, "S3", "FAIL", "verified date missing or not YYYY-MM-DD");
    const want = layerFor(rel);
    if (want && layer && layer !== want)
      p.add(rel, h.line, "S4", "FAIL", `layer "${layer}" does not match its place (expected ${want})`);
  }
}

// scripts/lib/budgets.ts
import { statSync as statSync2 } from "fs";
var FILE_BUDGETS = [
  [/^AGENTS\.md$/, 150],
  [/^CLAUDE\.md$/, 20],
  [/^STATE\.md$/, 80],
  [/^DESIGN\.md$/, 200],
  [/^docs\/README\.md$/, 100],
  [/^docs\/OWNER-QUEUE\.md$/, 80],
  [/^docs\/roadmap\.md$/, 30],
  [/^docs\/workflow\.md$/, 120],
  [/^docs\/product\/brief\.md$/, 200],
  [/^docs\/architecture\/overview\.md$/, 300],
  [/^docs\/decisions\/\d{4}-.*\.md$/, 80],
  [/^docs\/design\/ux-writing\.md$/, 150],
  [/^docs\/slices\/[^_][^/]*\/brief\.md$/, 200],
  [/^docs\/slices\/[^_][^/]*\/spec\.md$/, 300],
  [/^docs\/slices\/[^_][^/]*\/plan\.md$/, 200],
  [/^docs\/slices\/[^_][^/]*\/tasks\.md$/, 150],
  [/^docs\/slices\/[^_][^/]*\/epic\.md$/, 150]
];
var AGENTS_SECTIONS = { "1": 5, "2": 15, "3": 8, "4": 15, "5": 10, "6": 25, "7": 10, "8": 15 };
var STATE_SECTIONS = { now: 15, next: 10, blocked: 10, "direction in force": 10, "owner items": 15, measurements: 10 };
var BRIEF_SECTIONS = {
  "who it is for": 20,
  "the job and the promise": 20,
  "how it earns its keep": 15,
  "non-goals": 20,
  constraints: 20,
  "success measures": 15,
  "bets in force": 20,
  glossary: 30
};
var OVERVIEW_SECTIONS = {
  "what it is": 10,
  "system context": 30,
  containers: 50,
  "key runtime flows": 60,
  data: 20,
  "cross-cutting": 50,
  "environments and deploy path": 30,
  "constraints and debts": 30,
  "code map": 5
};
function sections(text, key) {
  const out = [];
  const unclosed = [];
  const lines = text.split(`
`);
  let cur = null;
  let fence = null;
  let broken = false;
  lines.forEach((l, i) => {
    const f = l.match(/^ {0,3}(```|~~~)/)?.[1];
    if (fence !== null && broken && /^## /.test(l))
      fence = null;
    else if (f && (fence === null || fence === f)) {
      if (fence)
        fence = null;
      else {
        fence = f;
        broken = !lines.slice(i + 1).some((x) => new RegExp(`^ {0,3}${f}`).test(x));
        if (broken)
          unclosed.push(i + 1);
      }
    }
    if (fence === null && !f && /^#{1,2} /.test(l)) {
      const k = /^## /.test(l) ? key(l.slice(3).trim()) : null;
      cur = k ? { key: k, line: i + 1, n: 0 } : null;
      if (cur)
        out.push(cur);
    } else if (cur && l.trim())
      cur.n++;
  });
  return { out, unclosed };
}
function checkSections(p, file, rule, budgets, key) {
  const { out, unclosed } = sections(p.read(file), key);
  for (const line of unclosed)
    p.add(file, line, "B7", "WARN", "unclosed code fence; section budgets read it as closed at the next ## heading");
  for (const s of out)
    if (s.n > budgets[s.key])
      p.add(file, s.line, rule, "FAIL", `section "${s.key}" has ${s.n} lines, budget ${budgets[s.key]}`);
}
var byPrefix = (b) => (h) => Object.keys(b).find((k) => h.toLowerCase().startsWith(k)) ?? null;
function budgets(p) {
  for (const f of ["AGENTS.md", "CLAUDE.md", "STATE.md", "DESIGN.md", ...p.walk("docs").filter((x) => x.endsWith(".md"))]) {
    const hit = FILE_BUDGETS.find(([re]) => re.test(f));
    if (hit && p.lines(f) > hit[1])
      p.add(f, hit[1] + 1, "B1", "FAIL", `${p.lines(f)} lines, budget ${hit[1]}`);
  }
  if (p.exists("AGENTS.md")) {
    checkSections(p, "AGENTS.md", "B2", AGENTS_SECTIONS, (h) => h.match(/^(\d)\./)?.[1] ?? null);
    const head = p.read("AGENTS.md").split(`
`).slice(1).findIndex((l) => l.startsWith("## "));
    const hdr = p.read("AGENTS.md").split(`
`).slice(1, head < 0 ? undefined : head + 1).filter((l) => l.trim()).length;
    if (hdr > 3)
      p.add("AGENTS.md", 2, "B2", "FAIL", `header comment has ${hdr} lines, budget 3`);
  }
  checkSections(p, "STATE.md", "B3", STATE_SECTIONS, byPrefix(STATE_SECTIONS));
  checkSections(p, "docs/product/brief.md", "B6", BRIEF_SECTIONS, byPrefix(BRIEF_SECTIONS));
  checkSections(p, "docs/architecture/overview.md", "B6", OVERVIEW_SECTIONS, byPrefix(OVERVIEW_SECTIONS));
  const unscoped = p.walk(".claude/rules").filter((f) => f.endsWith(".md") && !f.endsWith("README.md")).filter((f) => !/^paths:/m.test(p.read(f).match(/^---\r?\n([\s\S]*?)\r?\n---(?:\r?\n|$)/)?.[1] ?? ""));
  const ruleLines = unscoped.reduce((n, f) => n + p.lines(f), 0);
  if (ruleLines > 50)
    p.add(".claude/rules", 1, "B4", "FAIL", `unscoped rules total ${ruleLines} lines, budget 50`);
  const slice = currentSlice(p);
  const chain = ["AGENTS.md", "CLAUDE.md", "STATE.md", "docs/README.md", ...slice ? [slice] : []].reduce((n, f) => n + p.lines(f), ruleLines);
  if (chain > 600)
    p.add("AGENTS.md", 1, "B5", "FAIL", `read-first chain is ${chain} lines, budget 600${slice ? ` (current slice ${slice.split("/")[2]})` : ""}`);
}
function currentSlice(p) {
  const dirs = p.walk("docs/slices").map((f) => f.split("/")[2]).filter((d, i, a) => !d.startsWith("_") && a.indexOf(d) === i).filter((d) => p.exists(`docs/slices/${d}/brief.md`));
  const m = (d) => statSync2(p.path(`docs/slices/${d}`)).mtimeMs;
  const num = (d) => parseInt(d.match(/^\d+/)?.[0] ?? "-1", 10);
  dirs.sort((a, b) => m(b) - m(a) || num(b) - num(a) || (a < b ? 1 : -1));
  return dirs[0] ? `docs/slices/${dirs[0]}/brief.md` : null;
}

// scripts/lib/hygiene.ts
var HOME_PATH = /(?<![\w.\-\/])\/(?:Users|home)\/[^\/\s]+\//;
var ROOT_FILES = ["AGENTS.md", "CLAUDE.md", "STATE.md", "DESIGN.md", "README.md", "CHANGELOG.md"];
function hygiene(p) {
  for (const rel of [...ROOT_FILES.filter((f) => p.exists(f)), ...p.walk("docs")]) {
    const lines = p.read(rel).split(`
`);
    for (let i = 0;i < lines.length; i++)
      if (HOME_PATH.test(lines[i])) {
        p.add(rel, i + 1, "H1", "FAIL", "absolute home path (/Users/<name>/ or /home/<name>/); use a repo-relative path");
        break;
      }
  }
}

// scripts/standard-check.ts
if (process.argv.includes("--version")) {
  console.log(EMBEDDED_VERSION ?? readFileSync3(join3(import.meta.dir, "../VERSION"), "utf8").trim());
  process.exit(0);
}
var root = resolve(process.argv[2] ?? ".");
if (!existsSync3(root) || !statSync3(root).isDirectory()) {
  console.error(`standard-check: project root not found or not a directory: ${root}
Usage: bun run scripts/standard-check.ts [project-root]`);
  process.exit(2);
}
var p = new Project(root);
structure(p);
budgets(p);
hygiene(p);
var rows = p.findings.sort((a, b) => a.file.localeCompare(b.file) || a.line - b.line);
console.log("| file | line | rule | spec | level | message |");
console.log("| --- | --- | --- | --- | --- | --- |");
for (const f of rows)
  console.log(`| ${f.file} | ${f.line} | ${f.rule} | STANDARD.md ${RULES[f.rule]} | ${f.level} | ${f.msg} |`);
var fails = rows.filter((f) => f.level === "FAIL").length;
console.log(`
${fails} FAIL, ${rows.length - fails} WARN`);
process.exit(fails ? 1 : 0);
