import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtempSync, mkdirSync, readFileSync, writeFileSync, existsSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { spawnSync } from 'node:child_process';

const repoRoot = path.resolve(import.meta.dirname, '../../..');
const guardScript = path.join(repoRoot, 'plugins/nuclio/hooks/guard.mjs');
const eventLogScript = path.join(repoRoot, 'plugins/nuclio/hooks/event-log.mjs');
const writeStateScript = path.join(repoRoot, 'plugins/nuclio/scripts/write-state.mjs');
const appendEventScript = path.join(repoRoot, 'plugins/nuclio/scripts/append-event.mjs');
const validateEventScript = path.join(repoRoot, 'plugins/nuclio/scripts/validate-event.mjs');
const bootstrapCheckScript = path.join(repoRoot, 'plugins/nuclio/scripts/bootstrap-check.mjs');
const validatePlanScript = path.join(repoRoot, 'plugins/nuclio/scripts/validate-plan.mjs');
const validateContextReportScript = path.join(repoRoot, 'plugins/nuclio/scripts/validate-context-report.mjs');
const validateMemoryPatchScript = path.join(repoRoot, 'plugins/nuclio/scripts/validate-memory-patch.mjs');
const validateStateScript = path.join(repoRoot, 'plugins/nuclio/scripts/validate-state.mjs');

function workspace() {
  return mkdtempSync(path.join(tmpdir(), 'nuclio-smoke-'));
}

function writeJson(filePath, value) {
  mkdirSync(path.dirname(filePath), { recursive: true });
  writeFileSync(filePath, `${JSON.stringify(value, null, 2)}\n`);
}

function runNode(script, args = [], { cwd = workspace(), env = {} } = {}) {
  return spawnSync(process.execPath, [script, ...args], {
    cwd,
    env: { ...process.env, ...env },
    encoding: 'utf8',
  });
}

function runGuard(cwd, tool, toolInput) {
  return runNode(guardScript, [], {
    cwd,
    env: {
      CLAUDE_TOOL_NAME: tool,
      CLAUDE_TOOL_INPUT: typeof toolInput === 'string' ? toolInput : JSON.stringify(toolInput),
    },
  });
}

function assertBlocked(result, messageIncludes = 'Blocked:') {
  assert.notEqual(result.status, 0, `expected command to be blocked, stdout=${result.stdout} stderr=${result.stderr}`);
  assert.match(result.stderr, new RegExp(messageIncludes.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')));
}

function assertAllowed(result) {
  assert.equal(result.status, 0, `expected command to be allowed, stdout=${result.stdout} stderr=${result.stderr}`);
}

function projectState(overrides = {}) {
  return {
    workflow: 'project_initialization',
    phase: 'initial_dev_docs',
    status: 'active',
    gate: null,
    approved: {
      foundation: true,
      architecture: true,
      scaffold: true,
      initial_dev_docs: true,
    },
    blocking_reason: null,
    updated_at: '2026-06-18T00:00:00.000Z',
    ...overrides,
  };
}

function changeState(overrides = {}) {
  return {
    workflow: 'change',
    phase: 'build',
    status: 'active',
    gate: null,
    current_task: 'T1',
    build_iteration: 0,
    approved: {
      spec: true,
      design: true,
      final: false,
      memory: false,
    },
    blocking_reason: null,
    updated_at: '2026-06-18T00:00:00.000Z',
    ...overrides,
  };
}

function writePlan(cwd, changeId = 'c1') {
  const plan = `tasks:\n  - id: T1\n    allowed_paths: [src/**]\n    forbidden_paths: [src/secret/**]\n    acceptance: done\n    verify: node --check src/a.mjs\n    review_focus: scope\n`;
  const planPath = path.join(cwd, `.nuclio/changes/${changeId}/plan.yaml`);
  mkdirSync(path.dirname(planPath), { recursive: true });
  writeFileSync(planPath, plan);
}

test('historical .dev-docs approval does not globally authorize future writes', () => {
  const cwd = workspace();
  writeJson(path.join(cwd, '.nuclio/project/init-state.json'), projectState({ status: 'done', phase: 'done' }));

  const result = runGuard(cwd, 'Write', { file_path: '.dev-docs/unrelated.md', content: 'x' });

  assertBlocked(result, 'writing .dev-docs requires canonical Nucl.io approval state');
});

test('project initial dev docs approval is scoped to approved target paths', () => {
  const cwd = workspace();
  writeJson(path.join(cwd, '.nuclio/project/init-state.json'), projectState({
    approved: {
      foundation: true,
      architecture: true,
      scaffold: true,
      initial_dev_docs: true,
      initial_dev_docs_scope: { target_paths: ['.dev-docs/index.md'] },
    },
  }));

  assertAllowed(runGuard(cwd, 'Write', { file_path: '.dev-docs/index.md', content: 'x' }));
  assertBlocked(runGuard(cwd, 'Write', { file_path: '.dev-docs/other.md', content: 'x' }), 'writing .dev-docs requires canonical Nucl.io approval state');
});

test('memory approval is scoped by memory.patch.md accept/edit targets', () => {
  const cwd = workspace();
  writeJson(path.join(cwd, '.nuclio/changes/c1/state.json'), changeState({
    phase: 'close',
    current_task: null,
    approved: { spec: true, design: true, final: true, memory: true },
  }));
  writeFileSync(path.join(cwd, '.nuclio/changes/c1/memory.patch.md'), '| id | target | decision |\n| --- | --- | --- |\n| U1 | .dev-docs/accepted.md | accept |\n| U2 | .dev-docs/edited.md | edit |\n| U3 | .dev-docs/rejected.md | reject |\n');

  assertAllowed(runGuard(cwd, 'Write', { file_path: '.dev-docs/accepted.md', content: 'x' }));
  assertAllowed(runGuard(cwd, 'Write', { file_path: '.dev-docs/edited.md', content: 'x' }));
  assertBlocked(runGuard(cwd, 'Write', { file_path: '.dev-docs/rejected.md', content: 'x' }), 'writing .dev-docs requires canonical Nucl.io approval state');
});

test('invalid Nuclio state files fail closed for application and .dev-docs writes', () => {
  const cwd = workspace();
  mkdirSync(path.join(cwd, '.nuclio/changes/c1'), { recursive: true });
  writeFileSync(path.join(cwd, '.nuclio/changes/c1/state.json'), '{ invalid json');

  assertBlocked(runGuard(cwd, 'Write', { file_path: 'src/a.mjs', content: 'x' }), 'invalid Nuclio state file .nuclio/changes/c1/state.json');
  assertBlocked(runGuard(cwd, 'Write', { file_path: '.dev-docs/index.md', content: 'x' }), 'invalid Nuclio state file .nuclio/changes/c1/state.json');
});

test('schema-invalid Nuclio change state files fail closed for application writes', () => {
  const cwd = workspace();
  writeJson(path.join(cwd, '.nuclio/changes/c1/state.json'), {
    workflow: 'invalid',
    phase: 'build',
    status: 'active',
    gate: null,
    updated_at: '2026-06-18T00:00:00.000Z',
  });

  assertBlocked(
    runGuard(cwd, 'Write', { file_path: 'src/a.mjs', content: 'x' }),
    'Blocked: invalid Nuclio state file .nuclio/changes/c1/state.json.',
  );
});

test('Bash write-like commands with known targets use plan boundaries', () => {
  const cwd = workspace();
  writeJson(path.join(cwd, '.nuclio/changes/c1/state.json'), changeState());
  writePlan(cwd);

  const allowedCommands = [
    "sed -i 's/a/b/' src/a.mjs",
    "perl -pi -e 's/a/b/' src/a.mjs",
    'cp src/a.mjs src/b.mjs',
    'mv src/a.mjs src/b.mjs',
    'install src/a.mjs src/b.mjs',
    'touch src/a.mjs',
    'mkdir -p src/generated',
  ];

  for (const command of allowedCommands) {
    assertAllowed(runGuard(cwd, 'Bash', { command }));
  }

  const blocked = runGuard(cwd, 'Bash', { command: "sed -i 's/a/b/' tests/a.ts" });
  assertBlocked(blocked, 'outside task T1 allowed_paths');
  const events = readFileSync(path.join(cwd, '.nuclio/changes/c1/events.jsonl'), 'utf8').trim().split('\n').map((line) => JSON.parse(line));
  assert.equal(events.at(-1).type, 'operation.blocked');
  assert.equal(events.at(-1).result, 'blocked');
  assert.deepEqual(events.at(-1).target_paths, ['tests/a.ts']);
});

test('active Nuclio workflow allows controlled helper target extraction', () => {
  const cwd = workspace();
  writeJson(path.join(cwd, '.nuclio/changes/c1/state.json'), changeState());
  writePlan(cwd);

  const writeStateCommand = `node plugins/nuclio/scripts/write-state.mjs .nuclio/changes/c1/state.json '${JSON.stringify(changeState())}'`;
  const appendEventCommand = `node plugins/nuclio/scripts/append-event.mjs .nuclio/changes/c1/events.jsonl '${JSON.stringify({ type: 'task.started', tool: 'Bash', artifact: null, result: 'unknown' })}'`;

  assertAllowed(runGuard(cwd, 'Bash', { command: writeStateCommand }));
  assertAllowed(runGuard(cwd, 'Bash', { command: appendEventCommand }));
});

test('active Nuclio workflow blocks arbitrary node scripts as ambiguous', () => {
  const cwd = workspace();
  writeJson(path.join(cwd, '.nuclio/changes/c1/state.json'), changeState());
  writePlan(cwd);

  assertBlocked(runGuard(cwd, 'Bash', { command: 'node scripts/write.js' }), 'ambiguous Bash command in active Nuclio workflow');
});

test('active Nuclio workflow blocks ambiguous Bash write-like commands without known targets', () => {
  const cwd = workspace();
  writeJson(path.join(cwd, '.nuclio/changes/c1/state.json'), changeState());
  writePlan(cwd);

  const commands = [
    'python scripts/update.py',
    'node scripts/update.mjs',
  ];

  for (const command of commands) {
    assertBlocked(runGuard(cwd, 'Bash', { command }), 'ambiguous Bash command in active Nuclio workflow');
  }
});

test('dangerous Bash can be allowed only by current_workflow scoped risk approval', () => {
  const cwd = workspace();
  writePlan(cwd);

  writeJson(path.join(cwd, '.nuclio/changes/c1/state.json'), changeState({
    risk_approvals: [
      { approved: true, scope: 'current_workflow', command_pattern: 'contains:git push origin feature/add-nuclio', expires_at: null },
    ],
  }));
  assertAllowed(runGuard(cwd, 'Bash', { command: 'git push origin feature/add-nuclio' }));
  assertBlocked(runGuard(cwd, 'Bash', { command: 'git push origin main' }), 'dangerous bash command requires human approval');

  writeJson(path.join(cwd, '.nuclio/changes/c1/state.json'), changeState({
    risk_approvals: [
      { approved: true, command_pattern: 'contains:git push origin feature/add-nuclio', expires_at: null },
    ],
  }));
  assertBlocked(runGuard(cwd, 'Bash', { command: 'git push origin feature/add-nuclio' }), 'dangerous bash command requires human approval');

  writeJson(path.join(cwd, '.nuclio/changes/c1/state.json'), changeState({
    risk_approvals: [
      { approved: true, scope: 'global', command_pattern: 'contains:git push origin feature/add-nuclio', expires_at: null },
    ],
  }));
  assertBlocked(runGuard(cwd, 'Bash', { command: 'git push origin feature/add-nuclio' }), 'dangerous bash command requires human approval');
});

test('write-state validates state before writing target', () => {
  const cwd = workspace();
  const target = '.nuclio/changes/c1/state.json';
  const invalid = JSON.stringify({ workflow: 'change', phase: 'build' });
  const result = runNode(writeStateScript, [target, invalid], { cwd });

  assert.notEqual(result.status, 0);
  assert.equal(existsSync(path.join(cwd, target)), false, 'invalid state must not be written');
});

test('write-state rejects targets outside allowed Nuclio state files', () => {
  const cwd = workspace();
  const valid = JSON.stringify(changeState());
  const outsideTarget = `../${path.basename(cwd)}-outside.json`;

  assert.notEqual(runNode(writeStateScript, [outsideTarget, valid], { cwd }).status, 0);
  assert.notEqual(runNode(writeStateScript, ['.nuclio/other/state.json', valid], { cwd }).status, 0);
  assert.equal(existsSync(path.resolve(cwd, outsideTarget)), false, 'outside target must not be written');
  assert.equal(existsSync(path.join(cwd, '.nuclio/other/state.json')), false, 'non-state target must not be written');
});

test('append-event validates event payload and limits target path', () => {
  const cwd = workspace();
  const validEvent = JSON.stringify({ type: 'task.verified', tool: 'Bash', artifact: '.nuclio/changes/c1/evidence/verify.md', task_id: 'T1', result: 'pass', target_paths: ['src/a.mjs'] });
  const invalidEvent = JSON.stringify({ type: '', tool: 42, artifact: '.nuclio/changes/c1/evidence/verify.md' });

  assert.equal(runNode(appendEventScript, ['.nuclio/changes/c1/events.jsonl', validEvent], { cwd }).status, 0);
  assert.notEqual(runNode(appendEventScript, ['events.jsonl', validEvent], { cwd }).status, 0);
  assert.notEqual(runNode(appendEventScript, ['.nuclio/changes/c1/events.jsonl', invalidEvent], { cwd }).status, 0);
  assert.equal(runNode(validateEventScript, ['.nuclio/changes/c1/events.jsonl'], { cwd }).status, 0);
});

test('event validator enforces planned result and decision enums', () => {
  const cwd = workspace();
  const valid = JSON.stringify({ type: 'decision.recorded', tool: null, artifact: null, result: 'pass', decision: 'accept' });
  const invalidResult = JSON.stringify({ type: 'task.verified', tool: 'Bash', artifact: null, result: 'passed' });
  const invalidDecision = JSON.stringify({ type: 'decision.recorded', tool: null, artifact: null, decision: 'approved' });

  assert.equal(runNode(validateEventScript, [valid], { cwd }).status, 0);
  assert.notEqual(runNode(validateEventScript, [invalidResult], { cwd }).status, 0);
  assert.notEqual(runNode(validateEventScript, [invalidDecision], { cwd }).status, 0);
});

test('validate-state requires risk approval scope to be current_workflow', () => {
  const cwd = workspace();
  const validStatePath = path.join(cwd, 'valid-state.json');
  const missingScopePath = path.join(cwd, 'missing-scope.json');
  const wrongScopePath = path.join(cwd, 'wrong-scope.json');

  writeJson(validStatePath, changeState({
    risk_approvals: [{ approved: true, scope: 'current_workflow', command_pattern: 'contains:git push', expires_at: null }],
  }));
  writeJson(missingScopePath, changeState({
    risk_approvals: [{ approved: true, command_pattern: 'contains:git push', expires_at: null }],
  }));
  writeJson(wrongScopePath, changeState({
    risk_approvals: [{ approved: true, scope: 'global', command_pattern: 'contains:git push', expires_at: null }],
  }));

  assert.equal(runNode(validateStateScript, [validStatePath], { cwd }).status, 0);
  assert.notEqual(runNode(validateStateScript, [missingScopePath], { cwd }).status, 0);
  assert.notEqual(runNode(validateStateScript, [wrongScopePath], { cwd }).status, 0);
});

test('guard and event-log append operation.blocked events', () => {
  const cwd = workspace();
  writeJson(path.join(cwd, '.nuclio/changes/c1/state.json'), changeState());
  writePlan(cwd);

  const blocked = runGuard(cwd, 'Write', { file_path: 'tests/a.mjs', content: 'x' });
  assertBlocked(blocked, 'outside task T1 allowed_paths');
  const events = readFileSync(path.join(cwd, '.nuclio/changes/c1/events.jsonl'), 'utf8').trim().split('\n').map((line) => JSON.parse(line));
  assert.equal(events.at(-1).type, 'operation.blocked');
  assert.equal(events.at(-1).tool, 'Write');
  assert.deepEqual(events.at(-1).target_paths, ['tests/a.mjs']);

  const post = runNode(eventLogScript, [], {
    cwd,
    env: {
      CLAUDE_TOOL_NAME: 'Bash',
      CLAUDE_TOOL_INPUT: JSON.stringify({ command: 'echo x > src/a.mjs' }),
      CLAUDE_TOOL_OUTPUT: 'Blocked: example failure',
    },
  });
  assert.equal(post.status, 0);
  const updatedEvents = readFileSync(path.join(cwd, '.nuclio/changes/c1/events.jsonl'), 'utf8').trim().split('\n').map((line) => JSON.parse(line));
  assert.equal(updatedEvents.at(-1).type, 'operation.blocked');
  assert.equal(updatedEvents.at(-1).result, 'blocked');
});

test('event-log infers task_id from task-scoped evidence path', () => {
  const cwd = workspace();
  const artifact = '.nuclio/changes/c1/evidence/T1/verify.md';

  const post = runNode(eventLogScript, [], {
    cwd,
    env: {
      CLAUDE_TOOL_NAME: 'Write',
      CLAUDE_TOOL_INPUT: JSON.stringify({ file_path: artifact, content: '# Verify\n' }),
      CLAUDE_TOOL_OUTPUT: 'success',
    },
  });

  assert.equal(post.status, 0, `expected event-log to succeed, stdout=${post.stdout} stderr=${post.stderr}`);
  assert.equal(JSON.parse(post.stdout).task_id, 'T1');
  const events = readFileSync(path.join(cwd, '.nuclio/changes/c1/events.jsonl'), 'utf8').trim().split('\n').map((line) => JSON.parse(line));
  assert.equal(events.at(-1).task_id, 'T1');
});

test('event-log normalizes absolute target_paths to safe relative paths that validate', () => {
  const cwd = workspace();
  writeJson(path.join(cwd, '.nuclio/changes/c1/state.json'), changeState());
  const insideTarget = path.join(cwd, 'src/a.mjs');
  const outsideTarget = path.resolve(cwd, '../outside.mjs');

  const post = runNode(eventLogScript, [], {
    cwd,
    env: {
      CLAUDE_TOOL_NAME: 'Write',
      CLAUDE_TOOL_INPUT: JSON.stringify({ file_path: insideTarget, backup_path: outsideTarget }),
      CLAUDE_TOOL_OUTPUT: 'success',
    },
  });

  assert.equal(post.status, 0, `expected event-log to succeed, stdout=${post.stdout} stderr=${post.stderr}`);
  const event = JSON.parse(post.stdout);
  assert.deepEqual(event.target_paths, ['src/a.mjs']);
  assert.equal(runNode(validateEventScript, [JSON.stringify(event)], { cwd }).status, 0);
  assert.equal(runNode(validateEventScript, ['.nuclio/changes/c1/events.jsonl'], { cwd }).status, 0);
});

test('workflow helper validators accept minimal valid artifacts and reject invalid ones', () => {
  const cwd = workspace();
  writeJson(path.join(cwd, '.nuclio/project/init-state.json'), projectState());
  mkdirSync(path.join(cwd, '.dev-docs'), { recursive: true });
  writeFileSync(path.join(cwd, '.dev-docs/index.md'), '# Dev Docs\n');
  writeJson(path.join(cwd, '.nuclio/changes/c1/state.json'), changeState({ status: 'done' }));
  writeJson(path.join(cwd, '.nuclio/changes/c2/state.json'), changeState({ status: 'active' }));

  const bootstrap = runNode(bootstrapCheckScript, [], { cwd });
  assert.equal(bootstrap.status, 0);
  const bootstrapJson = JSON.parse(bootstrap.stdout);
  assert.equal(bootstrapJson.ok, true);
  assert.equal(bootstrapJson.foundation, 'ready');
  assert.equal(bootstrapJson.next_action, 'continue_current_change');
  assert.equal(bootstrapJson.active_changes.length, 1);

  const planPath = path.join(cwd, '.nuclio/changes/c2/plan.yaml');
  writePlan(cwd, 'c2');
  assert.equal(runNode(validatePlanScript, [planPath, '--section', 'tasks'], { cwd }).status, 0);
  assert.equal(runNode(validatePlanScript, [path.join(repoRoot, 'plugins/nuclio/skills/design/templates/plan-template.yaml'), '--section', 'tasks'], { cwd }).status, 0);
  assert.equal(runNode(validatePlanScript, [path.join(repoRoot, 'plugins/nuclio/skills/project-init/templates/scaffold-plan-template.yaml'), '--section', 'scaffold_tasks'], { cwd }).status, 0);

  const contextReport = path.join(cwd, '.nuclio/changes/c2/context-report.md');
  writeFileSync(contextReport, '# Context Report\n\n.dev-docs/index.md\n\n## Loaded\n- .dev-docs/index.md — reason: relevant\n\n## Skipped\n- .dev-docs/old.md — reason: stale\n\nmissing: none\nstale: .dev-docs/old.md\nnot applicable: none\n');
  assert.equal(runNode(validateContextReportScript, [contextReport], { cwd }).status, 0);

  const memoryPatch = path.join(cwd, '.nuclio/changes/c2/memory.patch.md');
  writeFileSync(memoryPatch, '| id | target | decision |\n| --- | --- | --- |\n| U1 | .dev-docs/index.md | accept |\n| U2 | .dev-docs/topic.md | defer |\n');
  assert.equal(runNode(validateMemoryPatchScript, [memoryPatch], { cwd }).status, 0);
  assert.equal(runNode(validateMemoryPatchScript, [path.join(repoRoot, 'plugins/nuclio/skills/close/templates/memory-patch-template.md')], { cwd }).status, 0);
  assert.equal(runNode(validateMemoryPatchScript, [path.join(repoRoot, 'plugins/nuclio/skills/project-init/templates/initial-dev-docs-patch-template.md')], { cwd }).status, 0);

  writeFileSync(memoryPatch, '| id | target | decision |\n| --- | --- | --- |\n| U1 | README.md | accept |\n');
  assert.notEqual(runNode(validateMemoryPatchScript, [memoryPatch], { cwd }).status, 0);
});
