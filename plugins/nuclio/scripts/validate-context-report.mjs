import { existsSync, readFileSync } from 'node:fs';

const filePath = process.argv[2];

function fail(message) {
  console.error(message);
  process.exit(1);
}

if (!filePath) {
  fail('usage: node validate-context-report.mjs <context-report.md>');
}

if (!existsSync(filePath)) {
  fail(`missing context report: ${filePath}`);
}

const raw = readFileSync(filePath, 'utf8');
const required = [
  ['.dev-docs/index.md', /\.dev-docs\/index\.md/],
  ['Loaded', /\bLoaded\b/i],
  ['Skipped', /\bSkipped\b/i],
  ['reason', /\breason\b/i],
  ['missing/stale/not applicable', /\b(missing|stale|not applicable)\b/i],
];
const missing = required.filter(([, pattern]) => !pattern.test(raw)).map(([label]) => label);

if (missing.length) {
  fail(`context report missing required content: ${missing.join(', ')}`);
}

console.log(`valid context report: ${filePath}`);
