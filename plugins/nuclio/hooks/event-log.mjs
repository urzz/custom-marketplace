import { appendFileSync, mkdirSync } from 'node:fs';
import path from 'node:path';

const tool = process.env.CLAUDE_TOOL_NAME || 'unknown';
const input = process.env.CLAUDE_TOOL_INPUT || '';
const output = process.env.CLAUDE_TOOL_OUTPUT || '';
const cwd = process.cwd();

const summary = {
  tool,
  input: input.slice(0, 500),
  output: output.slice(0, 500),
};

function collectStringValues(value, values = []) {
  if (typeof value === 'string') {
    values.push(value);
    return values;
  }

  if (!value || typeof value !== 'object') {
    return values;
  }

  if (Array.isArray(value)) {
    for (const item of value) {
      collectStringValues(item, values);
    } 
    return values;
  }

  for (const nestedValue of Object.values(value)) {
    collectStringValues(nestedValue, values);
  }

  return values;
}

function extractJsonStrings(raw) {
  try {
    const parsed = JSON.parse(raw);
    return collectStringValues(parsed);
  } catch {
    return [];
  }
}

function findEventsFile(rawText) {
  const candidates = [
    ...extractJsonStrings(input),
    ...extractJsonStrings(output),
    input,
    output,
  ];

  for (const candidate of candidates) {
    const normalized = String(candidate).replace(/\\/g, '/');
    const changeMatch = normalized.match(/(\.nuclio\/changes\/[^/]+\/)/);
    if (changeMatch) {
      return `${changeMatch[1]}events.jsonl`;
    }

    const projectMatch = normalized.match(/(\.nuclio\/project\/)/);
    if (projectMatch) {
      return `${projectMatch[1]}events.jsonl`;
    }
  }

  return null;
}

function appendSummary(target) {
  const filePath = path.resolve(cwd, target);
  mkdirSync(path.dirname(filePath), { recursive: true });
  appendFileSync(filePath, `${JSON.stringify(summary)}\n`);
}

const eventsFile = findEventsFile(input) || findEventsFile(output);

if (eventsFile) {
  appendSummary(eventsFile);
}

console.log(JSON.stringify(summary));
