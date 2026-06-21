import { existsSync, readFileSync } from 'node:fs';

const filePath = process.argv[2];
const sectionArgIndex = process.argv.indexOf('--section');
const section = sectionArgIndex === -1 ? 'tasks' : process.argv[sectionArgIndex + 1];

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

function isBlockScalarStart(trimmed) {
  return /^([A-Za-z_][\w-]*|-[ \t]+[A-Za-z_][\w-]*):\s*[|>][+-]?(?:\s+#.*)?$/.test(trimmed);
}

function skipBlockScalar(lines, startIndex, baseIndent) {
  let index = startIndex + 1;
  for (; index < lines.length; index += 1) {
    const line = lines[index];
    if (!line.trim()) continue;
    const indent = line.length - line.trimStart().length;
    if (indent <= baseIndent) break;
  }
  return index - 1;
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
    if (isBlockScalarStart(trimmed)) {
      index = skipBlockScalar(lines, index, indent);
      continue;
    }
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
    const idMatch = content.match(/^-\s+id:\s*(.+)$/);
    if (idMatch) {
      current = { id: unquote(idMatch[1]), allowed_paths: [], forbidden_paths: [] };
      tasks.push(current);
      continue;
    }
    if (!current) continue;
    const keyMatch = content.match(/^([A-Za-z_][\w-]*):\s*(.*)$/);
    if (!keyMatch) continue;
    const [, key, value] = keyMatch;
    if (key === 'allowed_paths' || key === 'forbidden_paths') {
      current[key] = parseInlineList(value) ?? extractList(lines, index, indent);
    } else {
      const inlineList = parseInlineList(value);
      if (inlineList) {
        current[key] = inlineList;
      } else if (!stripYamlComment(value).trim()) {
        const list = extractList(lines, index, indent);
        current[key] = list.length ? list : '';
      } else {
        current[key] = unquote(value);
      }
    }
  }
  return tasks;
}

const tasks = parsePlanTasks(readFileSync(filePath, 'utf8'), section);
const errors = [];
if (!tasks.length) {
  errors.push(`${section} must contain at least one task`);
}
for (const task of tasks) {
  if (!task.id) errors.push(`${section} entry missing id`);
  if (!Array.isArray(task.allowed_paths) || task.allowed_paths.length === 0) errors.push(`${task.id || '<unknown>'} allowed_paths must be non-empty`);
  if (!Array.isArray(task.forbidden_paths) || task.forbidden_paths.length === 0) errors.push(`${task.id || '<unknown>'} forbidden_paths must be non-empty`);
  if (section === 'tasks') {
    for (const key of ['acceptance', 'verify', 'review_focus']) {
      if (!task[key]) errors.push(`${task.id || '<unknown>'} missing ${key}`);
    }
  }
}

if (errors.length) fail(errors.join('\n'));
console.log(`valid ${section}: ${filePath}`);
