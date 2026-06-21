import { mkdirSync, writeFileSync } from 'node:fs';
import path from 'node:path';
import { validateStateObject } from './validate-state.mjs';

const target = process.argv[2];
const payload = process.argv[3];

if (!target || !payload) {
  console.error('usage: node write-state.mjs <state-file> <json-string>');
  process.exit(1);
}

const cwd = process.cwd();
const filePath = path.resolve(cwd, target);

function normalizeSlashes(value) {
  return String(value || '').replace(/\\/g, '/');
}

function safeRelativeTarget(candidate) {
  const relative = path.relative(cwd, candidate);
  if (!relative || relative.startsWith('..') || path.isAbsolute(relative)) return '';
  return normalizeSlashes(relative);
}

function isAllowedStateTarget(relativeTarget) {
  return relativeTarget === '.nuclio/project/init-state.json'
    || /^\.nuclio\/changes\/[^/]+\/state\.json$/.test(relativeTarget);
}

const relativeTarget = safeRelativeTarget(filePath);
if (!isAllowedStateTarget(relativeTarget)) {
  console.error('state file must be .nuclio/project/init-state.json or .nuclio/changes/<id>/state.json');
  process.exit(1);
}

let parsed;

try {
  parsed = JSON.parse(payload);
} catch {
  console.error('invalid JSON payload');
  process.exit(1);
}

const validation = validateStateObject(parsed);
if (!validation.ok) {
  console.error(validation.errors.join('\n'));
  process.exit(1);
}

mkdirSync(path.dirname(filePath), { recursive: true });
writeFileSync(filePath, `${JSON.stringify(parsed, null, 2)}\n`);

console.log(filePath);
