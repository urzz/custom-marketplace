import { existsSync, readFileSync, readdirSync } from 'node:fs';
import path from 'node:path';
import { validateStateObject } from './validate-state.mjs';

const cwd = process.cwd();

function argValue(name) {
  const index = process.argv.indexOf(name);
  if (index === -1) return null;
  return process.argv[index + 1] ?? null;
}

const requestedSkill = argValue('--requested-skill');

function relativePath(filePath) {
  return path.relative(cwd, filePath).replace(/\\/g, '/');
}

function readStateIfPresent(filePath) {
  if (!existsSync(filePath)) {
    return null;
  }

  try {
    const parsed = JSON.parse(readFileSync(filePath, 'utf8'));
    const validation = validateStateObject(parsed);
    return {
      path: relativePath(filePath),
      valid: validation.ok,
      errors: validation.errors,
      state: parsed,
    };
  } catch (error) {
    return {
      path: relativePath(filePath),
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

function isIgnoredRootEntry(name) {
  return name === '.git'
    || name === '.claude'
    || name === '.nuclio'
    || name === '.dev-docs'
    || name === 'node_modules'
    || name === '.DS_Store';
}

function rootEntries() {
  try {
    return readdirSync(cwd, { withFileTypes: true }).filter((entry) => !isIgnoredRootEntry(entry.name));
  } catch {
    return [];
  }
}

function hasAppLikeFiles(entries) {
  const appLikeNames = new Set([
    'package.json',
    'pyproject.toml',
    'Cargo.toml',
    'go.mod',
    'pom.xml',
    'build.gradle',
    'Makefile',
    'Dockerfile',
    'docker-compose.yml',
  ]);
  const appLikeDirs = new Set(['src', 'app', 'lib', 'server', 'client', 'web', 'cmd', 'internal']);
  return entries.some((entry) => appLikeNames.has(entry.name) || (entry.isDirectory() && appLikeDirs.has(entry.name)));
}

function repositoryStage({ hasNuclioDir, hasDevDocs, projectState }) {
  if (hasNuclioDir && hasDevDocs && projectState?.valid) {
    return 'existing_app_with_foundation';
  }

  const entries = rootEntries();
  if (entries.length === 0) {
    return 'empty_repo';
  }

  if (hasAppLikeFiles(entries)) {
    return 'existing_app_without_foundation';
  }

  return 'skeleton_repo';
}

function summarizeProjectState(projectState) {
  return projectState ? {
    path: projectState.path,
    valid: projectState.valid,
    errors: projectState.errors,
    workflow: projectState.state?.workflow ?? null,
    phase: projectState.state?.phase ?? null,
    status: projectState.state?.status ?? null,
    gate: projectState.state?.gate ?? null,
  } : null;
}

const hasNuclioDir = existsSync(path.join(cwd, '.nuclio'));
const hasDevDocs = existsSync(path.join(cwd, '.dev-docs/index.md'));
const foundationDetails = {
  nuclio_dir: hasNuclioDir,
  dev_docs_index: hasDevDocs,
};
const foundation = hasNuclioDir && hasDevDocs ? 'ready' : 'missing';
const projectState = readStateIfPresent(path.join(cwd, '.nuclio/project/init-state.json'));
const changes = listChangeStates();
const activeChanges = changes.filter((entry) => entry.valid && entry.state?.workflow === 'change' && entry.state.status !== 'done' && entry.state.status !== 'failed');
const invalidStates = [projectState, ...changes].filter((entry) => entry && !entry.valid);
const errors = [];

let ok = true;
let recommendation = 'resume';

if (invalidStates.length) {
  ok = false;
  recommendation = requestedSkill === 'resume' || projectState ? 'resume' : 'project-init';
  errors.push(...invalidStates.map((entry) => ({ path: entry.path, errors: entry.errors })));
} else if (activeChanges.length > 1) {
  ok = false;
  recommendation = 'resolve_multiple_active_changes';
  errors.push({ message: 'multiple active changes found', change_ids: activeChanges.map((entry) => entry.change_id) });
} else if (requestedSkill === 'resume') {
  recommendation = 'resume';
} else if (!projectState || foundation === 'missing') {
  recommendation = 'project-init';
} else if (activeChanges.length === 1) {
  recommendation = 'continue_current_change';
}

const repository_stage = repositoryStage({ hasNuclioDir, hasDevDocs, projectState });
const project_init_state = summarizeProjectState(projectState);
const active_changes = activeChanges.map((entry) => ({
  change_id: entry.change_id,
  path: entry.path,
  phase: entry.state.phase,
  status: entry.state.status,
  gate: entry.state.gate,
}));

console.log(JSON.stringify({
  ok,
  requested_skill: requestedSkill,
  repository_stage,
  has_nuclio_dir: hasNuclioDir,
  has_dev_docs: hasDevDocs,
  project_init_state,
  active_changes,
  recommendation,
  foundation,
  foundation_details: foundationDetails,
  project_state: project_init_state,
  next_action: recommendation,
  errors,
}, null, 2));
process.exit(ok ? 0 : 1);
