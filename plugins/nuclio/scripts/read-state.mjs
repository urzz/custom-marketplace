import { existsSync, readFileSync } from 'node:fs';
import path from 'node:path';

const target = process.argv[2];

if (!target) {
  console.error('usage: node read-state.mjs <state-file>');
  process.exit(1);
}

const filePath = path.resolve(process.cwd(), target);

if (!existsSync(filePath)) {
  console.log('null');
  process.exit(0);
}

const raw = readFileSync(filePath, 'utf8');
console.log(raw.trim() || 'null');
