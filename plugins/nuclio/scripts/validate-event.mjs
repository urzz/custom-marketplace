import { readFileSync } from 'node:fs';
import path from 'node:path';

const DECISIONS = ['accept', 'reject', 'edit', 'defer'];
const RESULTS = ['pass', 'needs_patch', 'needs_redesign', 'blocked', 'fail', 'unknown'];

function isPlainObject(value) {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value);
}

function normalizeSlashes(value) {
  return String(value || '').replace(/\\/g, '/');
}

function isSafeRelativePath(value) {
  if (typeof value !== 'string' || !value.trim()) {
    return false;
  }
  const normalized = path.posix.normalize(normalizeSlashes(value)).replace(/^\.\//, '');
  return normalized && normalized !== '..' && !normalized.startsWith('../') && !path.posix.isAbsolute(normalizeSlashes(value));
}

export function validateEventObject(event) {
  const errors = [];

  if (!isPlainObject(event)) {
    return { ok: false, errors: ['event must be a JSON object'] };
  }

  if (typeof event.type !== 'string' || !event.type.trim()) {
    errors.push('event.type must be a non-empty string');
  }

  if (!(typeof event.tool === 'string' || event.tool === null)) {
    errors.push('event.tool must be a string or null');
  }

  if (!(typeof event.artifact === 'string' || event.artifact === null)) {
    errors.push('event.artifact must be a string or null');
  } else if (typeof event.artifact === 'string' && event.artifact && !isSafeRelativePath(event.artifact)) {
    errors.push('event.artifact must be a safe relative path when provided');
  }

  if (Object.prototype.hasOwnProperty.call(event, 'target_paths')) {
    if (!Array.isArray(event.target_paths)) {
      errors.push('event.target_paths must be an array');
    } else {
      for (const targetPath of event.target_paths) {
        if (!isSafeRelativePath(targetPath)) {
          errors.push(`event.target_paths entry must be a safe relative path: ${String(targetPath)}`);
        }
      }
    }
  }

  if (Object.prototype.hasOwnProperty.call(event, 'decision') && event.decision !== null) {
    if (typeof event.decision !== 'string' || !DECISIONS.includes(event.decision)) {
      errors.push(`event.decision must be one of: ${DECISIONS.join(', ')}, null`);
    }
  }

  if (Object.prototype.hasOwnProperty.call(event, 'task_id') && event.task_id !== null && typeof event.task_id !== 'string') {
    errors.push('event.task_id must be a string or null');
  }

  if (Object.prototype.hasOwnProperty.call(event, 'result') && event.result !== null) {
    if (typeof event.result !== 'string' || !RESULTS.includes(event.result)) {
      errors.push(`event.result must be one of: ${RESULTS.join(', ')}, null`);
    }
  }

  if (Object.prototype.hasOwnProperty.call(event, 'reason') && event.reason !== null && typeof event.reason !== 'string') {
    errors.push('event.reason must be a string or null');
  }

  return { ok: errors.length === 0, errors };
}

export function parseEventJson(raw) {
  let parsed;
  try {
    parsed = JSON.parse(raw);
  } catch (error) {
    return { ok: false, event: null, errors: [`Invalid JSON: ${error.message}`] };
  }

  const validation = validateEventObject(parsed);
  return { ok: validation.ok, event: parsed, errors: validation.errors };
}

export function validateEventJsonl(raw) {
  const errors = [];
  const lines = raw.split(/\r?\n/).filter((line) => line.trim());
  for (const [index, line] of lines.entries()) {
    const result = parseEventJson(line);
    if (!result.ok) {
      errors.push(`line ${index + 1}: ${result.errors.join('; ')}`);
    }
  }

  return { ok: errors.length === 0, errors };
}

export function validateEventFile(filePath) {
  let raw;
  try {
    raw = readFileSync(filePath, 'utf8');
  } catch (error) {
    return { ok: false, errors: [`Cannot read event file: ${error.message}`] };
  }

  return validateEventJsonl(raw);
}

function isDirectRun() {
  return process.argv[1] && path.resolve(process.argv[1]) === path.resolve(import.meta.filename);
}

if (isDirectRun()) {
  const arg = process.argv[2];
  if (!arg) {
    console.error('usage: node validate-event.mjs <json-event-string|events.jsonl>');
    process.exit(1);
  }

  const result = arg.trim().startsWith('{') ? parseEventJson(arg) : validateEventFile(path.resolve(process.cwd(), arg));
  if (!result.ok) {
    console.error(result.errors.join('\n'));
    process.exit(1);
  }

  console.log('valid event');
}
