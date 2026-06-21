import { existsSync, readFileSync } from 'node:fs';
import path from 'node:path';

const filePath = process.argv[2];
const sectionArgIndex = process.argv.indexOf('--section');
const section = sectionArgIndex === -1 ? 'tasks' : process.argv[sectionArgIndex + 1];
const TASK_TYPES = ['implementation', 'verification', 'documentation', 'migration', 'research'];
const RISK_LEVELS = ['low', 'medium', 'high'];

function fail(message) {
  console.error(message);
  process.exit(1);
}

if (!filePath || !['tasks', 'scaffold_tasks'].includes(section)) {
  fail('usage: node validate-plan.mjs <plan.yaml> --section <tasks|scaffold_tasks>');
}

if (!existsSync(filePath)) {
  fail(`missing plan file: ${filePath}`);
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
    if (char === '#' && (index === 0 || /\s/.test(value[index - 1]))) {
      return value.slice(0, index).trimEnd();
    }
  }
  return value.trimEnd();
}

function unquote(value) {
  const trimmed = stripYamlComment(value).trim();
  if (trimmed.length >= 2 && ((trimmed[0] === '\'' && trimmed.at(-1) === '\'') || (trimmed[0] === '"' && trimmed.at(-1) === '"'))) {
    return trimmed.slice(1, -1);
  }
  return trimmed;
}

function parseInlineList(value) {
  const trimmed = stripYamlComment(value).trim();
  if (!trimmed.startsWith('[') || !trimmed.endsWith(']')) return null;
  const inner = trimmed.slice(1, -1).trim();
  if (!inner) return [];
  return inner.split(',').map((item) => unquote(item)).filter(Boolean);
}

function extractList(lines, startIndex, baseIndent) {
  const values = [];
  for (let index = startIndex + 1; index < lines.length; index += 1) {
    const line = lines[index];
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith('#')) continue;
    const indent = line.length - line.trimStart().length;
    if (indent <= baseIndent) break;
    const match = trimmed.match(/^[-*]\s+(.+)$/);
    if (match) values.push(unquote(match[1]));
  }
  return values;
}

function extractBlockScalar(lines, startIndex, baseIndent) {
  const values = [];
  for (let index = startIndex + 1; index < lines.length; index += 1) {
    const line = lines[index];
    if (!line.trim()) {
      values.push('');
      continue;
    }
    const indent = line.length - line.trimStart().length;
    if (indent <= baseIndent) break;
    values.push(line.slice(Math.min(indent, baseIndent + 2)).trimEnd());
  }
  return values.join('\n').trim();
}

function isBlockScalarValue(value) {
  return /^[|>][+-]?(?:\s+#.*)?$/.test(stripYamlComment(value).trim());
}

function assignPlanTaskField(task, key, value, lines, index, indent) {
  const inlineList = parseInlineList(value);
  if (inlineList !== null) {
    task[key] = inlineList;
  } else if (isBlockScalarValue(value)) {
    task[key] = extractBlockScalar(lines, index, indent);
  } else if (!stripYamlComment(value).trim()) {
    const list = extractList(lines, index, indent);
    task[key] = list.length ? list : '';
  } else {
    task[key] = unquote(value);
  }
}

function parsePlanTasks(raw, allowedSection) {
  const lines = raw.split(/\r?\n/);
  const tasks = [];
  let current = null;
  let currentSection = null;
  let currentSectionIndent = -1;

  for (let index = 0; index < lines.length; index += 1) {
    const line = lines[index];
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith('#')) continue;
    const indent = line.length - line.trimStart().length;
    const content = stripYamlComment(trimmed).trim();
    const topLevel = content.match(/^([A-Za-z_][\w-]*):(?:\s.*)?$/);
    if (topLevel && indent === 0) {
      currentSection = topLevel[1] === allowedSection ? topLevel[1] : null;
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
      current = {};
      tasks.push(current);
      const [, key, value] = itemKeyMatch;
      assignPlanTaskField(current, key, value, lines, index, indent);
      continue;
    }
    if (!current) continue;
    const keyMatch = content.match(/^([A-Za-z_][\w-]*):\s*(.*)$/);
    if (!keyMatch) continue;
    const [, key, value] = keyMatch;
    assignPlanTaskField(current, key, value, lines, index, indent);
  }
  return tasks;
}

function parseTopLevelList(raw, key) {
  const lines = raw.split(/\r?\n/);
  for (let index = 0; index < lines.length; index += 1) {
    const line = lines[index];
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith('#')) continue;
    const indent = line.length - line.trimStart().length;
    const match = stripYamlComment(trimmed).trim().match(new RegExp(`^${key}:\\s*(.*)$`));
    if (!match || indent !== 0) continue;
    const inlineList = parseInlineList(match[1]);
    if (inlineList !== null) return inlineList.filter((item) => String(item).trim());
    if (isBlockScalarValue(match[1])) {
      const block = extractBlockScalar(lines, index, indent);
      return block ? [block] : [];
    }
    if (match[1].trim()) {
      const scalar = unquote(match[1]);
      return scalar.trim() ? [scalar] : [];
    }
    return extractList(lines, index, indent).filter((item) => String(item).trim());
  }
  return [];
}

function hasNonEmptyPlanField(value) {
  if (Array.isArray(value)) return value.some((item) => String(item).trim());
  return String(value || '').trim().length > 0;
}

function normalizePlanPath(value) {
  return String(value || '').replace(/\\/g, '/').trim();
}

function isWindowsDriveAbsolutePath(value) {
  return /^[A-Za-z]:[\\/]/.test(String(value || '').trim());
}

function isSafeBoundaryPath(value) {
  if (isWindowsDriveAbsolutePath(value)) return false;
  const normalized = normalizePlanPath(value);
  if (!normalized || normalized.includes('\0') || path.posix.isAbsolute(normalized)) return false;
  if (normalized.split('/').includes('..')) return false;
  const normalizedAfter = path.posix.normalize(normalized);
  if (normalizedAfter.split('/').includes('..')) return false;
  return normalizedAfter === normalized.replace(/^\.\//, '');
}

function validateDependencyGraph(tasks, errors) {
  const ids = new Set();
  const graph = new Map();

  for (const [index, task] of tasks.entries()) {
    const label = task.id || `${section} entry ${index + 1}`;
    if (!task.id) continue;
    if (ids.has(task.id)) errors.push(`${label} duplicate id`);
    ids.add(task.id);
  }

  for (const [index, task] of tasks.entries()) {
    const label = task.id || `${section} entry ${index + 1}`;
    const deps = task.depends_on ?? [];
    if (!Array.isArray(deps)) {
      errors.push(`${label} depends_on must be an array`);
      graph.set(task.id, []);
      continue;
    }
    graph.set(task.id, deps);
    for (const dep of deps) {
      if (!ids.has(dep)) errors.push(`${label} depends_on references missing task id: ${dep}`);
      if (dep === task.id) errors.push(`${label} must not depend on itself`);
    }
  }

  const visiting = new Set();
  const visited = new Set();
  const stack = [];

  function dfs(id) {
    if (visiting.has(id)) {
      const cycleStart = stack.indexOf(id);
      const cycle = [...stack.slice(cycleStart), id].join(' -> ');
      errors.push(`dependency cycle detected: ${cycle}`);
      return;
    }
    if (visited.has(id)) return;
    visiting.add(id);
    stack.push(id);
    for (const dep of graph.get(id) || []) {
      if (ids.has(dep)) dfs(dep);
    }
    stack.pop();
    visiting.delete(id);
    visited.add(id);
  }

  for (const id of ids) dfs(id);
}

const raw = readFileSync(filePath, 'utf8');
const tasks = parsePlanTasks(raw, section);
const errors = [];
if (!tasks.length) {
  errors.push(`${section} must contain at least one task`);
}

if (section === 'tasks' && parseTopLevelList(raw, 'global_acceptance').length === 0) {
  errors.push('tasks plan must include top-level global_acceptance');
}

for (const [index, task] of tasks.entries()) {
  const label = task.id || `${section} entry ${index + 1}`;
  if (!task.id) errors.push(`${label} missing id`);
  if (!task.type || !TASK_TYPES.includes(String(task.type))) errors.push(`${label} type must be one of: ${TASK_TYPES.join(', ')}`);
  if (!task.risk || !RISK_LEVELS.includes(String(task.risk))) errors.push(`${label} risk must be one of: ${RISK_LEVELS.join(', ')}`);
  if (!task.source) errors.push(`${label} missing source`);

  for (const key of ['allowed_paths', 'forbidden_paths']) {
    if (!Array.isArray(task[key]) || task[key].length === 0) {
      errors.push(`${label} ${key} must be a non-empty array`);
      continue;
    }
    for (const boundaryPath of task[key]) {
      if (!isSafeBoundaryPath(boundaryPath)) errors.push(`${label} ${key} contains unsafe path: ${boundaryPath}`);
    }
  }

  for (const key of ['acceptance', 'verify', 'review_focus']) {
    if (!hasNonEmptyPlanField(task[key])) errors.push(`${label} missing ${key}`);
  }
}

validateDependencyGraph(tasks, errors);

if (errors.length) fail(errors.join('\n'));
console.log(`valid ${section}: ${filePath}`);
