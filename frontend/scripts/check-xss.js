#!/usr/bin/env node
/**
 * check:xss — a dependency-free lint for real XSS sinks in the frontend bundle.
 *
 * WHAT THIS IS
 * ------------
 * A high-signal guard against the handful of patterns that actually bypass
 * React's automatic JSX escaping. React escapes interpolated text, so XSS
 * requires opting out of that escaping or handing raw HTML to the DOM. Those
 * opt-outs are enumerable, which is what this script checks.
 *
 * WHAT THIS IS NOT
 * ----------------
 * It is NOT a proof that the app is free of XSS. It does not do dataflow or
 * taint analysis, and it cannot reason about whether a value reaching
 * `dangerouslySetInnerHTML` is attacker-controlled. Passing this check is a
 * floor, not a certificate. It exists to make an unsafe pattern a deliberate,
 * reviewable decision rather than an accident.
 *
 * SUPPRESSING A FINDING
 * ---------------------
 * Add `xss-allow` on the SAME LINE as the offending code. It must be the same
 * line — a suppression on the line above is ignored, so that every finding is
 * visibly justified at the exact place it occurs. A reason is encouraged:
 *
 *     <div dangerouslySetInnerHTML={{ __html: sanitized }} />  // xss-allow: sanitized via DOMPurify
 *
 * Use it only when the value is provably safe. Every suppression is visible
 * in review, which is the point.
 *
 * USAGE
 * -----
 *     npm run check:xss            # lint frontend/src
 *     npm run check:xss -- --json  # machine-readable output
 */

import { readdirSync, readFileSync, statSync } from "node:fs";
import { extname, join, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = fileURLToPath(new URL(".", import.meta.url));
const REPO_ROOT = resolve(HERE, "..");
const SCAN_ROOT = resolve(REPO_ROOT, "src");

const SKIP_DIRS = new Set(["node_modules", "dist", "build", ".git", "coverage"]);
const SCAN_EXTENSIONS = new Set([".js", ".jsx", ".mjs", ".ts", ".tsx"]);

/**
 * Each rule targets a pattern that defeats JSX auto-escaping.
 * `test` is a RegExp; `hint` explains the risk and the safe alternative.
 */
const RULES = [
  {
    id: "dangerously-set-inner-html",
    severity: "error",
    pattern: /\bdangerouslySetInnerHTML\b/,
    hint: "Bypasses React escaping. Sanitize the HTML (e.g. DOMPurify) first, or render plain text.",
  },
  {
    id: "inner-html-assignment",
    severity: "error",
    // `=` but not `==`, `===`, `=>`
    pattern: /\.innerHTML\s*=(?![=>])/,
    hint: "Raw HTML sink. Prefer textContent, or sanitize the assigned markup.",
  },
  {
    id: "outer-html-assignment",
    severity: "error",
    pattern: /\.outerHTML\s*=(?![=>])/,
    hint: "Raw HTML sink. Prefer replaceWith() with a constructed node.",
  },
  {
    id: "insert-adjacent-html",
    severity: "error",
    pattern: /\.insertAdjacentHTML\s*\(/,
    hint: "Parses raw HTML. Prefer DOM node construction.",
  },
  {
    id: "document-write",
    severity: "error",
    pattern: /\bdocument\.writeln?\s*\(/,
    hint: "document.write is a classic injection sink and blocks parsing.",
  },
  {
    id: "dynamic-eval",
    severity: "error",
    pattern: /(?:\beval\s*\(|\bnew\s+Function\s*\()/,
    hint: "Executes arbitrary code. Replace with an explicit dispatch table or JSON.parse.",
  },
  {
    id: "javascript-url-scheme",
    severity: "error",
    pattern: /\bjavascript\s*:/i,
    hint: "javascript: URLs execute on click. Use an https: URL or an onClick handler.",
  },
  {
    id: "data-url-html",
    severity: "error",
    pattern: /\bdata\s*:\s*text\/html/i,
    hint: "data:text/html executes script in some contexts. Serve the file instead.",
  },
  {
    id: "iframe-srcdoc",
    severity: "warn",
    pattern: /\bsrcdoc\s*=/,
    hint: "srcdoc injects raw markup into a frame. Confirm the value is sanitized.",
  },
  {
    id: "string-timer",
    severity: "warn",
    pattern: /\bset(?:Timeout|Interval)\s*\(\s*["'`]/,
    hint: "A string timer argument is evaluated as code. Pass a function instead.",
  },
];

const SUPPRESS_PATTERN = /\bxss-allow\b/;

// JSX expression comments, block comments, and line comments. Comments are
// masked rather than dropped so reported column numbers stay accurate.
// The `(?<!:)` guard keeps protocol-relative text such as "https://" intact.
const COMMENT_PATTERN = /\{\/\*.*?\*\/\}|\/\*.*?\*\/|(?<!:)\/\/.*$/g;

/** Replace comment bodies with spaces, preserving length and column offsets. */
function maskComments(line) {
  return line.replace(COMMENT_PATTERN, (match) => match.replace(/./g, " "));
}

function collectFiles(dir, out = []) {
  let entries;
  try {
    entries = readdirSync(dir, { withFileTypes: true });
  } catch {
    return out;
  }
  for (const entry of entries) {
    const full = join(dir, entry.name);
    if (entry.isDirectory()) {
      if (SKIP_DIRS.has(entry.name)) continue;
      collectFiles(full, out);
    } else if (entry.isFile() && SCAN_EXTENSIONS.has(extname(entry.name))) {
      out.push(full);
    }
  }
  return out;
}

function scanFile(file) {
  let source;
  try {
    source = readFileSync(file, "utf8");
  } catch {
    return [];
  }

  const lines = source.split(/\r?\n/);
  const findings = [];

  lines.forEach((line, index) => {
    if (SUPPRESS_PATTERN.test(line)) return;

    // Mask comments so prose *about* these APIs (very common in a security-
    // conscious codebase) is not reported as a violation.
    const scannable = maskComments(line);
    if (!scannable.trim()) return;

    for (const rule of RULES) {
      const match = rule.pattern.exec(scannable);
      if (!match) continue;
      findings.push({
        file: relative(REPO_ROOT, file).replace(/\\/g, "/"),
        line: index + 1,
        column: match.index + 1,
        rule: rule.id,
        severity: rule.severity,
        snippet: line.trim().slice(0, 120),
        hint: rule.hint,
      });
    }
  });

  return findings;
}

function main() {
  const asJson = process.argv.includes("--json");

  if (!statSync(SCAN_ROOT, { throwIfNoEntry: false })) {
    console.error(`check:xss — scan root not found: ${SCAN_ROOT}`);
    process.exit(2);
  }

  const files = collectFiles(SCAN_ROOT);
  const findings = files.flatMap(scanFile);

  const errors = findings.filter((f) => f.severity === "error");
  const warnings = findings.filter((f) => f.severity === "warn");

  if (asJson) {
    console.log(
      JSON.stringify(
        { scannedFiles: files.length, errors: errors.length, warnings: warnings.length, findings },
        null,
        2
      )
    );
    process.exit(errors.length ? 1 : 0);
  }

  for (const finding of findings) {
    const tag = finding.severity === "error" ? "ERROR" : "WARN ";
    console.log(`${tag}  ${finding.file}:${finding.line}:${finding.column}  [${finding.rule}]`);
    console.log(`      ${finding.snippet}`);
    console.log(`      -> ${finding.hint}`);
    console.log(`      -> suppress with: // xss-allow: <reason>`);
    console.log("");
  }

  if (errors.length === 0 && warnings.length === 0) {
    console.log(`check:xss — no issues found (${files.length} files scanned).`);
    console.log("Note: this is a floor, not a proof of XSS-freedom.");
    return;
  }

  console.log(
    `check:xss — ${errors.length} error(s), ${warnings.length} warning(s) across ${files.length} files.`
  );
  process.exitCode = errors.length ? 1 : 0;
}

main();
