import { existsSync, readFileSync, readdirSync } from 'node:fs';
import path from 'node:path';
import { validateStateObject } from './validate-state.mjs';

const cwd = process.cwd();

function readStateIfPresent(filePath) {
  if (!existsSync(filePath)) {
    return null;
  }

  try {
    const parsed = JSON.parse(readFileSync(filePath, 'utf8'));
    const validation = validateStateObject(parsed);
    return {
      path: path.relative(cwd, filePath).replace(/\\/g, '/'),
      valid: validation.ok,
      errors: validation.errors,
      state: parsed,
    };
  } catch (error) {
    return {
      path: path.relative(cwd, filePath).replace(/\\/g, '/'),
      valid: false,
      errors: [`Invalid JSON: ${error.message}`],
      state: null,
    };
  }
}

function listChangeStates() {
  const changesDir = path.join(cwd, '.nuclio/changes');
  if (!existsSync(changesDir)) {
    return [];
  }

  const states = [];
  for (const entry of readdirSync(changesDir, { withFileTypes: true })) {
    if (!entry.isDirectory()) {
      continue;
    }
    const stateInfo = readStateIfPresent(path.join(changesDir, entry.name, 'state.json'));
    if (stateInfo) {
      states.push({ change_id: entry.name, ...stateInfo });
    }
  }

  return states.sort((a, b) => String(b.state?.updated_at || '').localeCompare(String(a.state?.updated_at || '')));
}

const foundationDetails = {
  nuclio_dir: existsSync(path.join(cwd, '.nuclio')),
  dev_docs_index: existsSync(path.join(cwd, '.dev-docs/index.md')),
};
const foundation = foundationDetails.nuclio_dir && foundationDetails.dev_docs_index ? 'ready' : 'missing';
const projectState = readStateIfPresent(path.join(cwd, '.nuclio/project/init-state.json'));
const changes = listChangeStates();
const activeChanges = changes.filter((entry) => entry.valid && entry.state?.workflow === 'change' && entry.state.status !== 'done' && entry.state.status !== 'failed');
const invalidStates = [projectState, ...changes].filter((entry) => entry && !entry.valid);

let ok = true;
let nextAction = 'resume';
const errors = [];
if (invalidStates.length) {
  ok = false;
  nextAction = projectState ? 'resume' : 'project_init';
  errors.push(...invalidStates.map((entry) => ({ path: entry.path, errors: entry.errors })));
} else if (activeChanges.length > 1) {
  ok = false;
  nextAction = 'resolve_multiple_active_changes';
  errors.push({ message: 'multiple active changes found', change_ids: activeChanges.map((entry) => entry.change_id) });
} else if (!projectState || foundation === 'missing') {
  nextAction = 'project_init';
} else if (activeChanges.length === 1) {
  nextAction = 'continue_current_change';
}

console.log(JSON.stringify({
  ok,
  foundation,
  foundation_details: foundationDetails,
  project_state: projectState ? {
    path: projectState.path,
    valid: projectState.valid,
    errors: projectState.errors,
    workflow: projectState.state?.workflow ?? null,
    phase: projectState.state?.phase ?? null,
    status: projectState.state?.status ?? null,
    gate: projectState.state?.gate ?? null,
  } : null,
  active_changes: activeChanges.map((entry) => ({
    change_id: entry.change_id,
    path: entry.path,
    phase: entry.state.phase,
    status: entry.state.status,
    gate: entry.state.gate,
  })),
  next_action: nextAction,
  errors,
}, null, 2));
process.exit(ok ? 0 : 1);
