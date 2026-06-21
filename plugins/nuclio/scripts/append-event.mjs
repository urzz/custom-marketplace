import { appendFileSync, mkdirSync } from 'node:fs';
import path from 'node:path';
import { validateEventObject } from './validate-event.mjs';

const target = process.argv[2];
const payload = process.argv[3];
const cwd = process.cwd();

if (!target || !payload) {
  console.error('usage: node append-event.mjs <events-file> <json-string>');
  process.exit(1);
}

const filePath = path.resolve(cwd, target);

function isSafeEventsFile(candidate) {
  const projectEventsFile = path.resolve(cwd, '.nuclio/project/events.jsonl');
  if (candidate === projectEventsFile) {
    return true;
  }

  const changesRoot = path.resolve(cwd, '.nuclio/changes');
  const relativeToChanges = path.relative(changesRoot, candidate);
  if (relativeToChanges.startsWith('..') || path.isAbsolute(relativeToChanges)) {
    return false;
  }

  const segments = relativeToChanges.split(path.sep);
  return segments.length === 2 && segments[0] !== '' && segments[1] === 'events.jsonl';
}

if (!isSafeEventsFile(filePath)) {
  console.error('events file must be .nuclio/project/events.jsonl or .nuclio/changes/<id>/events.jsonl');
  process.exit(1);
}

let parsed;

try {
  parsed = JSON.parse(payload);
} catch {
  console.error('invalid JSON payload');
  process.exit(1);
}

const validation = validateEventObject(parsed);
if (!validation.ok) {
  console.error(validation.errors.join('\n'));
  process.exit(1);
}

mkdirSync(path.dirname(filePath), { recursive: true });
appendFileSync(filePath, `${JSON.stringify(parsed)}\n`);

console.log(filePath);
