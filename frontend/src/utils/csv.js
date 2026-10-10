/**
 * Safe CSV serialization utilities with protection against CSV Formula Injection (DDE injection).
 *
 * Cells starting with '=', '+', '-', '@', tab, or CR are prepended with a single quote
 * so spreadsheet viewers (Excel, Google Sheets, Calc) treat them as text rather than formulas.
 */

/**
 * Sanitize and format a single CSV cell value.
 *
 * @param {any} value
 * @returns {string}
 */
export function csvCell(value) {
  if (value === null || value === undefined) {
    return "";
  }
  let str = String(value);

  // CSV formula injection protection:
  // If the cell starts with =, +, -, @, \t, or \r, prefix with a single quote (')
  if (/^[=+\-@\t\r]/.test(str)) {
    str = "'" + str;
  }

  // Escape embedded quotes and wrap in quotes if it contains comma, double-quote, or newlines
  if (/[",\r\n]/.test(str)) {
    return `"${str.replace(/"/g, '""')}"`;
  }

  return str;
}

/**
 * Format a 2D array of rows into a CRLF-delimited CSV string.
 *
 * @param {Array<Array<any>>} rows
 * @param {Array<string>|null} [headers=null]
 * @returns {string}
 */
export function toCsv(rows = [], headers = null) {
  const lines = [];
  if (headers && headers.length > 0) {
    lines.push(headers.map(csvCell).join(","));
  }
  for (const row of rows) {
    lines.push(row.map(csvCell).join(","));
  }
  return lines.join("\r\n");
}
