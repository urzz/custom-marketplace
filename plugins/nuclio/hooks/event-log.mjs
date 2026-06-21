import { appendFileSync, existsSync, mkdirSync, readFileSync, readdirSync } from 'node:fs';
import path from 'node:path';

const tool = process.env.CLAUDE_TOOL_NAME || 'unknown';
const input = process.env.CLAUDE_TOOL_INPUT || '';
const output = process.env.CLAUDE_TOOL_OUTPUT || '';
const cwd = process.cwd();

function normalizeSlashes(value) {
  return String(value || '').replace(/\\/g, '/');
}

function normalizeRelativePath(value) {
  const normalized = path.posix.normalize(normalizeSlashes(value)).replace(/^\.\//, '');
  return normalized || '.';
}

function normalizePath(value) {
  return normalizeSlashes(value);
}

function safeWorkspaceRelativePath(value) {
  const raw = normalizeSlashes(value).trim();
  if (!raw) return '';
  let relative;
  if (raw.startsWith('/')) {
    relative = path.relative(cwd, raw);
  } else if (/^[A-Za-z]:\//.test(raw)) {
    return '';
  } else {
    relative = raw;
  }
  const normalized = normalizeRelativePath(relative);
  if (!normalized || normalized === '..' || normalized.startsWith('../') || normalized.startsWith('/')) return '';
  return normalized;
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
  if (!value || typeof value !== 'object') return values;
  if (Array.isArray(value)) {
    for (const item of value) collectStringValues(item, values);
    return values;
  }
  for (const nestedValue of Object.values(value)) collectStringValues(nestedValue, values);
  return values;
}

function isPathLikeKey(key) {
  return key === 'file_path' || key === 'path' || key.endsWith('_path');
}

function collectPathLikeValues(value, values = []) {
  if (!value || typeof value !== 'object') return values;
  if (Array.isArray(value)) {
    for (const item of value) collectPathLikeValues(item, values);
    return values;
  }
  for (const [key, nestedValue] of Object.entries(value)) {
    if (isPathLikeKey(key)) collectStringValues(nestedValue, values);
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

function activeChangeEventFile() {
  const changesDir = path.join(cwd, '.nuclio/changes');
  if (!existsSync(changesDir)) return null;
  const active = [];
  for (const entry of readdirSync(changesDir, { withFileTypes: true })) {
    if (!entry.isDirectory()) continue;
    const statePath = path.join(changesDir, entry.name, 'state.json');
    if (!existsSync(statePath)) continue;
    try {
      const state = JSON.parse(readFileSync(statePath, 'utf8'));
      if (state?.workflow === 'change' && state.status !== 'done' && state.status !== 'failed') {
        active.push({ id: entry.name, updated_at: state.updated_at || '' });
      }
    } catch {
      // Ignore invalid state in post-tool event logging.
    }
  }
  if (active.length !== 1) return null;
  return `.nuclio/changes/${active[0].id}/events.jsonl`;
}

function findEventsFile() {
  for (const candidate of candidateStrings()) {
    const normalized = normalizePath(candidate);
    const changeMatch = normalized.match(/(\.nuclio\/changes\/[^/]+\/)/);
    if (changeMatch) return `${changeMatch[1]}events.jsonl`;
    const projectMatch = normalized.match(/(\.nuclio\/project\/)/);
    if (projectMatch) return `${projectMatch[1]}events.jsonl`;
  }
  const active = activeChangeEventFile();
  if (active) return active;
  if (existsSync(path.join(cwd, '.nuclio/project/init-state.json'))) return '.nuclio/project/events.jsonl';
  return null;
}

function firstReferencedArtifact() {
  for (const candidate of candidateStrings()) {
    const normalized = normalizePath(candidate);
    const match = normalized.match(/(\.nuclio\/(?:project|changes\/[^/]+)\/[^\s"']+)/);
    if (match) return match[1].replace(/[),.;:]+$/, '');
    const devDocsMatch = normalized.match(/(\.dev-docs\/[^\s"']+)/);
    if (devDocsMatch) return devDocsMatch[1].replace(/[),.;:]+$/, '');
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
  if (normalized.includes('/.dev-docs/') || normalized.startsWith('.dev-docs/')) return 'memory.applied';
  return 'tool.used';
}

function isSafeEventsFile(filePath) {
  const projectEventsFile = path.resolve(cwd, '.nuclio/project/events.jsonl');
  if (filePath === projectEventsFile) return true;
  const changesRoot = path.resolve(cwd, '.nuclio/changes');
  const relativeToChanges = path.relative(changesRoot, filePath);
  if (relativeToChanges.startsWith('..') || path.isAbsolute(relativeToChanges)) return false;
  const segments = relativeToChanges.split(path.sep);
  return segments.length === 2 && segments[0] !== '' && segments[1] === 'events.jsonl';
}

function appendEvent(target, event) {
  const filePath = path.resolve(cwd, target);
  if (!isSafeEventsFile(filePath)) return;
  mkdirSync(path.dirname(filePath), { recursive: true });
  appendFileSync(filePath, `${JSON.stringify(event)}\n`);
}

function targetPaths() {
  return [...new Set(collectPathLikeValues(parsedInput).map(safeWorkspaceRelativePath).filter(Boolean))];
}

function normalizedSecretKey(key) {
  return String(key || '').replace(/[^A-Za-z0-9]/g, '').toLowerCase();
}

function isSecretKey(key) {
  const normalized = normalizedSecretKey(key);
  return normalized === 'token'
    || normalized === 'password'
    || normalized === 'secret'
    || normalized === 'authorization'
    || normalized === 'apikey'
    || normalized.includes('token')
    || normalized.includes('password')
    || normalized.includes('secret')
    || normalized.includes('authorization')
    || (normalized.includes('api') && normalized.includes('key'));
}

function redactedJsonValue(value) {
  if (Array.isArray(value)) return value.map((item) => redactedJsonValue(item));
  if (!value || typeof value !== 'object') return value;
  return Object.fromEntries(Object.entries(value).map(([key, nestedValue]) => [
    key,
    isSecretKey(key) ? '[REDACTED]' : redactedJsonValue(nestedValue),
  ]));
}

function secretKeyPattern() {
  return String.raw`[A-Za-z][A-Za-z0-9_-]*(?:api[_-]?key|token|password|secret|authorization)[A-Za-z0-9_-]*|(?:token|password|secret|authorization|api[_-]?key)|[A-Za-z][A-Za-z0-9_-]*api[A-Za-z0-9_-]*key[A-Za-z0-9_-]*`;
}

function redactSecretAssignment(match, key, separator) {
  return `${key}${separator}[REDACTED]`;
}

function redactedText(value) {
  const key = secretKeyPattern();
  return String(value || '')
    .replace(new RegExp(`\\b(${key})(\\s*[:=]\\s*)Bearer\\s+[^\\s,;]+`, 'gi'), (_match, secretKey, separator) => `${secretKey}${separator}Bearer [REDACTED]`)
    .replace(new RegExp(`(["'])(${key})(\\1\\s*:\\s*)(["'])[^"'\\r\\n]*\\4`, 'gi'), (_match, quote, secretKey, separator) => `${quote}${secretKey}${separator}${quote}[REDACTED]${quote}`)
    .replace(new RegExp(`\\b(${key})(\\s*[:=]\\s*)["'][^"'\\r\\n]*["']`, 'gi'), redactSecretAssignment)
    .replace(new RegExp(`\\b(${key})(\\s*[:=]\\s*)(?!Bearer\\b)[^\\s,;]+`, 'gi'), redactSecretAssignment)
    .replace(new RegExp(`(--(?:${key}))(=)[^\\s,;]+`, 'gi'), redactSecretAssignment)
    .replace(new RegExp(`(--(?:${key}))(\\s+)[^\\s,;]+`, 'gi'), redactSecretAssignment);
}

function redactedDebugSnippet(value) {
  const parsed = parseJson(value);
  if (parsed !== undefined) return redactedText(JSON.stringify(redactedJsonValue(parsed)));
  return redactedText(value);
}

function truncate(value, maxLength = 500) {
  const text = String(value || '');
  return text.length > maxLength ? `${text.slice(0, maxLength)}…` : text;
}

function sanitizedCommandOrNull() {
  if (parsedInput && typeof parsedInput === 'object' && !Array.isArray(parsedInput) && typeof parsedInput.command === 'string') {
    return truncate(redactedText(parsedInput.command), 300);
  }
  return null;
}

function exitCodeOrNull() {
  const rawExitCode = process.env.CLAUDE_TOOL_EXIT_CODE ?? process.env.CLAUDE_TOOL_STATUS;
  if (rawExitCode === undefined || rawExitCode === '') return null;
  const parsed = Number(rawExitCode);
  return Number.isFinite(parsed) ? parsed : null;
}

function currentTaskId() {
  const pathValues = candidateStrings().join('\n');
  const match = pathValues.match(/(?:^|\/)tasks?\/([^/\s]+)\//i)
    || pathValues.match(/(?:^|\/)\.nuclio\/changes\/[^/\s]+\/evidence\/([^/\s]+)\//i)
    || pathValues.match(/task[_-]?id["'\s:]+([A-Za-z0-9_.-]+)/i);
  return match ? match[1] : null;
}

function resultFromOutput() {
  if (/Blocked:/i.test(output)) return 'blocked';
  if (/\b(pass(?:ed)?|success|ok)\b/i.test(output)) return 'pass';
  if (/\b(fail(?:ed)?|error)\b/i.test(output)) return 'fail';
  return 'unknown';
}

const artifact = firstReferencedArtifact();
const blockedMatch = output.match(/Blocked:\s*([^\n]+)/i);
const result = blockedMatch ? 'blocked' : resultFromOutput();
const paths = targetPaths();
const event = {
  type: blockedMatch ? 'operation.blocked' : inferEventType(artifact),
  tool,
  artifact,
  task_id: currentTaskId(),
  result,
  target_paths: paths,
  reason: blockedMatch ? redactedText(`Blocked: ${blockedMatch[1].trim()}`) : null,
  summary: {
    tool,
    command: sanitizedCommandOrNull(),
    target_paths: paths,
    exit_code: exitCodeOrNull(),
    result,
  },
};

if (process.env.NUCLIO_DEBUG_EVENT_LOG === '1') {
  event.debug = {
    input: truncate(redactedDebugSnippet(input)),
    output: truncate(redactedDebugSnippet(output)),
  };
}

const eventsFile = findEventsFile();
if (eventsFile) appendEvent(eventsFile, event);
console.log(JSON.stringify(event));
