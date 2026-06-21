import { appendFileSync, existsSync, mkdirSync, readFileSync, readdirSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const input = process.env.CLAUDE_TOOL_INPUT || '';
const tool = process.env.CLAUDE_TOOL_NAME || '';
const cwd = process.cwd();
const guardDir = path.dirname(fileURLToPath(import.meta.url));
const pluginRootFromGuard = path.resolve(guardDir, '..');

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

function commandSegments(command) {
  return String(command || '')
    .split(/(?:&&|\|\||;|\n)/g)
    .map((segment) => segment.trim())
    .filter(Boolean);
}

function rmCommandHasForceRecursive(tokens, startIndex) {
  let hasForce = false;
  let hasRecursive = false;

  for (let index = startIndex + 1; index < tokens.length; index += 1) {
    const token = tokens[index];
    if (token === '--') break;
    if (!token.startsWith('-') || token === '-') break;
    if (token.includes('f')) hasForce = true;
    if (/[rR]/.test(token)) hasRecursive = true;
    if (hasForce && hasRecursive) return true;
  }

  return false;
}

function gitOptionConsumesNext(token) {
  return token === '-C' || token === '-c' || token === '--git-dir' || token === '--work-tree' || token === '--namespace';
}

function gitCommandIsPush(tokens, startIndex) {
  for (let index = startIndex + 1; index < tokens.length; index += 1) {
    const token = tokens[index];
    if (token === '--') continue;
    if (gitOptionConsumesNext(token)) {
      index += 1;
      continue;
    }
    if (token.startsWith('--git-dir=') || token.startsWith('--work-tree=') || token.startsWith('--namespace=')) continue;
    if (token.startsWith('-')) continue;
    return token === 'push';
  }

  return false;
}

function hasDangerousBashCommand(command) {
  const commandString = String(command || '');
  if (conservativeDangerousBashPatterns.some((pattern) => pattern.test(commandString))) return true;

  const tokens = shellTokens(commandString);
  for (let index = 0; index < tokens.length; index += 1) {
    const token = tokens[index];
    if (token === 'rm' && rmCommandHasForceRecursive(tokens, index)) return true;
    if (token === 'git' && gitCommandIsPush(tokens, index)) return true;
  }

  return false;
}

function parseBashInput(rawInput) {
  try {
    const parsed = JSON.parse(rawInput);
    if (parsed && typeof parsed === 'object' && !Array.isArray(parsed) && typeof parsed.command === 'string') {
      return parsed.command;
    }
  } catch {
    // Fall back to raw input.
  }

  return rawInput;
}

function bashInputsToCheck(rawInput) {
  const command = parseBashInput(rawInput);
  return command === rawInput ? [rawInput] : [command, rawInput];
}

function bashCommandsForWriteTargetExtraction(rawInput) {
  return [parseBashInput(rawInput)];
}

function normalizeSlashes(value) {
  return String(value || '').replace(/\\/g, '/').replace(/\/+/g, '/');
}

function stripTrailingSlash(value) {
  return value === '/' ? value : value.replace(/\/+$/g, '');
}

function isWindowsAbsolutePath(value) {
  return /^[A-Za-z]:\//.test(value);
}

function normalizeRelativePath(value) {
  const normalizedSlashes = normalizeSlashes(value);
  if (!normalizedSlashes) return '';
  const normalized = path.posix.normalize(normalizedSlashes).replace(/^\.\//, '');
  return normalized || '.';
}

function normalizePath(value) {
  const normalized = normalizeSlashes(value);
  if (!normalized) return '';
  const normalizedCwd = stripTrailingSlash(path.posix.normalize(normalizeSlashes(cwd)));

  if (normalized.startsWith('/')) {
    return normalizeRelativePath(path.posix.relative(normalizedCwd, normalized));
  }

  if (isWindowsAbsolutePath(normalized)) {
    if (isWindowsAbsolutePath(normalizedCwd)) {
      const relative = normalizeSlashes(path.win32.relative(normalizedCwd, normalized));
      if (isWindowsAbsolutePath(relative)) return normalizeRelativePath(`../${relative}`);
      return normalizeRelativePath(relative);
    }
    return normalizeRelativePath(`../${normalized}`);
  }

  return normalizeRelativePath(normalized);
}

function isOutsideWorkspacePath(normalizedPath) {
  return normalizedPath === '..' || normalizedPath.startsWith('../');
}

function isSafeStatePath(targetPath) {
  const normalized = normalizePath(targetPath);
  if (isOutsideWorkspacePath(normalized)) return false;
  return normalized === '.nuclio/project/init-state.json'
    || /^\.nuclio\/changes\/[^/]+\/state\.json$/.test(normalized);
}

function isSafeEventsPath(targetPath) {
  const normalized = normalizePath(targetPath);
  if (isOutsideWorkspacePath(normalized)) return false;
  return normalized === '.nuclio/project/events.jsonl'
    || /^\.nuclio\/changes\/[^/]+\/events\.jsonl$/.test(normalized);
}

function hasOwn(value, key) {
  return Object.prototype.hasOwnProperty.call(value, key);
}

function isPlainObject(value) {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value);
}

function isSafeRelativePath(value) {
  const normalized = normalizeRelativePath(value);
  return Boolean(normalized) && normalized !== '..' && !normalized.startsWith('../') && !path.posix.isAbsolute(normalizeSlashes(value));
}

function validTargetPathScope(scope) {
  if (scope === undefined) return true;
  if (!isPlainObject(scope) || !Array.isArray(scope.target_paths)) return false;
  return scope.target_paths.every((targetPath) => typeof targetPath === 'string' && isSafeRelativePath(targetPath));
}

function hasNullableEnum(state, key, allowed) {
  return hasOwn(state, key) && (state[key] === null || allowed.includes(state[key]));
}

function hasNullableString(state, key) {
  return hasOwn(state, key) && (state[key] === null || typeof state[key] === 'string');
}

function hasOptionalString(state, key) {
  return !hasOwn(state, key) || state[key] === null || typeof state[key] === 'string';
}

function hasOptionalEnum(state, key, allowed) {
  return !hasOwn(state, key) || state[key] === null || allowed.includes(state[key]);
}

function hasBooleanApproval(state, key) {
  return isPlainObject(state.approved) && typeof state.approved[key] === 'boolean';
}

function hasValidRiskApprovals(state) {
  if (!hasOwn(state, 'risk_approvals')) return true;
  if (!Array.isArray(state.risk_approvals)) return false;
  return state.risk_approvals.every((approval) => isPlainObject(approval)
    && typeof approval.approved === 'boolean'
    && approval.scope === 'current_workflow'
    && typeof approval.command_pattern === 'string'
    && approval.command_pattern.trim().length > 0
    && (!hasOwn(approval, 'expires_at') || approval.expires_at === null || typeof approval.expires_at === 'string')
    && (!hasOwn(approval, 'reason') || approval.reason === null || typeof approval.reason === 'string'));
}

function hasValidCurrentTask(state) {
  if (!hasOwn(state, 'current_task')) return false;
  return state.current_task === null
    || typeof state.current_task === 'string'
    || (isPlainObject(state.current_task) && typeof state.current_task.id === 'string');
}

function hasValidProjectStateSchema(state) {
  return state.workflow === 'project_initialization'
    && PROJECT_PHASES.includes(state.phase)
    && PROJECT_STATUSES.includes(state.status)
    && hasNullableEnum(state, 'gate', PROJECT_GATES)
    && hasBooleanApproval(state, 'foundation')
    && hasBooleanApproval(state, 'architecture')
    && hasBooleanApproval(state, 'scaffold')
    && hasBooleanApproval(state, 'initial_dev_docs')
    && validTargetPathScope(state.approved?.initial_dev_docs_scope)
    && hasNullableString(state, 'blocking_reason')
    && hasOptionalString(state, 'project_id')
    && hasOptionalEnum(state, 'repository_stage', REPOSITORY_STAGES);
}

function hasValidChangeStateSchema(state) {
  return state.workflow === 'change'
    && CHANGE_PHASES.includes(state.phase)
    && CHANGE_STATUSES.includes(state.status)
    && hasNullableEnum(state, 'gate', CHANGE_GATES)
    && hasValidCurrentTask(state)
    && hasBooleanApproval(state, 'spec')
    && hasBooleanApproval(state, 'design')
    && hasBooleanApproval(state, 'final')
    && hasBooleanApproval(state, 'memory')
    && validTargetPathScope(state.approved?.memory_scope)
    && hasNullableString(state, 'blocking_reason')
    && hasOptionalString(state, 'project_id')
    && hasOptionalString(state, 'change_id')
    && hasOptionalEnum(state, 'change_kind', CHANGE_KINDS)
    && typeof state.build_iteration === 'number';
}

function hasValidStateSchema(state) {
  if (!isPlainObject(state)) return false;
  if (typeof state.updated_at !== 'string' || !state.updated_at) return false;
  if (!hasValidRiskApprovals(state)) return false;
  if (state.workflow === 'project_initialization') return hasValidProjectStateSchema(state);
  if (state.workflow === 'change') return hasValidChangeStateSchema(state);
  return false;
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
  if (!value || typeof value !== 'object') return paths;
  if (Array.isArray(value)) {
    for (const item of value) collectPathLikeValues(item, paths);
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
  if (!parsed.ok) return parsed;

  const paths = collectPathLikeValues(parsed.value).map(normalizePath).filter(Boolean);
  if (!paths.length) return { ok: false, reason: 'Blocked: write-like tool input must include a target path field.' };

  const outsidePath = paths.find(isOutsideWorkspacePath);
  if (outsidePath) return { ok: false, reason: `Blocked: ${outsidePath} is outside workspace/repository.` };

  return { ok: true, paths };
}

function isShellWriteRedirectionToken(token) {
  return /^(?:\d*)>>?[^&]*/.test(token) && !/^(?:\d*)>>?&/.test(token);
}

function redirectionTargetFromToken(token) {
  const match = String(token || '').match(/^(?:\d*)>>?(.+)$/);
  return match ? match[1] : '';
}

function cleanExtractedShellPath(value) {
  return String(value || '').trim().replace(/^["']|["']$/g, '').replace(/[;,]+$/g, '');
}

function collectShellRedirectionTargets(command, paths) {
  const tokens = shellTokens(command);
  for (let index = 0; index < tokens.length; index += 1) {
    const token = tokens[index];
    if (token === '>' || token === '>>') {
      const target = cleanExtractedShellPath(tokens[index + 1]);
      if (target) paths.push(target);
      index += 1;
      continue;
    }
    if (isShellWriteRedirectionToken(token)) {
      const target = cleanExtractedShellPath(redirectionTargetFromToken(token));
      if (target) paths.push(target);
    }
  }
}

function collectTeeTargets(command, paths) {
  const tokens = shellTokens(command);
  for (let index = 0; index < tokens.length; index += 1) {
    if (path.basename(tokens[index]) !== 'tee') continue;
    for (let targetIndex = index + 1; targetIndex < tokens.length; targetIndex += 1) {
      const token = tokens[targetIndex];
      if (token === '--') continue;
      if (token === '-a' || token === '--append' || token === '-i' || token === '--ignore-interrupts') continue;
      if (token.startsWith('-')) continue;
      const target = cleanExtractedShellPath(token);
      if (target) paths.push(target);
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
      if (target) paths.push(target);
    }
  }
}

function tokenLooksLikePath(token) {
  const cleaned = cleanExtractedShellPath(token);
  return Boolean(cleaned) && cleaned !== '--' && !/^[A-Z_][A-Z0-9_]*=/.test(cleaned);
}

function collectSedInPlaceTargets(tokens, paths) {
  const base = segmentBaseCommand(tokens);
  if (base !== 'sed' || !tokens.some((token) => token === '-i' || token.startsWith('-i'))) return;

  const operands = [];
  let scriptProvidedByOption = false;
  for (let index = 1; index < tokens.length; index += 1) {
    const token = tokens[index];
    if (token === '--') {
      operands.push(...tokens.slice(index + 1).filter(tokenLooksLikePath));
      break;
    }
    if (token === '-e' || token === '-f') {
      scriptProvidedByOption = true;
      index += 1;
      continue;
    }
    if (token.startsWith('-e') || token.startsWith('-f')) {
      scriptProvidedByOption = true;
      continue;
    }
    if (token === '-i' || token.startsWith('-i') || token.startsWith('-')) continue;
    operands.push(token);
  }

  const fileOperands = scriptProvidedByOption ? operands : operands.slice(1);
  for (const operand of fileOperands) {
    const target = cleanExtractedShellPath(operand);
    if (target) paths.push(target);
  }
}

function collectPerlInPlaceTargets(tokens, paths) {
  const base = segmentBaseCommand(tokens);
  if (base !== 'perl' || !tokens.some((token) => token === '-i' || token.startsWith('-i') || token === '-pi' || token.startsWith('-pi'))) return;

  for (let index = 1; index < tokens.length; index += 1) {
    const token = tokens[index];
    if (token === '--') {
      for (const operand of tokens.slice(index + 1)) {
        const target = cleanExtractedShellPath(operand);
        if (target) paths.push(target);
      }
      break;
    }
    if (token === '-e' || token === '-E' || token === '-M' || token === '-I') {
      index += 1;
      continue;
    }
    if (token.startsWith('-e') || token.startsWith('-E') || token.startsWith('-M') || token.startsWith('-I')) continue;
    if (token.startsWith('-')) continue;
    const target = cleanExtractedShellPath(token);
    if (target) paths.push(target);
  }
}

function nonOptionOperands(tokens, startIndex, optionsWithValues = new Set()) {
  const operands = [];
  for (let index = startIndex; index < tokens.length; index += 1) {
    const token = tokens[index];
    if (token === '--') {
      operands.push(...tokens.slice(index + 1).filter(tokenLooksLikePath));
      break;
    }
    if (optionsWithValues.has(token)) {
      index += 1;
      continue;
    }
    if ([...optionsWithValues].some((option) => token.startsWith(`${option}=`))) continue;
    if (token.startsWith('-') && token !== '-') continue;
    if (tokenLooksLikePath(token)) operands.push(token);
  }
  return operands;
}

function collectCopyMoveInstallTargets(tokens, paths) {
  const base = segmentBaseCommand(tokens);
  const commandIndex = tokens.findIndex((token) => path.basename(token) === base);
  if (!['cp', 'mv', 'install'].includes(base) || commandIndex === -1) return;

  const valueOptions = new Set(['-t', '--target-directory', '-T', '--no-target-directory', '-m', '--mode', '-o', '--owner', '-g', '--group', '-S', '--suffix', '-b', '--backup']);
  if (base === 'install' && tokens.includes('-d')) {
    for (const operand of nonOptionOperands(tokens, commandIndex + 1, valueOptions)) {
      const target = cleanExtractedShellPath(operand);
      if (target) paths.push(target);
    }
    return;
  }

  const targetDirectoryIndex = tokens.findIndex((token) => token === '-t' || token === '--target-directory');
  if (targetDirectoryIndex !== -1 && tokens[targetDirectoryIndex + 1]) {
    const target = cleanExtractedShellPath(tokens[targetDirectoryIndex + 1]);
    if (target) paths.push(target);
    return;
  }
  const targetDirectoryEquals = tokens.find((token) => token.startsWith('--target-directory='));
  if (targetDirectoryEquals) {
    const target = cleanExtractedShellPath(targetDirectoryEquals.slice('--target-directory='.length));
    if (target) paths.push(target);
    return;
  }

  const operands = nonOptionOperands(tokens, commandIndex + 1, valueOptions);
  const target = cleanExtractedShellPath(operands.at(-1));
  if (target) paths.push(target);
}

function collectTouchTargets(tokens, paths) {
  const base = segmentBaseCommand(tokens);
  const commandIndex = tokens.findIndex((token) => path.basename(token) === base);
  if (base !== 'touch' || commandIndex === -1) return;
  const operands = nonOptionOperands(tokens, commandIndex + 1, new Set(['-r', '--reference', '-t', '-d', '--date']));
  for (const operand of operands) {
    const target = cleanExtractedShellPath(operand);
    if (target) paths.push(target);
  }
}

function collectMkdirTargets(tokens, paths) {
  const base = segmentBaseCommand(tokens);
  const commandIndex = tokens.findIndex((token) => path.basename(token) === base);
  if (base !== 'mkdir' || commandIndex === -1) return;
  const operands = nonOptionOperands(tokens, commandIndex + 1, new Set(['-m', '--mode', '-Z', '--context']));
  for (const operand of operands) {
    const target = cleanExtractedShellPath(operand);
    if (target) paths.push(target);
  }
}

function collectKnownCommandWriteTargets(command, paths) {
  for (const segment of commandSegments(command)) {
    const tokens = shellTokens(segment);
    collectSedInPlaceTargets(tokens, paths);
    collectPerlInPlaceTargets(tokens, paths);
    collectCopyMoveInstallTargets(tokens, paths);
    collectTouchTargets(tokens, paths);
    collectMkdirTargets(tokens, paths);
  }
}

const CONTROLLED_NUCLIO_HELPERS = new Map([
  ['write-state.mjs', { kind: 'state', targetIsSafe: isSafeStatePath }],
  ['append-event.mjs', { kind: 'events', targetIsSafe: isSafeEventsPath }],
]);
const CONTROLLED_NUCLIO_READ_ONLY_HELPERS = new Set(['bootstrap-check.mjs']);

const PHASE_OWNED_ARTIFACTS = [
  { pattern: /^\.nuclio\/changes\/[^/]+\/spec\.md$/, ownerPhase: 'spec', approval: 'spec' },
  { pattern: /^\.nuclio\/changes\/[^/]+\/design\.md$/, ownerPhase: 'design', approval: 'design' },
  { pattern: /^\.nuclio\/changes\/[^/]+\/plan\.ya?ml$/, ownerPhase: 'design', approval: 'design' },
  { pattern: /^\.nuclio\/changes\/[^/]+\/close\.md$/, ownerPhase: 'close', approval: 'final' },
  { pattern: /^\.nuclio\/changes\/[^/]+\/memory\.patch\.md$/, ownerPhase: 'close', approval: 'memory' },
];

function normalizedAbsolutePath(value) {
  const normalized = normalizeSlashes(value).replace(/^['"]|['"]$/g, '');
  if (!normalized || (!normalized.startsWith('/') && !isWindowsAbsolutePath(normalized))) return '';
  return normalizeSlashes(path.resolve(normalized));
}

function nuclioHelperInfo(helperName) {
  const writeHelper = CONTROLLED_NUCLIO_HELPERS.get(helperName);
  if (writeHelper) return { ...writeHelper, access: 'write' };
  if (CONTROLLED_NUCLIO_READ_ONLY_HELPERS.has(helperName)) return { kind: 'read-only', access: 'read' };
  return null;
}

function controlledNuclioHelperFromScript(scriptPath) {
  const normalized = normalizeSlashes(scriptPath).replace(/^['"]|['"]$/g, '');
  if (!normalized) return null;

  const helperName = path.posix.basename(normalized);
  const helper = nuclioHelperInfo(helperName);
  if (!helper) return null;

  if (normalized === `$CLAUDE_PLUGIN_ROOT/scripts/${helperName}`) return helper;
  if (normalized === `\${CLAUDE_PLUGIN_ROOT}/scripts/${helperName}`) return helper;
  if (normalized === `plugins/nuclio/scripts/${helperName}`) return helper;

  const absolute = normalizedAbsolutePath(normalized);
  if (!absolute) return null;

  if (process.env.CLAUDE_PLUGIN_ROOT) {
    const envPluginRootHelper = normalizedAbsolutePath(path.join(process.env.CLAUDE_PLUGIN_ROOT, 'scripts', helperName));
    if (absolute === envPluginRootHelper) return helper;
  }

  const inferredPluginRootHelper = normalizedAbsolutePath(path.join(pluginRootFromGuard, 'scripts', helperName));
  if (absolute === inferredPluginRootHelper) return helper;

  return null;
}

function isSideEffectfulNodeOption(token) {
  return token === '--require'
    || token.startsWith('--require=')
    || token === '-r'
    || (token.startsWith('-r') && !token.startsWith('--'))
    || token === '--import'
    || token.startsWith('--import=')
    || token === '--loader'
    || token.startsWith('--loader=')
    || token === '--experimental-loader'
    || token.startsWith('--experimental-loader=');
}

function nodeOptionConsumesNext(token) {
  return token === '--require'
    || token === '-r'
    || token === '--import'
    || token === '--loader'
    || token === '--experimental-loader'
    || token === '-e'
    || token === '--eval'
    || token === '-p'
    || token === '--print';
}

function hasNodeOptionsEnvAssignment(tokens) {
  return tokens.some((token) => /^NODE_OPTIONS=/.test(token));
}

function isShellEnvAssignment(token) {
  return /^[A-Za-z_][A-Za-z0-9_]*=.*/.test(token || '');
}

function hasClaudePluginRootAssignment(tokens, beforeIndex = tokens.length) {
  return tokens.slice(0, beforeIndex).some((token) => /^CLAUDE_PLUGIN_ROOT=/.test(token));
}

function controlledNuclioHelperTarget(tokens) {
  const base = segmentBaseCommand(tokens);
  if (base !== 'node') return null;

  const commandIndex = tokens.findIndex((token) => path.basename(token) === 'node');
  if (commandIndex === -1) return null;

  const assignsClaudePluginRoot = hasClaudePluginRootAssignment(tokens, commandIndex);
  let scriptIndex = commandIndex + 1;
  let hasNodeOption = false;
  let sideEffectfulNodeOption = null;
  while (tokens[scriptIndex] && tokens[scriptIndex].startsWith('-')) {
    hasNodeOption = true;
    if (isSideEffectfulNodeOption(tokens[scriptIndex])) sideEffectfulNodeOption = tokens[scriptIndex];
    if (nodeOptionConsumesNext(tokens[scriptIndex])) {
      scriptIndex += 2;
      continue;
    }
    scriptIndex += 1;
  }

  const helper = controlledNuclioHelperFromScript(tokens[scriptIndex] || '');
  if (!helper) return null;
  const target = tokens[scriptIndex + 1];
  if (assignsClaudePluginRoot) {
    return { kind: helper.kind, target: target ? normalizePath(target) : '', ok: false, reason: 'Blocked: controlled Nuclio helper commands must not assign CLAUDE_PLUGIN_ROOT in the same command segment.' };
  }
  if (hasNodeOptionsEnvAssignment(tokens)) {
    return { kind: helper.kind, target: target ? normalizePath(target) : '', ok: false, reason: 'Blocked: controlled Nuclio helper commands must not set NODE_OPTIONS.' };
  }
  if (sideEffectfulNodeOption || hasNodeOption) {
    return { kind: helper.kind, target: target ? normalizePath(target) : '', ok: false, reason: 'Blocked: controlled Nuclio helper commands must not use Node options.' };
  }
  if (helper.access === 'read') return { kind: helper.kind, target: '', ok: true, readOnly: true };
  if (!target) return null;
  return { kind: helper.kind, target: normalizePath(target), ok: helper.targetIsSafe(target) };
}

function collectControlledNuclioHelperTargets(command, paths) {
  for (const segment of commandSegments(command)) {
    const helper = controlledNuclioHelperTarget(shellTokens(segment));
    if (helper?.ok) paths.push(helper.target);
  }
}

function controlledNuclioHelperTargetsFromCommand(command) {
  const targets = [];
  for (const segment of commandSegments(command)) {
    const helper = controlledNuclioHelperTarget(shellTokens(segment));
    if (helper?.ok) targets.push(helper.target);
  }
  return [...new Set(targets)];
}

function invalidControlledNuclioHelper(command) {
  for (const segment of commandSegments(command)) {
    const helper = controlledNuclioHelperTarget(shellTokens(segment));
    if (helper && !helper.ok) return helper;
  }
  return null;
}

function extractBashWriteTargetPaths(rawInput) {
  const paths = [];
  for (const command of bashCommandsForWriteTargetExtraction(rawInput)) {
    collectShellRedirectionTargets(command, paths);
    collectTeeTargets(command, paths);
    collectRegexWriteTargets(command, paths);
    collectKnownCommandWriteTargets(command, paths);
    collectControlledNuclioHelperTargets(command, paths);
  }

  return [...new Set(paths.map(normalizePath).filter(Boolean))];
}

function targetPathsForBashWriteTargets(rawInput) {
  const paths = extractBashWriteTargetPaths(rawInput);
  const outsidePath = paths.find(isOutsideWorkspacePath);
  if (outsidePath) return { ok: false, reason: `Blocked: ${outsidePath} is outside workspace/repository.` };
  return { ok: true, paths };
}

function isControlledHelperWriteTarget(targetPath) {
  return isSafeStatePath(targetPath) || isSafeEventsPath(targetPath);
}

function targetIsProtectedStateOrEvents(targetPath) {
  const normalized = normalizePath(targetPath);
  return /^\.nuclio\/changes\/[^/]+\/(?:state\.json|events\.jsonl)$/.test(normalized)
    || normalized === '.nuclio/project/init-state.json'
    || normalized === '.nuclio/project/events.jsonl';
}

function phaseOwnedArtifactForTarget(targetPath) {
  const normalized = normalizePath(targetPath);
  return PHASE_OWNED_ARTIFACTS.find((artifact) => artifact.pattern.test(normalized)) ?? null;
}

function phaseOwnedArtifactAllows(rootDir, targetPath) {
  const artifact = phaseOwnedArtifactForTarget(targetPath);
  if (!artifact) return { ok: true };
  const changes = activeChanges(rootDir);
  const normalized = normalizePath(targetPath);
  const matchingChange = changes.find(({ changeId }) => normalized.startsWith(`.nuclio/changes/${changeId}/`));
  if (!matchingChange) return { ok: true };
  const approved = canonicalApproval(matchingChange.state, artifact.approval) === true;
  if (approved) {
    return { ok: false, reason: `Blocked: phase-owned .nuclio artifact ${normalized} belongs to ${artifact.ownerPhase} phase after ${artifact.approval} approval.` };
  }
  return { ok: true };
}

function readStateFileIfPresent(filePath) {
  if (!existsSync(filePath)) return null;
  const relativePath = normalizePath(path.relative(cwd, filePath));
  try {
    const parsed = JSON.parse(readFileSync(filePath, 'utf8'));
    if (!hasValidStateSchema(parsed)) {
      return { ok: false, relativePath, state: null };
    }
    return { ok: true, relativePath, state: parsed };
  } catch {
    return { ok: false, relativePath, state: null };
  }
}

function readProjectStateEntry(rootDir) {
  return readStateFileIfPresent(path.join(rootDir, '.nuclio/project/init-state.json'));
}

function readProjectState(rootDir) {
  const entry = readProjectStateEntry(rootDir);
  return entry?.ok ? entry.state : null;
}

function listChangeStateEntries(rootDir) {
  const changesDir = path.join(rootDir, '.nuclio/changes');
  if (!existsSync(changesDir)) return [];

  const states = [];
  for (const entry of readdirSync(changesDir, { withFileTypes: true })) {
    if (!entry.isDirectory()) continue;
    const statePath = path.join(changesDir, entry.name, 'state.json');
    const stateEntry = readStateFileIfPresent(statePath);
    if (stateEntry) {
      states.push({
        changeId: entry.name,
        state: stateEntry.state,
        ok: stateEntry.ok,
        relativePath: stateEntry.relativePath,
        statePath,
        changeDir: path.dirname(statePath),
      });
    }
  }

  return states.sort((a, b) => String(b.state?.updated_at || '').localeCompare(String(a.state?.updated_at || '')));
}

function listChangeStates(rootDir) {
  return listChangeStateEntries(rootDir).filter((entry) => entry.ok);
}

function invalidStateEntries(rootDir) {
  return [readProjectStateEntry(rootDir), ...listChangeStateEntries(rootDir)].filter((entry) => entry && !entry.ok);
}

function canonicalApproval(state, key) {
  if (!state || typeof state !== 'object' || !state.approved || typeof state.approved !== 'object') return undefined;
  if (typeof state.approved[key] === 'boolean') return state.approved[key];
  return undefined;
}

function activeChanges(rootDir) {
  return listChangeStates(rootDir).filter(({ state }) => state.workflow === 'change' && state.status !== 'done' && state.status !== 'failed');
}

function activeProject(rootDir) {
  const state = readProjectState(rootDir);
  if (state?.workflow === 'project_initialization' && state.status !== 'done' && state.status !== 'failed') return state;
  return null;
}

function hasActiveNuclioWorkflow(rootDir) {
  return Boolean(activeProject(rootDir)) || activeChanges(rootDir).length > 0;
}

function markdownSection(raw, headingName) {
  const headingRegex = /^##\s+(.+?)\s*$/gim;
  let match;
  while ((match = headingRegex.exec(raw)) !== null) {
    if (match[1].trim().toLowerCase() !== headingName.toLowerCase()) continue;
    const start = headingRegex.lastIndex;
    headingRegex.lastIndex = start;
    const next = headingRegex.exec(raw);
    return raw.slice(start, next ? next.index : raw.length);
  }
  return null;
}

function splitMarkdownTableLine(line) {
  return line.slice(1, -1).split('|').map((cell) => cell.trim());
}

function parseFirstMarkdownTable(rawSection) {
  if (!rawSection) return { headers: [], rows: [] };
  const lines = rawSection.split(/\r?\n/);
  let start = -1;
  for (let index = 0; index < lines.length; index += 1) {
    const line = lines[index].trim();
    if (line.startsWith('|') && line.endsWith('|')) {
      start = index;
      break;
    }
  }
  if (start === -1) return { headers: [], rows: [] };

  const tableLines = [];
  for (let index = start; index < lines.length; index += 1) {
    const line = lines[index].trim();
    if (!line.startsWith('|') || !line.endsWith('|')) break;
    tableLines.push(line);
  }
  if (tableLines.length < 2) return { headers: [], rows: [] };

  const headers = splitMarkdownTableLine(tableLines[0]).map((cell) => cell.toLowerCase());
  const rows = [];
  for (const line of tableLines.slice(2)) {
    const cells = splitMarkdownTableLine(line);
    if (cells.every((cell) => /^:?-+:?$/.test(cell))) continue;
    const row = {};
    for (const [index, header] of headers.entries()) row[header] = cells[index] ?? '';
    if (Object.values(row).some((cell) => String(cell).trim())) rows.push(row);
  }
  return { headers, rows };
}

function proposalTargetsById(raw) {
  const table = parseFirstMarkdownTable(markdownSection(raw, 'Proposed Updates') ?? markdownSection(raw, 'Proposed Files'));
  const targets = new Map();
  for (const row of table.rows) {
    const id = String(row.id || '').trim();
    const target = row.target ?? row.path ?? row.target_path;
    if (id && target) targets.set(id, target);
  }
  return targets;
}

function markdownMetadataValue(block, keyAlternatives) {
  for (const key of keyAlternatives) {
    const escaped = key.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    const match = block.match(new RegExp(`^\\s*(?:[-*]\\s*)?${escaped}:\\s*(.+?)\\s*$`, 'im'));
    if (match) return match[1].trim();
  }
  return '';
}

function anchorsInUpdateBlock(block) {
  const anchors = new Set();
  const patterns = [
    /<a\s+[^>]*(?:id|name)=["']([^"']+)["'][^>]*>/gim,
    /\{#([A-Za-z0-9_.:-]+)\}/g,
    /^\s*(?:[-*]\s*)?(?:anchor|content_anchor):\s*(\S+)\s*$/gim,
  ];
  for (const pattern of patterns) {
    let match;
    while ((match = pattern.exec(block)) !== null) anchors.add(match[1]);
  }
  return anchors;
}

function updateBlocksByProposalId(raw) {
  const blocks = new Map();
  const headingRegex = /^###\s+Update\s+(\S+)\s*$/gim;
  const matches = [...raw.matchAll(headingRegex)];
  for (const [index, match] of matches.entries()) {
    const start = match.index;
    const end = matches[index + 1]?.index ?? raw.length;
    const block = raw.slice(start, end);
    blocks.set(match[1], {
      headingId: match[1],
      id: markdownMetadataValue(block, ['id']),
      anchors: anchorsInUpdateBlock(block),
    });
  }
  return blocks;
}

function validApprovedContentRef(ref, proposalId, proposalTargets, updateBlocks) {
  const trimmed = String(ref || '').trim();
  if (!trimmed || !proposalId || !proposalTargets.has(proposalId)) return false;
  const block = updateBlocks.get(proposalId);
  if (!block) return false;

  const acceptedRefs = new Set([
    `Update ${proposalId}`,
    `### Update ${proposalId}`,
    `proposal:${proposalId}`,
    `#update-${String(proposalId).toLowerCase()}`,
  ]);
  for (const anchor of block.anchors || []) {
    acceptedRefs.add(anchor);
    acceptedRefs.add(`#${anchor}`);
  }

  return acceptedRefs.has(trimmed);
}

function isSafeConcreteDevDocsPatchTarget(target) {
  const raw = String(target || '').replace(/\\/g, '/').trim();
  const normalized = normalizeRelativePath(raw);
  return raw.startsWith('.dev-docs/')
    && !raw.endsWith('/')
    && !raw.split('/').includes('..')
    && normalized.startsWith('.dev-docs/')
    && normalized !== '.dev-docs/'
    && !normalized.endsWith('/')
    && !normalized.includes('/../')
    && !/[*?[\]{}]/.test(raw)
    && !/[*?[\]{}]/.test(normalized);
}

function extractAcceptedPatchTargets(filePath) {
  if (!existsSync(filePath)) return [];
  const raw = readFileSync(filePath, 'utf8');
  const proposalTargets = proposalTargetsById(raw);
  const updateBlocks = updateBlocksByProposalId(raw);
  const approvalTable = parseFirstMarkdownTable(markdownSection(raw, 'Human Approval Decisions'));
  const targets = [];

  for (const row of approvalTable.rows) {
    const decision = String(row.decision || '').trim().toLowerCase();
    if (decision !== 'accept' && decision !== 'edit') continue;
    const id = String(row.id || '').trim();
    const approvedContentRef = row.approved_content_ref ?? row.content_ref ?? row.approved_content ?? '';
    if (!validApprovedContentRef(approvedContentRef, id, proposalTargets, updateBlocks)) continue;
    const target = proposalTargets.get(id);
    if (target && isSafeConcreteDevDocsPatchTarget(target)) targets.push(target);
  }

  return targets.map(normalizePath).filter(Boolean);
}

function targetEqualsAny(targetPath, allowedTargets) {
  const normalizedTarget = normalizePath(targetPath);
  return allowedTargets.some((allowed) => normalizePath(allowed) === normalizedTarget);
}

function targetMatchesAny(targetPath, allowedTargets) {
  const normalizedTarget = normalizePath(targetPath);
  return allowedTargets.some((allowed) => normalizePath(allowed) === normalizedTarget || matchesPattern(normalizedTarget, allowed));
}

function scopedApprovalTargets(state, key) {
  const scope = state?.approved?.[key];
  if (!scope || typeof scope !== 'object' || !Array.isArray(scope.target_paths)) return [];
  return scope.target_paths.map(normalizePath).filter(Boolean);
}

function projectDevDocsApprovalAllows(rootDir, targetPath) {
  const state = readProjectState(rootDir);
  if (!(state?.workflow === 'project_initialization'
    && state.status !== 'done'
    && state.status !== 'failed'
    && state.phase === 'initial_dev_docs'
    && canonicalApproval(state, 'initial_dev_docs') === true)) {
    return false;
  }

  const scopedTargets = scopedApprovalTargets(state, 'initial_dev_docs_scope');
  const patchTargets = extractAcceptedPatchTargets(path.join(rootDir, '.nuclio/project/initial-dev-docs.patch.md'));
  return (scopedTargets.length > 0 && targetMatchesAny(targetPath, scopedTargets))
    || (patchTargets.length > 0 && targetEqualsAny(targetPath, patchTargets));
}

function changeMemoryApprovalAllows(rootDir, targetPath) {
  return listChangeStates(rootDir).some(({ state, changeDir }) => {
    if (!(state.workflow === 'change'
      && state.status !== 'done'
      && state.status !== 'failed'
      && state.phase === 'close'
      && canonicalApproval(state, 'memory') === true)) {
      return false;
    }

    const scopedTargets = scopedApprovalTargets(state, 'memory_scope');
    const patchTargets = extractAcceptedPatchTargets(path.join(changeDir, 'memory.patch.md'));
    return (scopedTargets.length > 0 && targetMatchesAny(targetPath, scopedTargets))
      || (patchTargets.length > 0 && targetEqualsAny(targetPath, patchTargets));
  });
}

function hasExplicitNuclioDevDocsApproval(rootDir, targetPath) {
  return projectDevDocsApprovalAllows(rootDir, targetPath) || changeMemoryApprovalAllows(rootDir, targetPath);
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

  while (patternIndex < patternSegment.length && patternSegment[patternIndex] === '*') patternIndex += 1;
  return patternIndex === patternSegment.length;
}

function matchGlobSegments(targetSegments, patternSegments, targetIndex = 0, patternIndex = 0) {
  if (patternIndex === patternSegments.length) return targetIndex === targetSegments.length;
  const patternSegment = patternSegments[patternIndex];
  if (patternSegment === '**') {
    for (let nextTargetIndex = targetIndex; nextTargetIndex <= targetSegments.length; nextTargetIndex += 1) {
      if (matchGlobSegments(targetSegments, patternSegments, nextTargetIndex, patternIndex + 1)) return true;
    }
    return false;
  }
  if (targetIndex >= targetSegments.length) return false;
  return matchSegment(targetSegments[targetIndex], patternSegment)
    && matchGlobSegments(targetSegments, patternSegments, targetIndex + 1, patternIndex + 1);
}

function matchesPattern(targetPath, pattern) {
  const normalizedTarget = normalizePath(targetPath);
  const normalizedPattern = normalizePath(pattern);
  if (!normalizedPattern) return false;
  return matchGlobSegments(globSegments(normalizedTarget), globSegments(normalizedPattern));
}

function stripYamlComment(value) {
  let quote = null;
  for (let index = 0; index < value.length; index += 1) {
    const char = value[index];
    if (quote) {
      if (char === quote) quote = null;
      continue;
    }
    if (char === '\'' || char === '"') {
      quote = char;
      continue;
    }
    if (char === '#' && (index === 0 || /\s/.test(value[index - 1]))) return value.slice(0, index).trimEnd();
  }
  return value.trimEnd();
}

function unquoteYamlScalar(value) {
  const trimmed = stripYamlComment(value).trim();
  if (trimmed.length >= 2) {
    const first = trimmed[0];
    const last = trimmed[trimmed.length - 1];
    if ((first === '\'' && last === '\'') || (first === '"' && last === '"')) return trimmed.slice(1, -1);
  }
  return trimmed;
}

function parseInlineYamlList(value) {
  const trimmed = stripYamlComment(value).trim();
  if (!trimmed.startsWith('[') || !trimmed.endsWith(']')) return null;
  const inner = trimmed.slice(1, -1).trim();
  if (!inner) return [];
  const values = [];
  let quote = null;
  let current = '';
  for (let index = 0; index < inner.length; index += 1) {
    const char = inner[index];
    if (quote) {
      if (char === quote) quote = null;
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
  if (quote) return null;
  values.push(unquoteYamlScalar(current));
  return values.filter((item) => item.length > 0);
}

function extractYamlList(lines, startIndex, baseIndent) {
  const values = [];
  for (let index = startIndex + 1; index < lines.length; index += 1) {
    const line = lines[index];
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith('#')) continue;
    const indent = line.length - line.trimStart().length;
    if (indent <= baseIndent) break;
    const itemMatch = trimmed.match(/^-\s+(.+)$/);
    if (itemMatch) values.push(unquoteYamlScalar(itemMatch[1]));
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
    if (!trimmed) continue;
    const indent = line.length - line.trimStart().length;
    if (indent <= baseIndent) break;
  }
  return index - 1;
}

function parsePlanTasks(filePath, allowedSection) {
  if (!existsSync(filePath)) return [];
  const lines = readFileSync(filePath, 'utf8').split(/\r?\n/);
  const tasks = [];
  let current = null;
  let currentSection = null;
  let currentSectionIndent = -1;

  for (let index = 0; index < lines.length; index += 1) {
    const line = lines[index];
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith('#')) continue;
    const indent = line.length - line.trimStart().length;
    if (isBlockScalarStart(trimmed)) {
      index = skipBlockScalar(lines, index, indent);
      continue;
    }
    const content = stripYamlComment(trimmed).trim();
    const topLevelKeyMatch = content.match(/^([A-Za-z_][\w-]*):(?:\s*)?$/) || content.match(/^([A-Za-z_][\w-]*):\s+.+$/);
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
    const itemKeyMatch = content.match(/^-\s+([A-Za-z_][\w-]*):\s*(.*)$/);
    if (itemKeyMatch) {
      current = { allowed_paths: [], forbidden_paths: [] };
      tasks.push(current);
      const [, key, value] = itemKeyMatch;
      if (key === 'id') current.id = unquoteYamlScalar(value);
      if (key === 'allowed_paths') current.allowed_paths = parseInlineYamlList(value) ?? extractYamlList(lines, index, indent);
      if (key === 'forbidden_paths') current.forbidden_paths = parseInlineYamlList(value) ?? extractYamlList(lines, index, indent);
      continue;
    }
    if (!current) continue;
    const keyMatch = content.match(/^([A-Za-z_][\w-]*):\s*(.*)$/);
    if (!keyMatch) continue;
    const [, key, value] = keyMatch;
    if (key === 'id') current.id = unquoteYamlScalar(value);
    if (key === 'allowed_paths') current.allowed_paths = parseInlineYamlList(value) ?? extractYamlList(lines, index, indent);
    if (key === 'forbidden_paths') current.forbidden_paths = parseInlineYamlList(value) ?? extractYamlList(lines, index, indent);
  }

  return tasks;
}

function taskPathBoundaryAllows(targetPath, task, label) {
  const forbidden = task.forbidden_paths || [];
  const allowed = task.allowed_paths || [];
  if (forbidden.some((pattern) => matchesPattern(targetPath, pattern))) return { ok: false, reason: `Blocked: ${targetPath} matches ${label} forbidden_paths.` };
  if (!allowed.length) return { ok: false, reason: `Blocked: ${label} allowed_paths is empty.` };
  if (!allowed.some((pattern) => matchesPattern(targetPath, pattern))) return { ok: false, reason: `Blocked: ${targetPath} is outside ${label} allowed_paths.` };
  return { ok: true };
}

function currentTaskId(state) {
  if (typeof state.current_task === 'string') return state.current_task;
  if (state.current_task && typeof state.current_task.id === 'string') return state.current_task.id;
  return null;
}

function changePathBoundaryAllows(_rootDir, change, targetPath) {
  const { state, changeDir } = change;
  if (state.phase !== 'build' || canonicalApproval(state, 'design') !== true) {
    return { ok: false, reason: 'Blocked: application writes require change phase build and approved.design === true.' };
  }
  const taskId = currentTaskId(state);
  if (!taskId) return { ok: false, reason: 'Blocked: build writes require state.current_task.' };
  const tasks = parsePlanTasks(path.join(changeDir, 'plan.yaml'), 'tasks');
  const task = tasks.find((candidate) => candidate.id === taskId);
  if (!task) return { ok: false, reason: `Blocked: current_task ${taskId} was not found in plan.yaml.` };
  return taskPathBoundaryAllows(targetPath, task, `task ${taskId}`);
}

function activeChangeBoundaryAllows(rootDir, targetPath) {
  const changes = activeChanges(rootDir);
  if (!changes.length) return null;
  if (changes.length > 1) return { ok: false, reason: 'Blocked: application writes require exactly one active workflow: change.' };
  return changePathBoundaryAllows(rootDir, changes[0], targetPath);
}

function projectScaffoldBoundaryAllows(rootDir, targetPath) {
  const state = readProjectState(rootDir);
  if (!state || state.workflow !== 'project_initialization' || state.status === 'failed' || state.status === 'done') return null;
  if (canonicalApproval(state, 'scaffold') !== true) return { ok: false, reason: 'Blocked: project scaffold writes require approved.scaffold === true.' };
  const tasks = parsePlanTasks(path.join(rootDir, '.nuclio/project/scaffold-plan.yaml'), 'scaffold_tasks');
  if (!tasks.length) return { ok: false, reason: 'Blocked: scaffold-plan.yaml contains no scaffold_tasks with allowed_paths.' };
  for (const task of tasks) {
    const result = taskPathBoundaryAllows(targetPath, task, `scaffold task ${task.id}`);
    if (result.ok) return result;
  }
  return { ok: false, reason: `Blocked: ${targetPath} is outside scaffold allowed_paths or matches forbidden_paths.` };
}

function applicationWriteAllows(rootDir, targetPath) {
  const changeResult = activeChangeBoundaryAllows(rootDir, targetPath);
  if (changeResult) return changeResult;
  const projectResult = projectScaffoldBoundaryAllows(rootDir, targetPath);
  if (projectResult) return projectResult;
  return { ok: true };
}

function validRiskApproval(approval, command) {
  if (!approval || typeof approval !== 'object' || approval.approved !== true || approval.scope !== 'current_workflow' || typeof approval.command_pattern !== 'string') return false;
  if (approval.expires_at) {
    const expires = Date.parse(approval.expires_at);
    if (Number.isFinite(expires) && expires <= Date.now()) return false;
  }
  if (approval.command_pattern.startsWith('contains:')) {
    return command.includes(approval.command_pattern.slice('contains:'.length));
  }
  return approval.command_pattern === command;
}

function hasScopedRiskApproval(rootDir, command) {
  const states = [activeProject(rootDir), ...activeChanges(rootDir).map((entry) => entry.state)].filter(Boolean);
  return states.some((state) => Array.isArray(state.risk_approvals) && state.risk_approvals.some((approval) => validRiskApproval(approval, command)));
}

function segmentBaseCommand(tokens) {
  let index = 0;
  while (tokens[index] && /^[A-Z_][A-Z0-9_]*=.*/.test(tokens[index])) index += 1;
  if (tokens[index] === 'env') index += 1;
  return path.basename(tokens[index] || '');
}

function isNodeCheckOrValidator(tokens) {
  const command = segmentBaseCommand(tokens);
  if (command !== 'node') return false;
  if (tokens.includes('--check')) return true;
  const script = tokens.find((token) => /(?:^|\/)validate-[^/]+\.mjs$/.test(token));
  return Boolean(script);
}

function isReadOnlyCommandSegment(segment) {
  const tokens = shellTokens(segment);
  if (!tokens.length) return true;
  if (isNodeCheckOrValidator(tokens)) return true;
  const base = segmentBaseCommand(tokens);
  const readOnly = new Set([
    'pwd', 'ls', 'find', 'rg', 'grep', 'git', 'jq', 'node', 'cat', 'wc', 'sort', 'uniq', 'printf', 'test', 'true', 'false',
  ]);
  if (!readOnly.has(base)) return false;
  if (base === 'git') {
    const allowedGit = /\bgit\s+(?:-[^\s]+\s+[^\s]+\s+)*(?:status|diff|log|show|ls-files|rev-parse|branch)\b/i;
    return allowedGit.test(segment);
  }
  if (base === 'node') return isNodeCheckOrValidator(tokens);
  return true;
}

function hasAmbiguousWriteLikeBash(command) {
  const segments = commandSegments(command);
  for (const segment of segments) {
    const tokens = shellTokens(segment);
    const helper = controlledNuclioHelperTarget(tokens);
    if (helper?.ok) continue;
    const base = segmentBaseCommand(tokens);
    if (!base) continue;
    const knownTargetWriteCommand = (base === 'sed' && tokens.some((token) => token === '-i' || token.startsWith('-i')))
      || (base === 'perl' && tokens.some((token) => token === '-pi' || token === '-p' || token === '-i' || token.startsWith('-pi') || token.startsWith('-i')))
      || ['cp', 'mv', 'install', 'touch', 'mkdir'].includes(base);
    if (knownTargetWriteCommand) {
      if (extractBashWriteTargetPaths(JSON.stringify({ command: segment })).length === 0) return true;
      continue;
    }
    if (['python', 'python3', 'node'].includes(base) && !isNodeCheckOrValidator(tokens)) {
      return true;
    }
    if (!isReadOnlyCommandSegment(segment) && extractBashWriteTargetPaths(JSON.stringify({ command: segment })).length === 0) {
      return true;
    }
  }
  return false;
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

function eventsFileForBlockedOperation(targetPaths) {
  for (const targetPath of targetPaths) {
    const normalized = normalizePath(targetPath);
    const changeMatch = normalized.match(/(?:^|\/)\.nuclio\/changes\/([^/]+)\//);
    if (changeMatch) return path.join(cwd, '.nuclio/changes', changeMatch[1], 'events.jsonl');
    if (/(^|\/)\.nuclio\/project\//.test(normalized)) return path.join(cwd, '.nuclio/project/events.jsonl');
  }
  const changes = activeChanges(cwd);
  if (changes.length === 1) return path.join(changes[0].changeDir, 'events.jsonl');
  if (changeMemoryApprovalAllows(cwd, targetPaths[0] || '')) {
    const closeChange = listChangeStates(cwd).find(({ state }) => state.workflow === 'change' && state.status !== 'done' && state.status !== 'failed' && state.phase === 'close');
    if (closeChange) return path.join(closeChange.changeDir, 'events.jsonl');
  }
  if (activeProject(cwd)) return path.join(cwd, '.nuclio/project/events.jsonl');
  return null;
}

function appendBlockedEvent(reason, targetPaths = []) {
  const eventFile = eventsFileForBlockedOperation(targetPaths);
  if (!eventFile || !isSafeEventsFile(path.resolve(eventFile))) return;
  const event = {
    type: 'operation.blocked',
    tool: tool || null,
    reason,
    artifact: targetPaths[0] || null,
    result: 'blocked',
    target_paths: targetPaths,
  };
  mkdirSync(path.dirname(eventFile), { recursive: true });
  appendFileSync(eventFile, `${JSON.stringify(event)}\n`);
}

function block(reason, targetPaths = []) {
  appendBlockedEvent(reason, targetPaths);
  console.error(reason);
  process.exit(2);
}

let targetPathResult = { ok: true, paths: [] };
if (writeLikeTools.has(tool)) {
  targetPathResult = targetPathsForWriteLikeTool(input);
} else if (tool === 'Bash') {
  targetPathResult = targetPathsForBashWriteTargets(input);
}

if (!targetPathResult.ok) block(targetPathResult.reason, []);

const targetPaths = targetPathResult.paths;
const bashCommand = tool === 'Bash' ? parseBashInput(input) : '';
const controlledHelperWriteTargets = tool === 'Bash' ? controlledNuclioHelperTargetsFromCommand(bashCommand) : [];
const rawMentionsDevDocs = /(^|[^\w.-])\.dev-docs\//.test(input) || input.includes('.dev-docs/');
const useRawDevDocsFallback = !targetPaths.length;
const touchesDevDocs = targetPaths.some(pathTargetsDevDocs) || (useRawDevDocsFallback && rawMentionsDevDocs);
const touchesApplication = targetPaths.some(isApplicationPath);
const invalidState = invalidStateEntries(cwd)[0];
if (invalidState && (touchesApplication || touchesDevDocs)) {
  block(`Blocked: invalid Nuclio state file ${invalidState.relativePath}.`, targetPaths);
}

const bashInputs = tool === 'Bash' ? bashInputsToCheck(input) : [];
const isDangerousBash = tool === 'Bash' && bashInputs.some((bashInput) => dangerousBashPatterns.some((pattern) => pattern.test(bashInput)) || hasDangerousBashCommand(bashInput));
const hasRiskApproval = tool === 'Bash' && hasScopedRiskApproval(cwd, bashCommand);

if (isDangerousBash && !hasRiskApproval) {
  block('Blocked: dangerous bash command requires human approval.', targetPaths);
}

const invalidHelper = tool === 'Bash' ? invalidControlledNuclioHelper(bashCommand) : null;
if (invalidHelper) {
  block(invalidHelper.reason ?? `Blocked: ${invalidHelper.kind} helper target must be a safe Nuclio ${invalidHelper.kind} path.`, [invalidHelper.target].filter(Boolean));
}

if (tool === 'Bash' && hasActiveNuclioWorkflow(cwd) && !hasRiskApproval && hasAmbiguousWriteLikeBash(bashCommand)) {
  block('Blocked: ambiguous Bash command in active Nuclio workflow; use Write/Edit/MultiEdit or a scoped risk approval.', targetPaths);
}

if (writeLikeTools.has(tool) || tool === 'Bash') {
  for (const targetPath of targetPaths) {
    if (targetIsProtectedStateOrEvents(targetPath) && !controlledHelperWriteTargets.some((helperTarget) => normalizePath(helperTarget) === normalizePath(targetPath))) {
      block('Blocked: writing Nucl.io state/events requires controlled state/events helper.', [targetPath]);
    }
    const artifactResult = phaseOwnedArtifactAllows(cwd, targetPath);
    if (!artifactResult.ok) block(artifactResult.reason, [targetPath]);
  }
}

if (touchesDevDocs) {
  const devDocsTargets = targetPaths.filter(pathTargetsDevDocs);
  const targetsToCheck = devDocsTargets.length ? devDocsTargets : ['.dev-docs/'];
  for (const targetPath of targetsToCheck) {
    if (!hasExplicitNuclioDevDocsApproval(cwd, targetPath)) {
      block('Blocked: writing .dev-docs requires canonical Nucl.io approval state.', targetsToCheck);
    }
  }
}

if (writeLikeTools.has(tool) || tool === 'Bash') {
  for (const targetPath of targetPaths.filter(isApplicationPath)) {
    const result = applicationWriteAllows(cwd, targetPath);
    if (!result.ok) block(result.reason, [targetPath]);
  }
}

console.log(`guard ok: ${cwd}`);
