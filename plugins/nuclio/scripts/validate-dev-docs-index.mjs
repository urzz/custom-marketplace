import { existsSync, readFileSync } from 'node:fs';
import path from 'node:path';

const filePath = process.argv[2];
const LOAD_MODES = ['index', 'leaf', 'always', 'conditional'];
const REQUIRED_HEADERS = ['Path', 'Load Mode', 'Visible In', 'Load When'];

function fail(message) {
  console.error(message);
  process.exit(1);
}

if (!filePath) {
  fail('usage: node validate-dev-docs-index.mjs <index.md>');
}

if (!existsSync(filePath)) {
  fail(`missing dev docs index: ${filePath}`);
}

function splitTableLine(line) {
  return line.slice(1, -1).split('|').map((cell) => cell.trim());
}

function normalizeHeader(value) {
  return String(value || '').trim().toLowerCase();
}

function parseTables(raw) {
  const lines = raw.split(/\r?\n/);
  const tables = [];
  for (let index = 0; index < lines.length; index += 1) {
    const line = lines[index].trim();
    if (!line.startsWith('|') || !line.endsWith('|')) continue;
    const tableLines = [];
    for (let cursor = index; cursor < lines.length; cursor += 1) {
      const tableLine = lines[cursor].trim();
      if (!tableLine.startsWith('|') || !tableLine.endsWith('|')) break;
      tableLines.push(tableLine);
    }
    if (tableLines.length >= 2) {
      const headers = splitTableLine(tableLines[0]);
      const rows = [];
      for (const rowLine of tableLines.slice(2)) {
        const cells = splitTableLine(rowLine);
        if (cells.every((cell) => /^:?-+:?$/.test(cell))) continue;
        const row = {};
        for (const [cellIndex, header] of headers.entries()) row[header] = cells[cellIndex] ?? '';
        if (Object.values(row).some((cell) => String(cell).trim())) rows.push(row);
      }
      tables.push({ headers, rows });
    }
    index += Math.max(tableLines.length - 1, 0);
  }
  return tables;
}

function findIndexTable(raw) {
  const required = REQUIRED_HEADERS.map(normalizeHeader);
  return parseTables(raw).find((table) => {
    const headers = table.headers.map(normalizeHeader);
    return required.every((header) => headers.includes(header));
  }) ?? null;
}

function rowValue(row, header) {
  const found = Object.keys(row).find((key) => normalizeHeader(key) === normalizeHeader(header));
  return found ? String(row[found] || '').trim() : '';
}

function isWindowsDriveAbsolutePath(value) {
  return /^[A-Za-z]:[\\/]/.test(String(value || '').trim());
}

function isSafeRelativePath(value) {
  if (isWindowsDriveAbsolutePath(value)) return false;
  const raw = String(value || '').replace(/\\/g, '/').trim();
  if (!raw || raw.includes('\0') || path.posix.isAbsolute(raw)) return false;
  if (raw.startsWith('~') || raw.startsWith('.nuclio/') || raw.startsWith('.dev-docs/')) return false;
  if (raw.split('/').includes('..')) return false;
  const normalized = path.posix.normalize(raw);
  if (normalized.split('/').includes('..')) return false;
  return normalized === raw.replace(/^\.\//, '');
}

const raw = readFileSync(filePath, 'utf8');
const table = findIndexTable(raw);
const errors = [];

if (!table) {
  errors.push(`index must include a table with headers: ${REQUIRED_HEADERS.join(', ')}`);
} else {
  if (!table.rows.length) errors.push('index table must include at least one row');
  for (const [index, row] of table.rows.entries()) {
    const label = `row ${index + 1}`;
    const docPath = rowValue(row, 'Path');
    const loadMode = rowValue(row, 'Load Mode').toLowerCase();
    const visibleIn = rowValue(row, 'Visible In');
    const loadWhen = rowValue(row, 'Load When');

    if (!isSafeRelativePath(docPath)) errors.push(`${label} Path must be a safe relative path`);
    if (!LOAD_MODES.includes(loadMode)) errors.push(`${label} Load Mode must be one of: ${LOAD_MODES.join(', ')}`);
    if (!visibleIn) errors.push(`${label} Visible In must be non-empty`);
    if (!loadWhen) errors.push(`${label} Load When must be non-empty`);
  }
}

if (errors.length) fail(errors.join('\n'));
console.log(`valid dev docs index: ${filePath}`);
