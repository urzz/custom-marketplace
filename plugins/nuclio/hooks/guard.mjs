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

const conservativeDangerousBashPatterns = [
  /(^|[^\w.-])rm\s+-(?=[^\s'"`;&|]*[rR])(?=[^\s'"`;&|]*f)[^\s'"`;&|]*/i,
  /(^|[^\w.-])git\s+(?:(?:-[A-Za-z]|--(?:git-dir|work-tree|namespace))\s+[^\s'"`;&|]+\s+|--(?:git-dir|work-tree|namespace)=[^\s'"`;&|]+\s+|-[^\s'"`;&|]+\s+)*push\b/i,
];

const writeLikeTools = new Set(['Write', 'Edit', 'MultiEdit']);

function shellTokens(command) {
  const tokens = [];
  let current = '';
  let quote = null;
  let escaped = false;

  function pushCurrent() {
    if (current) {
      tokens.push(current);
      current = '';
    }
  }

  for (const char of String(command || '')) {
    if (escaped) {
      current += char;
      escaped = false;
      continue;
    }

    if (char === '\\') {
      escaped = true;
      continue;
    }

    if (quote) {
      if (char === quote) {
        quote = null;
      } else {
        current += char;
      }
      continue;
    }

    if (char === '\'' || char === '"') {
      quote = char;
      continue;
    }

    if (/\s/.test(char) || char === ';' || char === '&' || char === '|') {
      pushCurrent();
      continue;
    }

    current += char;
  }

  pushCurrent();

  return tokens;
}

function rmCommandHasForceRecursive(tokens, startIndex) {
  let hasForce = false;
  let hasRecursive = false;

  for (let index = startIndex + 1; index < tokens.length; index += 1) {
    const token = tokens[index];
    if (token === '--') {
      break;
    }

    if (!token.startsWith('-') || token === '-') {
      break;
    }

    if (token.includes('f')) {
      hasForce = true;
    }

    if (/[rR]/.test(token)) {
      hasRecursive = true;
    }

    if (hasForce && hasRecursive) {
      return true;
    }
  }

  return false;
}

function gitOptionConsumesNext(token) {
  return token === '-C'
    || token === '-c'
    || token === '--git-dir'
    || token === '--work-tree'
    || token === '--namespace';
}

function gitCommandIsPush(tokens, startIndex) {
  for (let index = startIndex + 1; index < tokens.length; index += 1) {
    const token = tokens[index];
    if (token === '--') {
      continue;
    }

    if (gitOptionConsumesNext(token)) {
      index += 1;
      continue;
    }

    if (token.startsWith('--git-dir=') || token.startsWith('--work-tree=') || token.startsWith('--namespace=')) {
      continue;
    }

    if (token.startsWith('-')) {
      continue;
    }

    return token === 'push';
  }

  return false;
}

function hasDangerousBashCommand(command) {
  const commandString = String(command || '');
  if (conservativeDangerousBashPatterns.some((pattern) => pattern.test(commandString))) {
    return true;
  }

  const tokens = shellTokens(commandString);
  for (let index = 0; index < tokens.length; index += 1) {
    const token = tokens[index];
    if (token === 'rm' && rmCommandHasForceRecursive(tokens, index)) {
      return true;
    }

    if (token === 'git' && gitCommandIsPush(tokens, index)) {
      return true;
    }
  }

  return false;
}

function bashInputsToCheck(rawInput) {
  try {
    const parsed = JSON.parse(rawInput);
    if (parsed && typeof parsed === 'object' && !Array.isArray(parsed) && typeof parsed.command === 'string') {
      return [parsed.command, rawInput];
    }
  } catch {
    // Fall back to checking raw input below.
  }

  return [rawInput];
}

function bashCommandsForWriteTargetExtraction(rawInput) {
  try {
    const parsed = JSON.parse(rawInput);
    if (parsed && typeof parsed === 'object' && !Array.isArray(parsed) && typeof parsed.command === 'string') {
      return [parsed.command];
    }
  } catch {
    // Fall back to checking raw input below.
  }

  return [rawInput];
}

function normalizeSlashes(value) {
  return String(value || '')
    .replace(/\\/g, '/')
    .replace(/\/+/g, '/');
}

function stripTrailingSlash(value) {
  if (value === '/') {
    return value;
  }

  return value.replace(/\/+$/g, '');
}

function isWindowsAbsolutePath(value) {
  return /^[A-Za-z]:\//.test(value);
}

function normalizeRelativePath(value) {
  const normalizedSlashes = normalizeSlashes(value);
  if (!normalizedSlashes) {
    return '';
  }

  const normalized = path.posix.normalize(normalizedSlashes).replace(/^\.\//, '');
  return normalized || '.';
}

function normalizePath(value) {
  const normalized = normalizeSlashes(value);
  if (!normalized) {
    return '';
  }

  const normalizedCwd = stripTrailingSlash(path.posix.normalize(normalizeSlashes(cwd)));

  if (normalized.startsWith('/')) {
    return normalizeRelativePath(path.posix.relative(normalizedCwd, normalized));
  }

  if (isWindowsAbsolutePath(normalized)) {
    if (isWindowsAbsolutePath(normalizedCwd)) {
      const relative = normalizeSlashes(path.win32.relative(normalizedCwd, normalized));
      if (isWindowsAbsolutePath(relative)) {
        return normalizeRelativePath(`../${relative}`);
      }

      return normalizeRelativePath(relative);
    }

    return normalizeRelativePath(`../${normalized}`);
  }

  return normalizeRelativePath(normalized);
}

function isOutsideWorkspacePath(normalizedPath) {
  return normalizedPath === '..' || normalizedPath.startsWith('../');
}

function pathTargetsDevDocs(targetPath) {
  const normalized = normalizePath(targetPath);
  return /(^|\/)\.dev-docs(\/|$)/.test(normalized);
}

function pathTargetsNuclioArtifacts(targetPath) {
  const normalized = normalizePath(targetPath);
  return /(^|\/)\.nuclio(\/|$)/.test(normalized);
}

function isApplicationPath(targetPath) {
  return !pathTargetsDevDocs(targetPath) && !pathTargetsNuclioArtifacts(targetPath);
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

function parseToolInput(rawInput) {
  let parsed;
  try {
    parsed = JSON.parse(rawInput);
  } catch {
    return { ok: false, reason: 'Blocked: write-like tool input must be valid JSON.' };
  }

  if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
    return { ok: false, reason: 'Blocked: write-like tool input must be a JSON object.' };
  }

  return { ok: true, value: parsed };
}

function targetPathsForWriteLikeTool(rawInput) {
  const parsed = parseToolInput(rawInput);
  if (!parsed.ok) {
    return parsed;
  }

  const paths = collectPathLikeValues(parsed.value).map(normalizePath).filter(Boolean);
  if (!paths.length) {
    return { ok: false, reason: 'Blocked: write-like tool input must include a target path field.' };
  }

  const outsidePath = paths.find(isOutsideWorkspacePath);
  if (outsidePath) {
    return { ok: false, reason: `Blocked: ${outsidePath} is outside workspace/repository.` };
  }

  return {
    ok: true,
    paths,
  };
}

function isShellWriteRedirectionToken(token) {
  return /^(?:\d*)>>?[^&]*/.test(token) && !/^(?:\d*)>>?&/.test(token);
}

function redirectionTargetFromToken(token) {
  const match = String(token || '').match(/^(?:\d*)>>?(.+)$/);
  return match ? match[1] : '';
}

function cleanExtractedShellPath(value) {
  return String(value || '')
    .trim()
    .replace(/^["']|["']$/g, '')
    .replace(/[;,]+$/g, '');
}

function collectShellRedirectionTargets(command, paths) {
  const tokens = shellTokens(command);
  for (let index = 0; index < tokens.length; index += 1) {
    const token = tokens[index];
    if (token === '>' || token === '>>') {
      const target = cleanExtractedShellPath(tokens[index + 1]);
      if (target) {
        paths.push(target);
      }
      index += 1;
      continue;
    }

    if (isShellWriteRedirectionToken(token)) {
      const target = cleanExtractedShellPath(redirectionTargetFromToken(token));
      if (target) {
        paths.push(target);
      }
    }
  }
}

function collectTeeTargets(command, paths) {
  const tokens = shellTokens(command);
  for (let index = 0; index < tokens.length; index += 1) {
    if (path.basename(tokens[index]) !== 'tee') {
      continue;
    }

    for (let targetIndex = index + 1; targetIndex < tokens.length; targetIndex += 1) {
      const token = tokens[targetIndex];
      if (token === '--') {
        continue;
      }

      if (token === '-a' || token === '--append' || token === '-i' || token === '--ignore-interrupts') {
        continue;
      }

      if (token.startsWith('-')) {
        continue;
      }

      const target = cleanExtractedShellPath(token);
      if (target) {
        paths.push(target);
      }
      break;
    }
  }
}

function collectRegexWriteTargets(command, paths) {
  const patterns = [
    /\bopen\(\s*(["'`])([^"'`]+)\1\s*,\s*(["'`])[^"'`]*[wax+][^"'`]*\3/g,
    /\b(?:pathlib\.)?Path\(\s*(["'`])([^"'`]+)\1\s*\)\.write_text\s*\(/g,
    /\b(?:fs\.)?(?:writeFileSync|appendFileSync)\s*\(\s*(["'`])([^"'`]+)\1/g,
  ];

  for (const pattern of patterns) {
    let match;
    while ((match = pattern.exec(command)) !== null) {
      const target = cleanExtractedShellPath(match[2]);
      if (target) {
        paths.push(target);
      }
    }
  }
}

function extractBashWriteTargetPaths(rawInput) {
  const paths = [];
  for (const command of bashCommandsForWriteTargetExtraction(rawInput)) {
    collectShellRedirectionTargets(command, paths);
    collectTeeTargets(command, paths);
    collectRegexWriteTargets(command, paths);
  }

  return [...new Set(paths.map(normalizePath).filter(Boolean))];
}

function targetPathsForBashWriteTargets(rawInput) {
  const paths = extractBashWriteTargetPaths(rawInput);
  const outsidePath = paths.find(isOutsideWorkspacePath);
  if (outsidePath) {
    return { ok: false, reason: `Blocked: ${outsidePath} is outside workspace/repository.` };
  }

  return { ok: true, paths };
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

function canonicalApproval(state, key) {
  if (!state || typeof state !== 'object' || !state.approved || typeof state.approved !== 'object') {
    return undefined;
  }

  if (typeof state.approved[key] === 'boolean') {
    return state.approved[key];
  }

  return undefined;
}

function approvalAllows(state, canonicalKey, legacyKey) {
  const canonical = canonicalApproval(state, canonicalKey);
  if (canonical === true) {
    return true;
  }

  if (canonical === false) {
    return false;
  }

  return approvalFieldIsApproved(state?.[legacyKey]);
}

function readProjectState(rootDir) {
  return readJsonIfPresent(path.join(rootDir, '.nuclio/project/init-state.json'));
}

function listChangeStates(rootDir) {
  const changesDir = path.join(rootDir, '.nuclio/changes');
  if (!existsSync(changesDir)) {
    return [];
  }

  const states = [];
  for (const entry of readdirSync(changesDir, { withFileTypes: true })) {
    if (!entry.isDirectory()) {
      continue;
    }

    const statePath = path.join(changesDir, entry.name, 'state.json');
    const state = readJsonIfPresent(statePath);
    if (state) {
      states.push({ changeId: entry.name, state, statePath, changeDir: path.dirname(statePath) });
    }
  }

  return states.sort((a, b) => String(b.state.updated_at || '').localeCompare(String(a.state.updated_at || '')));
}

function activeChanges(rootDir) {
  return listChangeStates(rootDir).filter(({ state }) => (
    state.workflow === 'change' && state.status !== 'done' && state.status !== 'failed'
  ));
}

function hasProjectDevDocsApproval(rootDir) {
  const state = readProjectState(rootDir);
  return state?.workflow === 'project_initialization'
    && state.status !== 'failed'
    && approvalAllows(state, 'initial_dev_docs', 'initialDevDocsApproval');
}

function hasChangeMemoryApproval(rootDir) {
  return listChangeStates(rootDir).some(({ state }) => (
    state.workflow === 'change'
    && state.status !== 'failed'
    && state.phase === 'close'
    && approvalAllows(state, 'memory', 'memoryApproval')
  ));
}

function hasExplicitNuclioDevDocsApproval(rootDir) {
  return hasProjectDevDocsApproval(rootDir) || hasChangeMemoryApproval(rootDir);
}

function globSegments(pattern) {
  return normalizePath(pattern).split('/').filter(Boolean);
}

function matchSegment(targetSegment, patternSegment) {
  let targetIndex = 0;
  let patternIndex = 0;
  let starIndex = -1;
  let matchIndex = 0;

  while (targetIndex < targetSegment.length) {
    if (patternIndex < patternSegment.length && patternSegment[patternIndex] === '*') {
      starIndex = patternIndex;
      matchIndex = targetIndex;
      patternIndex += 1;
    } else if (patternIndex < patternSegment.length && patternSegment[patternIndex] === targetSegment[targetIndex]) {
      patternIndex += 1;
      targetIndex += 1;
    } else if (starIndex !== -1) {
      patternIndex = starIndex + 1;
      matchIndex += 1;
      targetIndex = matchIndex;
    } else {
      return false;
    }
  }

  while (patternIndex < patternSegment.length && patternSegment[patternIndex] === '*') {
    patternIndex += 1;
  }

  return patternIndex === patternSegment.length;
}

function matchGlobSegments(targetSegments, patternSegments, targetIndex = 0, patternIndex = 0) {
  if (patternIndex === patternSegments.length) {
    return targetIndex === targetSegments.length;
  }

  const patternSegment = patternSegments[patternIndex];
  if (patternSegment === '**') {
    for (let nextTargetIndex = targetIndex; nextTargetIndex <= targetSegments.length; nextTargetIndex += 1) {
      if (matchGlobSegments(targetSegments, patternSegments, nextTargetIndex, patternIndex + 1)) {
        return true;
      }
    }

    return false;
  }

  if (targetIndex >= targetSegments.length) {
    return false;
  }

  return matchSegment(targetSegments[targetIndex], patternSegment)
    && matchGlobSegments(targetSegments, patternSegments, targetIndex + 1, patternIndex + 1);
}

function matchesPattern(targetPath, pattern) {
  const normalizedTarget = normalizePath(targetPath);
  const normalizedPattern = normalizePath(pattern);
  if (!normalizedPattern) {
    return false;
  }

  return matchGlobSegments(globSegments(normalizedTarget), globSegments(normalizedPattern));
}

function stripYamlComment(value) {
  let quote = null;
  for (let index = 0; index < value.length; index += 1) {
    const char = value[index];
    if (quote) {
      if (char === quote) {
        quote = null;
      }
      continue;
    }

    if (char === '\'' || char === '"') {
      quote = char;
      continue;
    }

    if (char === '#' && (index === 0 || /\s/.test(value[index - 1]))) {
      return value.slice(0, index).trimEnd();
    }
  }

  return value.trimEnd();
}

function unquoteYamlScalar(value) {
  const trimmed = stripYamlComment(value).trim();
  if (trimmed.length >= 2) {
    const first = trimmed[0];
    const last = trimmed[trimmed.length - 1];
    if ((first === '\'' && last === '\'') || (first === '"' && last === '"')) {
      return trimmed.slice(1, -1);
    }
  }

  return trimmed;
}

function parseInlineYamlList(value) {
  const trimmed = stripYamlComment(value).trim();
  if (!trimmed.startsWith('[') || !trimmed.endsWith(']')) {
    return null;
  }

  const inner = trimmed.slice(1, -1).trim();
  if (!inner) {
    return [];
  }

  const values = [];
  let quote = null;
  let current = '';
  for (let index = 0; index < inner.length; index += 1) {
    const char = inner[index];
    if (quote) {
      if (char === quote) {
        quote = null;
      }
      current += char;
      continue;
    }

    if (char === '\'' || char === '"') {
      quote = char;
      current += char;
      continue;
    }

    if (char === ',') {
      values.push(unquoteYamlScalar(current));
      current = '';
      continue;
    }

    current += char;
  }

  if (quote) {
    return null;
  }

  values.push(unquoteYamlScalar(current));
  return values.filter((item) => item.length > 0);
}

function extractYamlList(lines, startIndex, baseIndent) {
  const values = [];
  for (let index = startIndex + 1; index < lines.length; index += 1) {
    const line = lines[index];
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith('#')) {
      continue;
    }

    const indent = line.length - line.trimStart().length;
    if (indent <= baseIndent) {
      break;
    }

    const itemMatch = trimmed.match(/^-\s+(.+)$/);
    if (itemMatch) {
      values.push(unquoteYamlScalar(itemMatch[1]));
    }
  }

  return values;
}

function isBlockScalarStart(trimmed) {
  return /^([A-Za-z_][\w-]*|-[ \t]+[A-Za-z_][\w-]*):\s*[|>][+-]?(?:\s+#.*)?$/.test(trimmed);
}

function skipBlockScalar(lines, startIndex, baseIndent) {
  let index = startIndex + 1;
  for (; index < lines.length; index += 1) {
    const line = lines[index];
    const trimmed = line.trim();
    if (!trimmed) {
      continue;
    }

    const indent = line.length - line.trimStart().length;
    if (indent <= baseIndent) {
      break;
    }
  }

  return index - 1;
}

function parsePlanTasks(filePath, allowedSection) {
  if (!existsSync(filePath)) {
    return [];
  }

  const lines = readFileSync(filePath, 'utf8').split(/\r?\n/);
  const tasks = [];
  let current = null;
  let currentSection = null;
  let currentSectionIndent = -1;

  for (let index = 0; index < lines.length; index += 1) {
    const line = lines[index];
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith('#')) {
      continue;
    }

    const indent = line.length - line.trimStart().length;
    if (isBlockScalarStart(trimmed)) {
      index = skipBlockScalar(lines, index, indent);
      continue;
    }

    const content = stripYamlComment(trimmed).trim();
    const topLevelKeyMatch = content.match(/^([A-Za-z_][\w-]*):(?:\s*)?$/)
      || content.match(/^([A-Za-z_][\w-]*):\s+.+$/);
    if (topLevelKeyMatch && indent === 0) {
      const sectionName = topLevelKeyMatch[1];
      currentSection = sectionName === allowedSection ? sectionName : null;
      currentSectionIndent = currentSection ? indent : -1;
      current = null;
      continue;
    }

    if (!currentSection || indent <= currentSectionIndent) {
      current = null;
      continue;
    }

    const idMatch = content.match(/^-\s+id:\s*(.+?)\s*$/);
    if (idMatch) {
      current = {
        id: unquoteYamlScalar(idMatch[1]),
        allowed_paths: [],
        forbidden_paths: [],
      };
      tasks.push(current);
      continue;
    }

    if (!current) {
      continue;
    }

    const allowedPathsMatch = content.match(/^allowed_paths:\s*(.*)$/);
    if (allowedPathsMatch) {
      const inlineList = parseInlineYamlList(allowedPathsMatch[1]);
      current.allowed_paths = inlineList ?? extractYamlList(lines, index, indent);
    }

    const forbiddenPathsMatch = content.match(/^forbidden_paths:\s*(.*)$/);
    if (forbiddenPathsMatch) {
      const inlineList = parseInlineYamlList(forbiddenPathsMatch[1]);
      current.forbidden_paths = inlineList ?? extractYamlList(lines, index, indent);
    }
  }

  return tasks;
}

function taskPathBoundaryAllows(targetPath, task, label) {
  const forbidden = task.forbidden_paths || [];
  const allowed = task.allowed_paths || [];

  if (forbidden.some((pattern) => matchesPattern(targetPath, pattern))) {
    return { ok: false, reason: `Blocked: ${targetPath} matches ${label} forbidden_paths.` };
  }

  if (!allowed.length) {
    return { ok: false, reason: `Blocked: ${label} allowed_paths is empty.` };
  }

  if (!allowed.some((pattern) => matchesPattern(targetPath, pattern))) {
    return { ok: false, reason: `Blocked: ${targetPath} is outside ${label} allowed_paths.` };
  }

  return { ok: true };
}

function currentTaskId(state) {
  if (typeof state.current_task === 'string') {
    return state.current_task;
  }

  if (state.current_task && typeof state.current_task.id === 'string') {
    return state.current_task.id;
  }

  return null;
}

function changePathBoundaryAllows(rootDir, change, targetPath) {
  const { state, changeDir } = change;

  if (state.phase !== 'build' || canonicalApproval(state, 'design') !== true) {
    return { ok: false, reason: 'Blocked: application writes require change phase build and approved.design === true.' };
  }

  const taskId = currentTaskId(state);
  if (!taskId) {
    return { ok: false, reason: 'Blocked: build writes require state.current_task.' };
  }

  const tasks = parsePlanTasks(path.join(changeDir, 'plan.yaml'), 'tasks');
  const task = tasks.find((candidate) => candidate.id === taskId);
  if (!task) {
    return { ok: false, reason: `Blocked: current_task ${taskId} was not found in plan.yaml.` };
  }

  return taskPathBoundaryAllows(targetPath, task, `task ${taskId}`);
}

function activeChangeBoundaryAllows(rootDir, targetPath) {
  const changes = activeChanges(rootDir);
  if (!changes.length) {
    return null;
  }

  if (changes.length > 1) {
    return { ok: false, reason: 'Blocked: application writes require exactly one active workflow: change.' };
  }

  return changePathBoundaryAllows(rootDir, changes[0], targetPath);
}

function projectScaffoldBoundaryAllows(rootDir, targetPath) {
  const state = readProjectState(rootDir);
  if (!state || state.workflow !== 'project_initialization' || state.status === 'failed') {
    return null;
  }

  if (canonicalApproval(state, 'scaffold') !== true) {
    return { ok: false, reason: 'Blocked: project scaffold writes require approved.scaffold === true.' };
  }

  const tasks = parsePlanTasks(path.join(rootDir, '.nuclio/project/scaffold-plan.yaml'), 'scaffold_tasks');
  if (!tasks.length) {
    return { ok: false, reason: 'Blocked: scaffold-plan.yaml contains no scaffold_tasks with allowed_paths.' };
  }

  for (const task of tasks) {
    const result = taskPathBoundaryAllows(targetPath, task, `scaffold task ${task.id}`);
    if (result.ok) {
      return result;
    }
  }

  return { ok: false, reason: `Blocked: ${targetPath} is outside scaffold allowed_paths or matches forbidden_paths.` };
}

function applicationWriteAllows(rootDir, targetPath) {
  const changeResult = activeChangeBoundaryAllows(rootDir, targetPath);
  if (changeResult) {
    return changeResult;
  }

  const projectResult = projectScaffoldBoundaryAllows(rootDir, targetPath);
  if (projectResult) {
    return projectResult;
  }

  return { ok: true };
}

let targetPathResult = { ok: true, paths: [] };
if (writeLikeTools.has(tool)) {
  targetPathResult = targetPathsForWriteLikeTool(input);
} else if (tool === 'Bash') {
  targetPathResult = targetPathsForBashWriteTargets(input);
}

if (!targetPathResult.ok) {
  console.error(targetPathResult.reason);
  process.exit(2);
}

const targetPaths = targetPathResult.paths;
const rawMentionsDevDocs = /(^|[^\w.-])\.dev-docs\//.test(input) || input.includes('.dev-docs/');
const useRawDevDocsFallback = !targetPaths.length;
const touchesDevDocs = targetPaths.some(pathTargetsDevDocs) || (useRawDevDocsFallback && rawMentionsDevDocs);
const bashInputs = tool === 'Bash' ? bashInputsToCheck(input) : [];
const isDangerousBash = tool === 'Bash'
  && bashInputs.some((bashInput) => (
    dangerousBashPatterns.some((pattern) => pattern.test(bashInput)) || hasDangerousBashCommand(bashInput)
  ));

if (touchesDevDocs && !hasExplicitNuclioDevDocsApproval(cwd)) {
  console.error('Blocked: writing .dev-docs requires canonical Nucl.io approval state.');
  process.exit(2);
}

if (writeLikeTools.has(tool) || tool === 'Bash') {
  for (const targetPath of targetPaths.filter(isApplicationPath)) {
    const result = applicationWriteAllows(cwd, targetPath);
    if (!result.ok) {
      console.error(result.reason);
      process.exit(2);
    }
  }
}

if (isDangerousBash) {
  console.error('Blocked: dangerous bash command requires human approval.');
  process.exit(2);
}

console.log(`guard ok: ${cwd}`);
