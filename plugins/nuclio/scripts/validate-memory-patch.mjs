import { existsSync, readFileSync } from 'node:fs';
import path from 'node:path';

const filePath = process.argv[2];
const DECISIONS = ['accept', 'reject', 'edit', 'defer'];

function fail(message) {
  console.error(message);
  process.exit(1);
}

if (!filePath) {
  fail('usage: node validate-memory-patch.mjs <memory.patch.md>');
}

if (!existsSync(filePath)) {
  fail(`missing memory patch: ${filePath}`);
}

function normalize(value) {
  return path.posix.normalize(String(value || '').replace(/\\/g, '/')).replace(/^\.\//, '');
}

function validTarget(target) {
  const normalized = normalize(target);
  return normalized.startsWith('.dev-docs/') && normalized !== '.dev-docs/' && !normalized.includes('/../');
}

function parseTableRows(raw) {
  const rows = [];
  const lines = raw.split(/\r?\n/).map((line) => line.trim()).filter((line) => line.startsWith('|') && line.endsWith('|'));
  if (lines.length < 2) return rows;
  const headers = lines[0].slice(1, -1).split('|').map((cell) => cell.trim().toLowerCase());
  const idIndex = headers.indexOf('id');
  const targetIndex = headers.findIndex((header) => ['target', 'path', 'target_path'].includes(header));
  const decisionIndex = headers.indexOf('decision');
  if (idIndex === -1 || targetIndex === -1 || decisionIndex === -1) return rows;
  for (const line of lines.slice(2)) {
    const cells = line.slice(1, -1).split('|').map((cell) => cell.trim());
    if (cells.every((cell) => /^-+$/.test(cell))) continue;
    rows.push({ id: cells[idIndex], target: cells[targetIndex], decision: cells[decisionIndex] });
  }
  return rows;
}

function parseUpdateBlocks(raw) {
  const rows = [];
  const blocks = raw.split(/(?=^##+\s+Update\b)/gim);
  for (const block of blocks) {
    const id = block.match(/^\s*(?:[-*]\s*)?id:\s*(\S+)/im)?.[1];
    const target = block.match(/^\s*(?:[-*]\s*)?(?:target|target_path|path):\s*(\S+)/im)?.[1];
    const decision = block.match(/^\s*(?:[-*]\s*)?decision:\s*(\S+)/im)?.[1];
    if (id || target || decision) rows.push({ id, target, decision });
  }
  return rows;
}

const raw = readFileSync(filePath, 'utf8');
const rows = [...parseTableRows(raw), ...parseUpdateBlocks(raw)];
const errors = [];
if (!rows.length) errors.push('memory patch must include update blocks or a table with id, target, decision');
for (const [index, row] of rows.entries()) {
  if (!row.id) errors.push(`row ${index + 1} missing id`);
  if (!row.target || !validTarget(row.target)) errors.push(`row ${index + 1} target must be under .dev-docs`);
  if (!row.decision || !DECISIONS.includes(String(row.decision).toLowerCase())) errors.push(`row ${index + 1} decision must be one of: ${DECISIONS.join(', ')}`);
}

if (errors.length) fail(errors.join('\n'));
console.log(`valid memory patch: ${filePath}`);
