import { appendFileSync, mkdirSync } from 'node:fs';
import path from 'node:path';

const tool = process.env.CLAUDE_TOOL_NAME || 'unknown';
const input = process.env.CLAUDE_TOOL_INPUT || '';
const output = process.env.CLAUDE_TOOL_OUTPUT || '';
const cwd = process.cwd();

function normalizePath(value) {
  return String(value || '').replace(/\\/g, '/');
}

function parseJson(raw) {
  try {
    return JSON.parse(raw);
  } catch {
    return undefined;
  }
}

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

function isPathLikeKey(key) {
  return key === 'file_path' || key === 'path' || key.endsWith('_path');
}

function collectPathLikeValues(value, values = []) {
  if (!value || typeof value !== 'object') {
    return values;
  }

  if (Array.isArray(value)) {
    for (const item of value) {
      collectPathLikeValues(item, values);
    }
    return values;
  }

  for (const [key, nestedValue] of Object.entries(value)) {
    if (isPathLikeKey(key)) {
      collectStringValues(nestedValue, values);
    }

    collectPathLikeValues(nestedValue, values);
  }

  return values;
}

const parsedInput = parseJson(input);
const parsedOutput = parseJson(output);

function candidateStrings() {
  return [
    ...collectPathLikeValues(parsedInput),
    ...collectPathLikeValues(parsedOutput),
    ...collectStringValues(parsedInput),
    ...collectStringValues(parsedOutput),
    input,
    output,
  ];
}

function findEventsFile() {
  for (const candidate of candidateStrings()) {
    const normalized = normalizePath(candidate);
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

function firstReferencedArtifact() {
  for (const candidate of candidateStrings()) {
    const normalized = normalizePath(candidate);
    const match = normalized.match(/(\.nuclio\/(?:project|changes\/[^/]+)\/[^\s"']+)/);
    if (match) {
      return match[1].replace(/[),.;:]+$/, '');
    }
  }

  return null;
}

function inferEventType(artifact) {
  const normalized = normalizePath(artifact || '');

  if (normalized.endsWith('/project-brief.md')) return 'project_init.project_brief.generated';
  if (normalized.endsWith('/architecture-baseline.md')) return 'project_init.architecture_baseline.generated';
  if (normalized.endsWith('/scaffold-plan.yaml')) return 'project_init.scaffold_plan.generated';
  if (normalized.endsWith('/initial-dev-docs.patch.md')) return 'project_init.initial_dev_docs_patch.generated';
  if (normalized.endsWith('/spec.md')) return 'spec.generated';
  if (normalized.endsWith('/design.md')) return 'design.generated';
  if (normalized.endsWith('/plan.yaml')) return 'artifact.generated';
  if (normalized.endsWith('/context.md') || normalized.endsWith('/context-report.md')) return 'context.reported';
  if (normalized.endsWith('/evidence/verify.md')) return 'task.verified';
  if (normalized.endsWith('/evidence/review.md')) return 'task.reviewed';
  if (normalized.endsWith('/close.md')) return 'close.generated';
  if (normalized.endsWith('/memory.patch.md')) return 'memory_patch.generated';
  if (normalized.includes('/.dev-docs/') || normalized.includes('.dev-docs/')) return 'memory.applied';

  return 'tool.used';
}

function isSafeEventsFile(filePath) {
  const projectEventsFile = path.resolve(cwd, '.nuclio/project/events.jsonl');
  if (filePath === projectEventsFile) {
    return true;
  }

  const changesRoot = path.resolve(cwd, '.nuclio/changes');
  const relativeToChanges = path.relative(changesRoot, filePath);
  if (relativeToChanges.startsWith('..') || path.isAbsolute(relativeToChanges)) {
    return false;
  }

  const segments = relativeToChanges.split(path.sep);
  return segments.length === 2 && segments[0] !== '' && segments[1] === 'events.jsonl';
}

function appendEvent(target, event) {
  const filePath = path.resolve(cwd, target);
  if (!isSafeEventsFile(filePath)) {
    return;
  }

  mkdirSync(path.dirname(filePath), { recursive: true });
  appendFileSync(filePath, `${JSON.stringify(event)}\n`);
}

const artifact = firstReferencedArtifact();
const event = {
  type: inferEventType(artifact),
  tool,
  artifact,
  debug: {
    input: input.slice(0, 500),
    output: output.slice(0, 500),
  },
};

const eventsFile = findEventsFile();

if (eventsFile) {
  appendEvent(eventsFile, event);
}

console.log(JSON.stringify(event));
