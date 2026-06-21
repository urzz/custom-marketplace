import { readFileSync } from 'node:fs';
import path from 'node:path';

const PROJECT_PHASES = ['foundation', 'architecture', 'scaffold', 'initial_dev_docs', 'done'];
const PROJECT_STATUSES = ['active', 'waiting_human', 'failed', 'done'];
const PROJECT_GATES = [
  'foundation_approval',
  'architecture_approval',
  'scaffold_approval',
  'initial_dev_docs_approval',
  'risk_approval',
];
const CHANGE_PHASES = ['spec', 'design', 'build', 'close'];
const CHANGE_STATUSES = ['active', 'waiting_human', 'failed', 'done'];
const CHANGE_GATES = [
  'spec_approval',
  'design_approval',
  'risk_approval',
  'final_acceptance',
  'memory_approval',
];
const CHANGE_KINDS = ['feature', 'bugfix', 'refactor', 'tech_debt', 'docs', 'maintenance'];
const REPOSITORY_STAGES = ['empty_repo', 'skeleton_repo', 'existing_app_without_foundation', 'existing_app_with_foundation'];

function hasOwn(value, key) {
  return Object.prototype.hasOwnProperty.call(value, key);
}

function isPlainObject(value) {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value);
}

function normalizeSlashes(value) {
  return String(value || '').replace(/\\/g, '/');
}

function normalizedRelativePath(value) {
  const normalized = path.posix.normalize(normalizeSlashes(value)).replace(/^\.\//, '');
  return normalized === '.' ? '' : normalized;
}

function isSafeRelativePath(value) {
  const normalized = normalizedRelativePath(value);
  return Boolean(normalized) && normalized !== '..' && !normalized.startsWith('../') && !path.posix.isAbsolute(normalizeSlashes(value));
}

function addError(errors, message) {
  errors.push(message);
}

function requireString(state, key, allowed, errors) {
  if (typeof state[key] !== 'string') {
    addError(errors, `Missing or invalid string field: ${key}`);
    return;
  }

  if (allowed && !allowed.includes(state[key])) {
    addError(errors, `Invalid ${key}: ${state[key]}. Expected one of: ${allowed.join(', ')}`);
  }
}

function requireBooleanApproval(state, key, errors) {
  if (!isPlainObject(state.approved) || typeof state.approved[key] !== 'boolean') {
    addError(errors, `Missing approved.${key} boolean`);
  }
}

function validateTargetPathScope(scope, key, errors) {
  if (scope === undefined) {
    return;
  }

  if (!isPlainObject(scope)) {
    addError(errors, `Invalid approved.${key}: expected object`);
    return;
  }

  if (!Array.isArray(scope.target_paths)) {
    addError(errors, `Invalid approved.${key}.target_paths: expected array`);
    return;
  }

  for (const targetPath of scope.target_paths) {
    if (typeof targetPath !== 'string' || !isSafeRelativePath(targetPath)) {
      addError(errors, `Invalid approved.${key}.target_paths entry: ${String(targetPath)}`);
    }
  }
}

function requireNullableEnum(state, key, allowed, errors) {
  if (!hasOwn(state, key)) {
    addError(errors, `Missing field: ${key}`);
    return;
  }

  if (state[key] !== null && !allowed.includes(state[key])) {
    addError(errors, `Invalid ${key}: ${state[key]}. Expected one of: ${allowed.join(', ')}, null`);
  }
}

function requireNullableString(state, key, errors) {
  if (!hasOwn(state, key) || (state[key] !== null && typeof state[key] !== 'string')) {
    addError(errors, `Missing or invalid nullable string field: ${key}`);
  }
}

function validateOptionalString(state, key, errors) {
  if (hasOwn(state, key) && state[key] !== null && typeof state[key] !== 'string') {
    addError(errors, `Invalid ${key}: expected string or null`);
  }
}

function validateOptionalEnum(state, key, allowed, errors) {
  if (hasOwn(state, key) && state[key] !== null && !allowed.includes(state[key])) {
    addError(errors, `Invalid ${key}: ${state[key]}. Expected one of: ${allowed.join(', ')}, null`);
  }
}

function validateCurrentTask(state, errors) {
  if (!hasOwn(state, 'current_task')) {
    addError(errors, 'Missing field: current_task');
    return;
  }

  if (state.current_task === null || typeof state.current_task === 'string') {
    return;
  }

  if (isPlainObject(state.current_task) && typeof state.current_task.id === 'string') {
    return;
  }

  addError(errors, 'Invalid current_task: expected null, string, or object with string id');
}

function validateRiskApprovals(state, errors) {
  if (!hasOwn(state, 'risk_approvals')) {
    return;
  }

  if (!Array.isArray(state.risk_approvals)) {
    addError(errors, 'Invalid risk_approvals: expected array');
    return;
  }

  for (const [index, approval] of state.risk_approvals.entries()) {
    if (!isPlainObject(approval)) {
      addError(errors, `Invalid risk_approvals[${index}]: expected object`);
      continue;
    }

    if (typeof approval.approved !== 'boolean') {
      addError(errors, `Invalid risk_approvals[${index}].approved: expected boolean`);
    }

    if (approval.scope !== 'current_workflow') {
      addError(errors, `Invalid risk_approvals[${index}].scope: expected current_workflow`);
    }

    if (typeof approval.command_pattern !== 'string' || !approval.command_pattern.trim()) {
      addError(errors, `Invalid risk_approvals[${index}].command_pattern: expected non-empty string`);
    }

    if (hasOwn(approval, 'expires_at') && approval.expires_at !== null && typeof approval.expires_at !== 'string') {
      addError(errors, `Invalid risk_approvals[${index}].expires_at: expected string or null`);
    }

    if (hasOwn(approval, 'reason') && approval.reason !== null && typeof approval.reason !== 'string') {
      addError(errors, `Invalid risk_approvals[${index}].reason: expected string or null`);
    }
  }
}

function validateProjectState(state, errors) {
  requireString(state, 'phase', PROJECT_PHASES, errors);
  requireString(state, 'status', PROJECT_STATUSES, errors);
  requireNullableEnum(state, 'gate', PROJECT_GATES, errors);
  requireBooleanApproval(state, 'foundation', errors);
  requireBooleanApproval(state, 'architecture', errors);
  requireBooleanApproval(state, 'scaffold', errors);
  requireBooleanApproval(state, 'initial_dev_docs', errors);
  validateTargetPathScope(state.approved?.initial_dev_docs_scope, 'initial_dev_docs_scope', errors);
  requireNullableString(state, 'blocking_reason', errors);
  validateOptionalString(state, 'project_id', errors);
  validateOptionalEnum(state, 'repository_stage', REPOSITORY_STAGES, errors);
}

function validateChangeState(state, errors) {
  requireString(state, 'phase', CHANGE_PHASES, errors);
  requireString(state, 'status', CHANGE_STATUSES, errors);
  requireNullableEnum(state, 'gate', CHANGE_GATES, errors);
  validateCurrentTask(state, errors);
  requireBooleanApproval(state, 'spec', errors);
  requireBooleanApproval(state, 'design', errors);
  requireBooleanApproval(state, 'final', errors);
  requireBooleanApproval(state, 'memory', errors);
  validateTargetPathScope(state.approved?.memory_scope, 'memory_scope', errors);
  requireNullableString(state, 'blocking_reason', errors);
  validateOptionalString(state, 'project_id', errors);
  validateOptionalString(state, 'change_id', errors);
  validateOptionalEnum(state, 'change_kind', CHANGE_KINDS, errors);

  if (typeof state.build_iteration !== 'number') {
    addError(errors, 'Missing numeric build_iteration');
  }
}

export function validateStateObject(state) {
  const errors = [];

  if (!isPlainObject(state)) {
    return { ok: false, errors: ['state must be a JSON object'] };
  }

  if (state.workflow === 'project_initialization') {
    validateProjectState(state, errors);
  } else if (state.workflow === 'change') {
    validateChangeState(state, errors);
  } else {
    addError(errors, 'workflow must be project_initialization or change');
  }

  validateRiskApprovals(state, errors);

  if (!state.updated_at || typeof state.updated_at !== 'string') {
    addError(errors, 'Missing updated_at string');
  }

  return { ok: errors.length === 0, errors };
}

export function parseStateJson(raw) {
  let parsed;
  try {
    parsed = JSON.parse(raw);
  } catch (error) {
    return { ok: false, state: null, errors: [`Invalid JSON: ${error.message}`] };
  }

  const validation = validateStateObject(parsed);
  return { ok: validation.ok, state: parsed, errors: validation.errors };
}

export function validateStateFile(filePath) {
  let raw;
  try {
    raw = readFileSync(filePath, 'utf8');
  } catch (error) {
    return { ok: false, state: null, errors: [`Cannot read state file: ${error.message}`] };
  }

  return parseStateJson(raw);
}

function isDirectRun() {
  return process.argv[1] && path.resolve(process.argv[1]) === path.resolve(import.meta.filename);
}

if (isDirectRun()) {
  const filePath = process.argv[2];

  if (!filePath) {
    console.error('Usage: node validate-state.mjs <state-file.json>');
    process.exit(1);
  }

  const result = validateStateFile(filePath);
  if (!result.ok) {
    console.error(result.errors.join('\n'));
    process.exit(1);
  }

  console.log(`valid state: ${filePath}`);
}
