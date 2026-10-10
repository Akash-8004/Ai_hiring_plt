#!/usr/bin/env node
/**
 * check:csv — a lint against unsafe, hand-rolled CSV generation in the frontend.
 *
 * Catches CSV generation patterns (e.g., raw array .join(","), hand-rolled
 * escaping, or unescaped string concatenation) that bypass formula-injection
 * escaping (DDE injection). All CSV creation must go through `toCsv` or `csvCell`
 * from `src/utils/csv.js`.
 *
 * SUPPRESSING A FINDING
 * ---------------------
 * Add `csv-allow` on the SAME LINE as the offending code:
 *     const line = values.join(","); // csv-allow: internal debug key, not a CSV export
 */

import { readdirSync, readFileSync, statSync } from "node:fs";
import { extname, join, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = fileURLToPath(new URL(".", import.meta.url));
const REPO_ROOT = resolve(HERE, "..");
const SCAN_ROOT = resolve(REPO_ROOT, "src");

const SKIP_DIRS = new Set(["node_modules", "dist", "build", ".git", "coverage"]);
const SCAN_EXTENSIONS = new Set([".js", ".jsx", ".mjs", ".ts", ".tsx"]);

// utils/csv.js is the canonical CSV serializer and is exempt from this check
const EXEMPT_FILES = new Set([
  resolve(SCAN_ROOT, "utils", "csv.js").replace(/\\/g, "/"),
]);

const RULES = [
  {
    id: "hand-rolled-csv-export",
    severity: "error",
    pattern: /(?:text\/csv|\.csv['"`])/,
    checkFile: (source) => {
      // If a file references CSV export/mime type, ensure it uses toCsv or csvCell
      const hasCsvContext = /(?:text\/csv|\.csv['"`])/.test(source);
      if (!hasCsvContext) return null;
      const usesSafeCsv = /\b(?:toCsv|csvCell)\b/.test(source);
      if (!usesSafeCsv) {
        return {
          pattern: /(?:text\/csv|\.csv['"`])/,
          hint: "File performs CSV export or generates CSV data without using toCsv/csvCell from src/utils/csv.js.",
        };
      }
      return null;
    },
  },
  {
    id: "raw-csv-row-join",
    severity: "error",
    pattern: /\.map\([^)]+\)\.join\(\s*['"](?:,|\\n|\\r\\n)['"]\s*\)/,
    hint: "Hand-rolled CSV row joining detected. Use toCsv(rows, headers) from src/utils/csv.js instead.",
  },
];

const SUPPRESS_PATTERN = /\bcsv-allow\b/;
const COMMENT_PATTERN = /\{\/\*.*?\*\/\}|\/\*.*?\*\/|(?<!:)\/\/.*$/g;

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
  const normFile = file.replace(/\\/g, "/");
  if (EXEMPT_FILES.has(normFile)) return [];

  let source;
  try {
    source = readFileSync(file, "utf8");
  } catch {
    return [];
  }

  const lines = source.split(/\r?\n/);
  const findings = [];

  // Check file-level rules first
  for (const rule of RULES) {
    if (rule.checkFile) {
      const violated = rule.checkFile(source);
      if (violated) {
        const lineIdx = lines.findIndex((l) => violated.pattern.test(l) && !SUPPRESS_PATTERN.test(l));
        if (lineIdx !== -1) {
          findings.push({
            file: relative(REPO_ROOT, file).replace(/\\/g, "/"),
            line: lineIdx + 1,
            column: 1,
            rule: rule.id,
            severity: rule.severity,
            snippet: lines[lineIdx].trim().slice(0, 120),
            hint: violated.hint,
          });
        }
      }
    }
  }

  // Check line-level rules
  lines.forEach((line, index) => {
    if (SUPPRESS_PATTERN.test(line)) return;

    const scannable = maskComments(line);
    if (!scannable.trim()) return;

    for (const rule of RULES) {
      if (rule.checkFile) continue;
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
    console.error(`check:csv — scan root not found: ${SCAN_ROOT}`);
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
    console.log(`      -> suppress with: // csv-allow: <reason>`);
    console.log("");
  }

  if (errors.length === 0 && warnings.length === 0) {
    console.log(`check:csv — no issues found (${files.length} files scanned).`);
    return;
  }

  console.log(
    `check:csv — ${errors.length} error(s), ${warnings.length} warning(s) across ${files.length} files.`
  );
  process.exitCode = errors.length ? 1 : 0;
}

main();
