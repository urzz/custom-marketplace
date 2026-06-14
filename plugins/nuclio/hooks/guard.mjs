import { existsSync, readFileSync, readdirSync } from 'node:fs';
import path from 'node:path';

const input = process.env.CLAUDE_TOOL_INPUT || '';
const tool = process.env.CLAUDE_TOOL_NAME || '';
const cwd = process.cwd();

const dangerousBashPatterns = [
  /\bgit\s+push\b/i,
  /\bkubectl\b/i,
  /\bterraform\s+apply\b/i,
  /\brm\s+-rf\b/i,
  /drop database/i,
];

function pathTargetsDevDocs(targetPath) {
  const normalized = String(targetPath).replace(/\\/g, '/');
  return /(^|\/)\.dev-docs(\/|$)/.test(normalized);
}

function collectPathLikeValues(value, paths = []) {
  if (!value || typeof value !== 'object') {
    return paths;
  }

  if (Array.isArray(value)) {
    for (const item of value) {
      collectPathLikeValues(item, paths);
    }
    return paths;
  }

  for (const [key, nestedValue] of Object.entries(value)) {
    if (typeof nestedValue === 'string' && (key === 'file_path' || key === 'path' || key.endsWith('_path'))) {
      paths.push(nestedValue);
      continue;
    }

    collectPathLikeValues(nestedValue, paths);
  }

  return paths;
}

function touchesDevDocsForWriteLikeTool(rawInput) {
  try {
    const parsed = JSON.parse(rawInput);
    const targetPaths = collectPathLikeValues(parsed);
    return targetPaths.some(pathTargetsDevDocs);
  } catch {
    return null;
  }
}

function readJsonIfPresent(filePath) {
  if (!existsSync(filePath)) {
    return null;
  }

  try {
    const parsed = JSON.parse(readFileSync(filePath, 'utf8'));
    return parsed && typeof parsed === 'object' ? parsed : null;
  } catch {
    return null;
  }
}

function approvalFieldIsApproved(value) {
  if (typeof value === 'string') {
    return value.toLowerCase() === 'approved';
  }

  if (value && typeof value === 'object' && typeof value.status === 'string') {
    return value.status.toLowerCase() === 'approved';
  }

  return false;
}

function hasProjectDevDocsApproval(rootDir) {
  const state = readJsonIfPresent(path.join(rootDir, '.nuclio/project/init-state.json'));
  return approvalFieldIsApproved(state?.initialDevDocsApproval);
}

function hasChangeMemoryApproval(rootDir) {
  const changesDir = path.join(rootDir, '.nuclio/changes');

  if (!existsSync(changesDir)) {
    return false;
  }

  for (const entry of readdirSync(changesDir, { withFileTypes: true })) {
    if (!entry.isDirectory()) {
      continue;
    }

    const state = readJsonIfPresent(path.join(changesDir, entry.name, 'state.json'));
    if (approvalFieldIsApproved(state?.memoryApproval)) {
      return true;
    }
  }

  return false;
}

function hasExplicitNuclioApproval(rootDir) {
  return hasProjectDevDocsApproval(rootDir) || hasChangeMemoryApproval(rootDir);
}

const rawMentionsDevDocs = /(^|[^\w.-])\.dev-docs\//.test(input) || input.includes('.dev-docs/');
const writeLikeDevDocsCheck = tool === 'Write' || tool === 'Edit'
  ? touchesDevDocsForWriteLikeTool(input)
  : null;
const touchesDevDocs = writeLikeDevDocsCheck ?? rawMentionsDevDocs;
const isDangerousBash = tool === 'Bash' && dangerousBashPatterns.some((pattern) => pattern.test(input));

if (touchesDevDocs && !hasExplicitNuclioApproval(cwd)) {
  console.error('Blocked: writing .dev-docs requires explicit Nucl.io approval state.');
  process.exit(2);
}

if (isDangerousBash) {
  console.error('Blocked: dangerous bash command requires human approval.');
  process.exit(2);
}

console.log(`guard ok: ${cwd}`);
