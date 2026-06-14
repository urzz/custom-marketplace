import { appendFileSync, mkdirSync } from 'node:fs';
import path from 'node:path';

const target = process.argv[2];
const payload = process.argv[3];

if (!target || !payload) {
  console.error('usage: node append-event.mjs <events-file> <json-string>');
  process.exit(1);
}

const filePath = path.resolve(process.cwd(), target);

let parsed;

try {
  parsed = JSON.parse(payload);
} catch {
  console.error('invalid JSON payload');
  process.exit(1);
}

mkdirSync(path.dirname(filePath), { recursive: true });
appendFileSync(filePath, `${JSON.stringify(parsed)}\n`);

console.log(filePath);
