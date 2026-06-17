import { readFileSync } from 'node:fs';

const filePath = process.argv[2];

function fail(message) {
  console.error(message);
  process.exit(1);
}

if (!filePath) {
  fail('Usage: node validate-state.mjs <state-file.json>');
}

let state;
try {
  state = JSON.parse(readFileSync(filePath, 'utf8'));
} catch (error) {
  fail(`Invalid JSON: ${error.message}`);
}

function requireString(key, allowed) {
  if (typeof state[key] !== 'string') {
    fail(`Missing or invalid string field: ${key}`);
  }

  if (allowed && !allowed.includes(state[key])) {
    fail(`Invalid ${key}: ${state[key]}. Expected one of: ${allowed.join(', ')}`);
  }
}

function requireBooleanApproval(key) {
  if (!state.approved || typeof state.approved !== 'object' || typeof state.approved[key] !== 'boolean') {
    fail(`Missing approved.${key} boolean`);
  }
}

function hasField(key) {
  return Object.prototype.hasOwnProperty.call(state, key);
}

function requireNullableEnum(key, allowed) {
  if (!hasField(key)) {
    fail(`Missing field: ${key}`);
  }

  if (state[key] !== null && !allowed.includes(state[key])) {
    fail(`Invalid ${key}: ${state[key]}. Expected one of: ${allowed.join(', ')}, null`);
  }
}

function requireNullableString(key) {
  if (!hasField(key) || (state[key] !== null && typeof state[key] !== 'string')) {
    fail(`Missing or invalid nullable string field: ${key}`);
  }
}

function requireCurrentTask() {
  if (!hasField('current_task')) {
    fail('Missing field: current_task');
  }

  if (state.current_task === null || typeof state.current_task === 'string') {
    return;
  }

  if (
    typeof state.current_task === 'object' &&
    !Array.isArray(state.current_task) &&
    typeof state.current_task.id === 'string'
  ) {
    return;
  }

  fail('Invalid current_task: expected null, string, or object with string id');
}

if (state.workflow === 'project_initialization') {
  requireString('phase', ['foundation', 'architecture', 'scaffold', 'initial_dev_docs', 'done']);
  requireString('status', ['active', 'waiting_human', 'failed', 'done']);
  requireNullableEnum('gate', [
    'foundation_approval',
    'architecture_approval',
    'scaffold_approval',
    'initial_dev_docs_approval',
    'risk_approval',
  ]);
  requireBooleanApproval('foundation');
  requireBooleanApproval('architecture');
  requireBooleanApproval('scaffold');
  requireBooleanApproval('initial_dev_docs');
  requireNullableString('blocking_reason');
} else if (state.workflow === 'change') {
  requireString('phase', ['spec', 'design', 'build', 'close']);
  requireString('status', ['active', 'waiting_human', 'failed', 'done']);
  requireNullableEnum('gate', [
    'spec_approval',
    'design_approval',
    'risk_approval',
    'final_acceptance',
    'memory_approval',
  ]);
  requireCurrentTask();
  requireBooleanApproval('spec');
  requireBooleanApproval('design');
  requireBooleanApproval('final');
  requireBooleanApproval('memory');
  requireNullableString('blocking_reason');

  if (typeof state.build_iteration !== 'number') {
    fail('Missing numeric build_iteration');
  }
} else {
  fail('workflow must be project_initialization or change');
}

if (!state.updated_at || typeof state.updated_at !== 'string') {
  fail('Missing updated_at string');
}

console.log(`valid state: ${filePath}`);
