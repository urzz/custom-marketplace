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
const validateDevDocsIndexScript = path.join(repoRoot, 'plugins/nuclio/scripts/validate-dev-docs-index.mjs');
const validateContextReportScript = path.join(repoRoot, 'plugins/nuclio/scripts/validate-context-report.mjs');
const validateMemoryPatchScript = path.join(repoRoot, 'plugins/nuclio/scripts/validate-memory-patch.mjs');
const validateStateScript = path.join(repoRoot, 'plugins/nuclio/scripts/validate-state.mjs');
const projectInitStateTemplate = path.join(repoRoot, 'plugins/nuclio/skills/project-init/templates/init-state-template.json');
const specStateTemplate = path.join(repoRoot, 'plugins/nuclio/skills/spec/templates/state-template.json');
const contextReportTemplate = path.join(repoRoot, 'plugins/nuclio/skills/spec/templates/context-report-template.md');
const pluginManifestPath = path.join(repoRoot, 'plugins/nuclio/.claude-plugin/plugin.json');
const browserVerifierPath = path.join(repoRoot, 'plugins/nuclio/agents/browser-verifier.md');
const nuclioSkillFiles = [
  ['project-init', path.join(repoRoot, 'plugins/nuclio/skills/project-init/SKILL.md')],
  ['spec', path.join(repoRoot, 'plugins/nuclio/skills/spec/SKILL.md')],
  ['design', path.join(repoRoot, 'plugins/nuclio/skills/design/SKILL.md')],
  ['build', path.join(repoRoot, 'plugins/nuclio/skills/build/SKILL.md')],
  ['close', path.join(repoRoot, 'plugins/nuclio/skills/close/SKILL.md')],
  ['resume', path.join(repoRoot, 'plugins/nuclio/skills/resume/SKILL.md')],
  ['apply-memory', path.join(repoRoot, 'plugins/nuclio/skills/apply-memory/SKILL.md')],
];

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

function pluginRootCommand(scriptName) {
  return `node "$CLAUDE_PLUGIN_ROOT/scripts/${scriptName}"`;
}

function escapeRegExp(value) {
  return String(value).replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

function assertSkillUsesPluginRootHelper(content, skillName, scriptName) {
  const command = pluginRootCommand(scriptName);
  assert.match(content, new RegExp(escapeRegExp(command)));
  if (scriptName === 'bootstrap-check.mjs') {
    assert.match(content, new RegExp(`${escapeRegExp(command)} --requested-skill ${escapeRegExp(skillName)}`));
  }
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
  const plan = `tasks:\n  - id: T1\n    type: implementation\n    risk: low\n    depends_on: []\n    source: spec.md#acceptance\n    allowed_paths: [src/**]\n    forbidden_paths: [src/secret/**]\n    acceptance: done\n    verify: node --check src/a.mjs\n    review_focus: scope\nglobal_acceptance:\n  - all task acceptance criteria are satisfied\n`;
  const planPath = path.join(cwd, `.nuclio/changes/${changeId}/plan.yaml`);
  mkdirSync(path.dirname(planPath), { recursive: true });
  writeFileSync(planPath, plan);
}

test('Nuclio skill helper commands are plugin-root aware', () => {
  const requiredHelpersBySkill = new Map([
    ['project-init', ['bootstrap-check.mjs', 'write-state.mjs', 'append-event.mjs']],
    ['spec', ['bootstrap-check.mjs', 'validate-context-report.mjs', 'write-state.mjs', 'append-event.mjs']],
    ['design', ['bootstrap-check.mjs', 'validate-plan.mjs', 'write-state.mjs', 'append-event.mjs']],
    ['build', ['bootstrap-check.mjs', 'validate-plan.mjs', 'write-state.mjs', 'append-event.mjs']],
    ['close', ['bootstrap-check.mjs', 'validate-context-report.mjs', 'validate-memory-patch.mjs', 'write-state.mjs', 'append-event.mjs']],
    ['resume', ['bootstrap-check.mjs']],
    ['apply-memory', ['bootstrap-check.mjs', 'validate-memory-patch.mjs', 'append-event.mjs']],
  ]);

  for (const [skillName, skillPath] of nuclioSkillFiles) {
    const content = readFileSync(skillPath, 'utf8');
    assert.doesNotMatch(content, /node\s+plugins\/nuclio\/scripts\/[A-Za-z0-9-]+\.mjs/);
    for (const helperName of requiredHelpersBySkill.get(skillName)) {
      assertSkillUsesPluginRootHelper(content, skillName, helperName);
    }
  }
});

test('guard recognizes controlled helpers from plugin-root, absolute, and development paths', () => {
  const cwd = workspace();
  writeJson(path.join(cwd, '.nuclio/changes/c1/state.json'), changeState());
  writePlan(cwd);

  const helperScripts = [
    ['state', 'write-state.mjs', '.nuclio/changes/c1/state.json', JSON.stringify(changeState())],
    ['events', 'append-event.mjs', '.nuclio/changes/c1/events.jsonl', JSON.stringify({ type: 'task.started', tool: 'Bash', artifact: null, result: 'unknown' })],
  ];

  for (const [_kind, helperName, target, payload] of helperScripts) {
    const scriptForms = [
      `$CLAUDE_PLUGIN_ROOT/scripts/${helperName}`,
      `\${CLAUDE_PLUGIN_ROOT}/scripts/${helperName}`,
      path.join(repoRoot, 'plugins/nuclio/scripts', helperName),
      `plugins/nuclio/scripts/${helperName}`,
    ];

    for (const scriptForm of scriptForms) {
      assertAllowed(runGuard(cwd, 'Bash', { command: `node ${scriptForm} ${target} '${payload}'` }));
    }
  }
});

test('guard blocks controlled helper lookalike paths and side-effectful node options', () => {
  const cwd = workspace();
  writeJson(path.join(cwd, '.nuclio/changes/c1/state.json'), changeState());
  writePlan(cwd);

  const statePayload = JSON.stringify(changeState());
  const eventPayload = JSON.stringify({ type: 'task.started', tool: 'Bash', artifact: null, result: 'unknown' });

  const blockedCommands = [
    `node /tmp/plugins/nuclio/scripts/write-state.mjs .nuclio/changes/c1/state.json '${statePayload}'`,
    `node /tmp/$CLAUDE_PLUGIN_ROOT/scripts/write-state.mjs .nuclio/changes/c1/state.json '${statePayload}'`,
    `node --require=/tmp/evil.cjs "$CLAUDE_PLUGIN_ROOT/scripts/write-state.mjs" .nuclio/changes/c1/state.json '${statePayload}'`,
    `NODE_OPTIONS=--require=/tmp/evil.cjs node "$CLAUDE_PLUGIN_ROOT/scripts/write-state.mjs" .nuclio/changes/c1/state.json '${statePayload}'`,
    `node /tmp/plugins/nuclio/scripts/append-event.mjs .nuclio/changes/c1/events.jsonl '${eventPayload}'`,
  ];

  for (const command of blockedCommands) {
    assertBlocked(runGuard(cwd, 'Bash', { command }));
  }
});

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
  writeFileSync(path.join(cwd, '.nuclio/changes/c1/memory.patch.md'), `# Memory Patch: c1

## Proposed Updates

| id | target | operation | reason | confidence |
| --- | --- | --- | --- | --- |
| U1 | .dev-docs/accepted.md | update | Accept target | high |
| U2 | .dev-docs/edited.md | update | Edit target | high |
| U3 | .dev-docs/rejected.md | update | Reject target | high |

### Update U1

- id: U1
- target: .dev-docs/accepted.md
- operation: update
- reason: Accept target
- confidence: high

\`\`\`diff
--- before
+++ after
@@
- old
+ new
\`\`\`

### Update U2

- id: U2
- target: .dev-docs/edited.md
- operation: update
- reason: Edit target
- confidence: high

\`\`\`diff
--- before
+++ after
@@
- old
+ new
\`\`\`

### Update U3

- id: U3
- target: .dev-docs/rejected.md
- operation: update
- reason: Reject target
- confidence: high

\`\`\`diff
--- before
+++ after
@@
- old
+ new
\`\`\`

## Human Approval Decisions

| id | decision | approved_content_ref | note |
| --- | --- | --- | --- |
| U1 | accept | Update U1 | approved |
| U2 | edit | Update U2 | edited |
| U3 | reject |  | rejected |
`);

  assertAllowed(runGuard(cwd, 'Write', { file_path: '.dev-docs/accepted.md', content: 'x' }));
  assertAllowed(runGuard(cwd, 'Write', { file_path: '.dev-docs/edited.md', content: 'x' }));
  assertBlocked(runGuard(cwd, 'Write', { file_path: '.dev-docs/rejected.md', content: 'x' }), 'writing .dev-docs requires canonical Nucl.io approval state');
});

test('guard ignores accept/edit memory approvals without valid approved_content_ref', () => {
  const cwd = workspace();
  writeJson(path.join(cwd, '.nuclio/changes/c1/state.json'), changeState({
    phase: 'close',
    current_task: null,
    approved: { spec: true, design: true, final: true, memory: true },
  }));
  writeFileSync(path.join(cwd, '.nuclio/changes/c1/memory.patch.md'), `# Memory Patch: c1

## Proposed Updates

| id | target | operation | reason | confidence |
| --- | --- | --- | --- | --- |
| U1 | .dev-docs/empty-ref.md | update | Empty ref must not authorize | high |
| U2 | .dev-docs/bogus-ref.md | update | Bogus ref must not authorize | high |

### Update U1

- id: U1
- target: .dev-docs/empty-ref.md
- operation: update
- reason: Empty ref must not authorize
- confidence: high

\`\`\`diff
--- before
+++ after
@@
- old
+ new
\`\`\`

### Update U2

- id: U2
- target: .dev-docs/bogus-ref.md
- operation: update
- reason: Bogus ref must not authorize
- confidence: high

\`\`\`diff
--- before
+++ after
@@
- old
+ new
\`\`\`

## Human Approval Decisions

| id | decision | approved_content_ref | note |
| --- | --- | --- | --- |
| U1 | accept |  | empty ref |
| U2 | edit | Update missing | bogus ref |
`);

  assertBlocked(runGuard(cwd, 'Write', { file_path: '.dev-docs/empty-ref.md', content: 'x' }), 'writing .dev-docs requires canonical Nucl.io approval state');
  assertBlocked(runGuard(cwd, 'Write', { file_path: '.dev-docs/bogus-ref.md', content: 'x' }), 'writing .dev-docs requires canonical Nucl.io approval state');
});

function memoryPatchWithTarget(target) {
  return `# Memory Patch: c1

## Proposed Updates

| id | target | operation | reason | confidence |
| --- | --- | --- | --- | --- |
| U1 | ${target} | update | Target must be a concrete file path | high |

### Update U1

- id: U1
- target: ${target}
- operation: update
- reason: Target must be a concrete file path
- confidence: high

\`\`\`diff
--- before
+++ after
@@
- old
+ new
\`\`\`

## Human Approval Decisions

| id | decision | approved_content_ref | note |
| --- | --- | --- | --- |
| U1 | accept | Update U1 | approved |
`;
}

test('memory patch validator rejects glob targets', () => {
  const cwd = workspace();
  const memoryPatch = path.join(cwd, 'memory.patch.md');
  writeFileSync(memoryPatch, memoryPatchWithTarget('.dev-docs/**'));

  assert.notEqual(runNode(validateMemoryPatchScript, [memoryPatch], { cwd }).status, 0, 'glob targets must be rejected');
});

test('memory patch validator rejects directory targets', () => {
  const cwd = workspace();
  const memoryPatch = path.join(cwd, 'memory.patch.md');
  writeFileSync(memoryPatch, memoryPatchWithTarget('.dev-docs/topic/'));

  assert.notEqual(runNode(validateMemoryPatchScript, [memoryPatch], { cwd }).status, 0, 'directory targets must be rejected');
});

test('memory patch validator rejects traversal targets before normalization', () => {
  const cwd = workspace();
  const memoryPatch = path.join(cwd, 'memory.patch.md');
  writeFileSync(memoryPatch, memoryPatchWithTarget('.dev-docs/topic/../bar.md'));

  assert.notEqual(runNode(validateMemoryPatchScript, [memoryPatch], { cwd }).status, 0, 'traversal targets must be rejected');
});

test('guard rejects approved memory patch targets with traversal before normalization', () => {
  const cwd = workspace();
  writeJson(path.join(cwd, '.nuclio/changes/c1/state.json'), changeState({
    phase: 'close',
    current_task: null,
    approved: { spec: true, design: true, final: true, memory: true },
  }));
  writeFileSync(path.join(cwd, '.nuclio/changes/c1/memory.patch.md'), memoryPatchWithTarget('.dev-docs/topic/../bar.md'));

  assertBlocked(runGuard(cwd, 'Write', { file_path: '.dev-docs/bar.md', content: 'x' }), 'writing .dev-docs requires canonical Nucl.io approval state');
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

test('active Nuclio workflow allows plugin-root bootstrap-check for read-only workflow entry checks', () => {
  const cwd = workspace();
  writeJson(path.join(cwd, '.nuclio/changes/c1/state.json'), changeState());
  writePlan(cwd);

  for (const requestedSkill of ['build', 'close', 'resume']) {
    assertAllowed(runGuard(cwd, 'Bash', { command: `node "$CLAUDE_PLUGIN_ROOT/scripts/bootstrap-check.mjs" --requested-skill ${requestedSkill}` }));
  }
});

test('controlled plugin-root helpers are blocked when CLAUDE_PLUGIN_ROOT is assigned in the same segment', () => {
  const cwd = workspace();
  writeJson(path.join(cwd, '.nuclio/changes/c1/state.json'), changeState());
  writePlan(cwd);
  const statePayload = JSON.stringify(changeState());

  assertAllowed(runGuard(cwd, 'Bash', { command: `node "$CLAUDE_PLUGIN_ROOT/scripts/write-state.mjs" .nuclio/changes/c1/state.json '${statePayload}'` }));
  assertAllowed(runGuard(cwd, 'Bash', { command: `node "\${CLAUDE_PLUGIN_ROOT}/scripts/write-state.mjs" .nuclio/changes/c1/state.json '${statePayload}'` }));
  assertBlocked(runGuard(cwd, 'Bash', { command: `CLAUDE_PLUGIN_ROOT=/tmp/evil node "$CLAUDE_PLUGIN_ROOT/scripts/write-state.mjs" .nuclio/changes/c1/state.json '${statePayload}'` }), 'controlled Nuclio helper commands must not assign CLAUDE_PLUGIN_ROOT');
  assertBlocked(runGuard(cwd, 'Bash', { command: `CLAUDE_PLUGIN_ROOT=/tmp/evil node "\${CLAUDE_PLUGIN_ROOT}/scripts/write-state.mjs" .nuclio/changes/c1/state.json '${statePayload}'` }), 'controlled Nuclio helper commands must not assign CLAUDE_PLUGIN_ROOT');
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
  const needsPatch = JSON.stringify({ type: 'task.reviewed', tool: null, artifact: '.nuclio/changes/c1/evidence/review.md', result: 'needs_patch' });
  const needsRedesign = JSON.stringify({ type: 'task.reviewed', tool: null, artifact: '.nuclio/changes/c1/evidence/review.md', result: 'needs_redesign' });
  const invalidResult = JSON.stringify({ type: 'task.verified', tool: 'Bash', artifact: null, result: 'passed' });
  const invalidDecision = JSON.stringify({ type: 'decision.recorded', tool: null, artifact: null, decision: 'approved' });

  assert.equal(runNode(validateEventScript, [valid], { cwd }).status, 0);
  assert.equal(runNode(validateEventScript, [needsPatch], { cwd }).status, 0);
  assert.equal(runNode(validateEventScript, [needsRedesign], { cwd }).status, 0);
  assert.notEqual(runNode(validateEventScript, [invalidResult], { cwd }).status, 0);
  assert.notEqual(runNode(validateEventScript, [invalidDecision], { cwd }).status, 0);
});

test('validate-state accepts design repository_stage and change_kind enums', () => {
  const cwd = workspace();
  const validProjectStatePath = path.join(cwd, 'valid-project-state.json');
  const invalidProjectStatePath = path.join(cwd, 'invalid-project-state.json');
  const validChangeStatePath = path.join(cwd, 'valid-change-state.json');
  const invalidChangeStatePath = path.join(cwd, 'invalid-change-state.json');

  assert.equal(runNode(validateStateScript, [projectInitStateTemplate], { cwd }).status, 0);
  assert.equal(runNode(validateStateScript, [specStateTemplate], { cwd }).status, 0);

  writeJson(validProjectStatePath, projectState({ repository_stage: 'existing_app_with_foundation' }));
  writeJson(invalidProjectStatePath, projectState({ repository_stage: 'greenfield' }));
  writeJson(validChangeStatePath, changeState({ change_kind: 'tech_debt' }));
  writeJson(invalidChangeStatePath, changeState({ change_kind: 'chore' }));

  assert.equal(runNode(validateStateScript, [validProjectStatePath], { cwd }).status, 0);
  assert.notEqual(runNode(validateStateScript, [invalidProjectStatePath], { cwd }).status, 0);
  assert.equal(runNode(validateStateScript, [validChangeStatePath], { cwd }).status, 0);
  assert.notEqual(runNode(validateStateScript, [invalidChangeStatePath], { cwd }).status, 0);
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

test('event-log default output omits raw debug input and output snippets', () => {
  const cwd = workspace();
  writeJson(path.join(cwd, '.nuclio/changes/c1/state.json'), changeState());
  const rawInput = JSON.stringify({ command: 'echo token=SECRET_TOKEN > src/a.mjs' });
  const rawOutput = 'success authorization: Bearer SECRET_VALUE';

  const post = runNode(eventLogScript, [], {
    cwd,
    env: {
      CLAUDE_TOOL_NAME: 'Bash',
      CLAUDE_TOOL_INPUT: rawInput,
      CLAUDE_TOOL_OUTPUT: rawOutput,
    },
  });

  assert.equal(post.status, 0, `expected event-log to succeed, stdout=${post.stdout} stderr=${post.stderr}`);
  const event = JSON.parse(post.stdout);
  assert.equal(Object.hasOwn(event, 'debug'), false, 'default event must not persist debug snippets');
  assert.notEqual(event.debug?.input, rawInput);
  assert.notEqual(event.debug?.output, rawOutput);
  assert.equal(event.summary?.tool, 'Bash');
  assert.equal(event.summary?.result, event.result);
  assert.equal(runNode(validateEventScript, [JSON.stringify(event)], { cwd }).status, 0);
});

test('event-log debug redacts JSON secret fields from input and output', () => {
  const cwd = workspace();
  writeJson(path.join(cwd, '.nuclio/changes/c1/state.json'), changeState());
  const secretValues = [
    'RAW_PASSWORD_VALUE',
    'RAW_API_KEY_VALUE',
    'RAW_TOKEN_VALUE',
    'RAW_AUTHORIZATION_VALUE',
    'RAW_SECRET_VALUE',
  ];
  const rawInput = JSON.stringify({
    command: 'printf ok > src/a.mjs',
    password: secretValues[0],
    api_key: secretValues[1],
    nested: [{ token: secretValues[2] }],
  });
  const rawOutput = JSON.stringify({
    ok: true,
    authorization: `Bearer ${secretValues[3]}`,
    details: { secret: secretValues[4] },
  });

  const post = runNode(eventLogScript, [], {
    cwd,
    env: {
      CLAUDE_TOOL_NAME: 'Bash',
      CLAUDE_TOOL_INPUT: rawInput,
      CLAUDE_TOOL_OUTPUT: rawOutput,
      NUCLIO_DEBUG_EVENT_LOG: '1',
    },
  });

  assert.equal(post.status, 0, `expected event-log to succeed, stdout=${post.stdout} stderr=${post.stderr}`);
  const event = JSON.parse(post.stdout);
  assert.equal(typeof event.debug?.input, 'string');
  assert.equal(typeof event.debug?.output, 'string');
  const debugText = `${event.debug.input}\n${event.debug.output}`;
  for (const secretValue of secretValues) {
    assert.doesNotMatch(debugText, new RegExp(escapeRegExp(secretValue)), `${secretValue} must be redacted`);
  }
  assert.match(debugText, /\[REDACTED\]/);
});

test('event-log redacts prefixed secret keys in summary command and debug snippets', () => {
  const cwd = workspace();
  writeJson(path.join(cwd, '.nuclio/changes/c1/state.json'), changeState());
  const secretValues = [
    'sk-ant-raw-secret',
    'sk-openai-raw-secret',
    'placeholder_secret_token',
    'client-secret-raw-value',
    'anthropic-lower-raw-value',
  ];
  const command = `ANTHROPIC_API_KEY=${secretValues[0]} OPENAI_API_KEY=${secretValues[1]} GITHUB_TOKEN=${secretValues[2]} node -e 'console.log("ok")' --client-secret=${secretValues[3]} --anthropic_api_key ${secretValues[4]}`;
  const rawOutput = `{"client_secret":"${secretValues[3]}","anthropic_api_key":"${secretValues[4]}","GITHUB_TOKEN":"${secretValues[2]}"}`;

  const post = runNode(eventLogScript, [], {
    cwd,
    env: {
      CLAUDE_TOOL_NAME: 'Bash',
      CLAUDE_TOOL_INPUT: JSON.stringify({ command, env: { anthropic_api_key: secretValues[4] } }),
      CLAUDE_TOOL_OUTPUT: rawOutput,
      NUCLIO_DEBUG_EVENT_LOG: '1',
    },
  });

  assert.equal(post.status, 0, `expected event-log to succeed, stdout=${post.stdout} stderr=${post.stderr}`);
  const event = JSON.parse(post.stdout);
  const persisted = readFileSync(path.join(cwd, '.nuclio/changes/c1/events.jsonl'), 'utf8');
  const redactedText = `${event.summary?.command}\n${event.debug?.input}\n${event.debug?.output}\n${persisted}`;
  for (const secretValue of secretValues) {
    assert.doesNotMatch(redactedText, new RegExp(escapeRegExp(secretValue)), `${secretValue} must be redacted from summary/debug/event log`);
  }
  assert.match(redactedText, /ANTHROPIC_API_KEY=\[REDACTED\]/);
  assert.match(redactedText, /GITHUB_TOKEN=\[REDACTED\]/);
  assert.match(redactedText, /client_secret/);
  assert.match(redactedText, /\[REDACTED\]/);
});

test('event-log redacts bare secret keys and CLI flag forms in summary command and debug snippets', () => {
  const cwd = workspace();
  writeJson(path.join(cwd, '.nuclio/changes/c1/state.json'), changeState());
  const secretValues = [
    'RAW_TOKEN',
    'RAW_PASSWORD',
    'RAW_AUTH',
    'RAW_SECRET',
    'RAW_API_KEY',
    'RAW_FLAG',
    'RAW_FLAGPW',
    'RAW_FLAGAUTH',
    'RAW_COLON_TOKEN',
    'RAW_JSONISH_PASSWORD',
  ];
  const command = `token=${secretValues[0]} password=${secretValues[1]} authorization=${secretValues[2]} secret=${secretValues[3]} api_key=${secretValues[4]} node cli.mjs --token ${secretValues[5]} --password=${secretValues[6]} --authorization=${secretValues[7]}`;
  const rawOutput = `token: ${secretValues[8]} authorization: Bearer ${secretValues[2]} {"password":"${secretValues[9]}","api_key":"${secretValues[4]}"}`;

  const post = runNode(eventLogScript, [], {
    cwd,
    env: {
      CLAUDE_TOOL_NAME: 'Bash',
      CLAUDE_TOOL_INPUT: JSON.stringify({ command }),
      CLAUDE_TOOL_OUTPUT: rawOutput,
      NUCLIO_DEBUG_EVENT_LOG: '1',
    },
  });

  assert.equal(post.status, 0, `expected event-log to succeed, stdout=${post.stdout} stderr=${post.stderr}`);
  const event = JSON.parse(post.stdout);
  const persisted = readFileSync(path.join(cwd, '.nuclio/changes/c1/events.jsonl'), 'utf8');
  const redactedText = `${event.summary?.command}\n${event.debug?.input}\n${event.debug?.output}\n${persisted}`;
  for (const secretValue of secretValues) {
    assert.doesNotMatch(redactedText, new RegExp(escapeRegExp(secretValue)), `${secretValue} must be redacted from summary/debug/event log`);
  }
  assert.match(redactedText, /token=\[REDACTED\]/);
  assert.match(redactedText, /password=\[REDACTED\]/);
  assert.match(redactedText, /authorization=\[REDACTED\]/);
  assert.match(redactedText, /secret=\[REDACTED\]/);
  assert.match(redactedText, /api_key=\[REDACTED\]/);
  assert.match(redactedText, /--token\s+\[REDACTED\]/);
  assert.match(redactedText, /--password=\[REDACTED\]/);
  assert.match(redactedText, /--authorization=\[REDACTED\]/);
  assert.match(redactedText, /token:\s*\[REDACTED\]/);
  assert.match(redactedText, /authorization:\s*Bearer \[REDACTED\]/);
});

test('event-log redacts blocked output secrets from top-level reason', () => {
  const cwd = workspace();
  writeJson(path.join(cwd, '.nuclio/changes/c1/state.json'), changeState());
  const secretValues = [
    'RAW_REASON_TOKEN',
    'RAW_REASON_AUTH',
    'RAW_REASON_PASSWORD',
    'RAW_REASON_SECRET',
    'RAW_REASON_API_KEY',
  ];
  const blockedOutput = `Blocked: denied token=${secretValues[0]} authorization=${secretValues[1]} password=${secretValues[2]} secret=${secretValues[3]} api_key=${secretValues[4]}`;

  const post = runNode(eventLogScript, [], {
    cwd,
    env: {
      CLAUDE_TOOL_NAME: 'Bash',
      CLAUDE_TOOL_INPUT: JSON.stringify({ command: 'node cli.mjs' }),
      CLAUDE_TOOL_OUTPUT: blockedOutput,
    },
  });

  assert.equal(post.status, 0, `expected event-log to succeed, stdout=${post.stdout} stderr=${post.stderr}`);
  const event = JSON.parse(post.stdout);
  const persistedEvent = readFileSync(path.join(cwd, '.nuclio/changes/c1/events.jsonl'), 'utf8')
    .trim()
    .split('\n')
    .map((line) => JSON.parse(line))
    .at(-1);
  const reasonText = `${event.reason}\n${persistedEvent.reason}`;
  for (const secretValue of secretValues) {
    assert.doesNotMatch(reasonText, new RegExp(escapeRegExp(secretValue)), `${secretValue} must be redacted from stdout and persisted top-level reason`);
  }
  assert.match(reasonText, /token=\[REDACTED\]/);
  assert.match(reasonText, /authorization=\[REDACTED\]/);
  assert.match(reasonText, /password=\[REDACTED\]/);
  assert.match(reasonText, /secret=\[REDACTED\]/);
  assert.match(reasonText, /api_key=\[REDACTED\]/);
  assert.match(reasonText, /\[REDACTED\]/);
});

test('plugin manifest contains marketplace metadata fields', () => {
  const manifest = JSON.parse(readFileSync(pluginManifestPath, 'utf8'));
  for (const field of ['name', 'description', 'version', 'author', 'homepage', 'repository', 'license', 'strict']) {
    assert.ok(Object.hasOwn(manifest, field), `manifest missing ${field}`);
  }
  assert.equal(manifest.name, 'nuclio');
  assert.equal(typeof manifest.description, 'string');
  assert.equal(typeof manifest.version, 'string');
  assert.equal(typeof manifest.author, 'string');
  assert.match(manifest.homepage, /^https?:\/\//);
  assert.match(manifest.repository, /^https?:\/\//);
  assert.equal(typeof manifest.license, 'string');
  assert.equal(manifest.strict, true);
});

test('browser verifier documents external dev-browser dependency and blocked behavior', () => {
  const content = readFileSync(browserVerifierPath, 'utf8');
  assert.match(content, /dev-browser:dev-browser/);
  assert.match(content, /external (?:runtime )?skill dependency|Requires external skill/i);
  assert.match(content, /blocked/);
  assert.match(content, /dev-browser skill unavailable/);
  assert.match(content, /do not invent browser verification results/i);
});

test('guard freezes approved phase-owned artifacts even within their owner phase', () => {
  const cwd = workspace();
  writeJson(path.join(cwd, '.nuclio/changes/c1/state.json'), changeState({
    phase: 'design',
    current_task: null,
    approved: { spec: true, design: true, final: false, memory: false },
  }));

  assertBlocked(runGuard(cwd, 'Write', { file_path: '.nuclio/changes/c1/design.md', content: 'mutated' }), 'phase-owned .nuclio artifact');
  assertBlocked(runGuard(cwd, 'Write', { file_path: '.nuclio/changes/c1/plan.yaml', content: 'tasks: []\n' }), 'phase-owned .nuclio artifact');

  writeJson(path.join(cwd, '.nuclio/changes/c1/state.json'), changeState({
    phase: 'spec',
    current_task: null,
    approved: { spec: true, design: false, final: false, memory: false },
  }));
  assertBlocked(runGuard(cwd, 'Edit', { file_path: '.nuclio/changes/c1/spec.md', old_string: 'a', new_string: 'b' }), 'phase-owned .nuclio artifact');
});

test('guard freezes approved close and memory artifacts against direct rewrites', () => {
  const cwd = workspace();
  writeJson(path.join(cwd, '.nuclio/changes/c1/state.json'), changeState({
    phase: 'close',
    current_task: null,
    approved: { spec: true, design: true, final: true, memory: true },
  }));

  assertBlocked(runGuard(cwd, 'Write', { file_path: '.nuclio/changes/c1/close.md', content: 'mutated' }), 'phase-owned .nuclio artifact');
  assertBlocked(runGuard(cwd, 'Write', { file_path: '.nuclio/changes/c1/memory.patch.md', content: 'mutated' }), 'phase-owned .nuclio artifact');
  assertAllowed(runGuard(cwd, 'Write', { file_path: '.nuclio/changes/c1/evidence/final.md', content: 'evidence' }));
});

test('guard blocks memory.patch rewrites from expanding dev-docs authorization after memory approval', () => {
  const cwd = workspace();
  writeJson(path.join(cwd, '.nuclio/changes/c1/state.json'), changeState({
    phase: 'close',
    current_task: null,
    approved: { spec: true, design: true, final: true, memory: true },
  }));
  writeFileSync(path.join(cwd, '.nuclio/changes/c1/memory.patch.md'), memoryPatchWithTarget('.dev-docs/accepted.md'));

  assertAllowed(runGuard(cwd, 'Write', { file_path: '.dev-docs/accepted.md', content: 'x' }));
  assertBlocked(runGuard(cwd, 'Write', { file_path: '.nuclio/changes/c1/memory.patch.md', content: memoryPatchWithTarget('.dev-docs/new-target.md') }), 'phase-owned .nuclio artifact');
  assertBlocked(runGuard(cwd, 'Write', { file_path: '.dev-docs/new-target.md', content: 'x' }), 'writing .dev-docs requires canonical Nucl.io approval state');
});

test('guard protects approved phase-owned change artifacts from direct writes in build phase', () => {
  const cwd = workspace();
  writeJson(path.join(cwd, '.nuclio/changes/c1/state.json'), changeState({
    phase: 'build',
    approved: { spec: true, design: true, final: false, memory: false },
  }));
  writePlan(cwd);

  assertBlocked(runGuard(cwd, 'Edit', { file_path: '.nuclio/changes/c1/spec.md', old_string: 'a', new_string: 'b' }), 'phase-owned .nuclio artifact');
  assertBlocked(runGuard(cwd, 'Write', { file_path: '.nuclio/changes/c1/design.md', content: 'x' }), 'phase-owned .nuclio artifact');
  assertBlocked(runGuard(cwd, 'Write', { file_path: '.nuclio/changes/c1/plan.yaml', content: 'tasks: []\n' }), 'phase-owned .nuclio artifact');
  assertAllowed(runGuard(cwd, 'Write', { file_path: '.nuclio/changes/c1/evidence/T1/verify.md', content: 'evidence' }));
});

test('guard keeps controlled state and events helpers allowed while direct state/events writes are blocked', () => {
  const cwd = workspace();
  writeJson(path.join(cwd, '.nuclio/changes/c1/state.json'), changeState());
  writePlan(cwd);
  const statePayload = JSON.stringify(changeState({ phase: 'build' }));
  const eventPayload = JSON.stringify({ type: 'task.started', tool: 'Bash', artifact: null, result: 'unknown' });

  assertBlocked(runGuard(cwd, 'Write', { file_path: '.nuclio/changes/c1/state.json', content: statePayload }), 'state/events helper');
  assertBlocked(runGuard(cwd, 'Write', { file_path: '.nuclio/changes/c1/events.jsonl', content: eventPayload }), 'state/events helper');
  assertAllowed(runGuard(cwd, 'Bash', { command: `node "$CLAUDE_PLUGIN_ROOT/scripts/write-state.mjs" .nuclio/changes/c1/state.json '${statePayload}'` }));
  assertAllowed(runGuard(cwd, 'Bash', { command: `node "$CLAUDE_PLUGIN_ROOT/scripts/append-event.mjs" .nuclio/changes/c1/events.jsonl '${eventPayload}'` }));
});

test('output-filter declares post-use summary semantics instead of hiding original Bash output', () => {
  const hooksConfig = JSON.parse(readFileSync(path.join(repoRoot, 'plugins/nuclio/hooks/hooks.json'), 'utf8'));
  const postToolHooks = hooksConfig.hooks?.PostToolUse ?? [];
  assert.ok(postToolHooks.some((entry) => entry.matcher === 'Bash'
    && entry.hooks?.some((hook) => String(hook.command || '').includes('output-filter.mjs'))));

  const outputFilter = readFileSync(path.join(repoRoot, 'plugins/nuclio/hooks/output-filter.mjs'), 'utf8');
  assert.match(outputFilter, /filtered post-use summary/i);
  assert.match(outputFilter, /not relied on to replace or hide the original Bash output/i);
});

test('plan, dev-docs index, and context report validators enforce deterministic protocols', () => {
  const cwd = workspace();

  const validPlan = path.join(cwd, 'valid-plan.yaml');
  writeFileSync(validPlan, `tasks:
  - id: T1
    type: implementation
    risk: low
    depends_on: []
    source: spec.md#requirements
    allowed_paths: [src/**]
    forbidden_paths: [.nuclio/**]
    acceptance: ok
    verify: node --check src/a.mjs
    review_focus: correctness
global_acceptance:
  - ok
`);
  assert.equal(runNode(validatePlanScript, [validPlan, '--section', 'tasks'], { cwd }).status, 0);

  const missingDependencyPlan = path.join(cwd, 'missing-dependency-plan.yaml');
  writeFileSync(missingDependencyPlan, `tasks:
  - id: T1
    type: implementation
    risk: low
    depends_on: [MISSING]
    source: spec.md#requirements
    allowed_paths: [src/**]
    forbidden_paths: [.nuclio/**]
    acceptance: ok
    verify: ok
    review_focus: ok
global_acceptance:
  - ok
`);
  assert.notEqual(runNode(validatePlanScript, [missingDependencyPlan, '--section', 'tasks'], { cwd }).status, 0, 'missing depends_on reference must fail');

  const cyclePlan = path.join(cwd, 'cycle-plan.yaml');
  writeFileSync(cyclePlan, `tasks:
  - id: T1
    type: implementation
    risk: low
    depends_on: [T2]
    source: spec.md#requirements
    allowed_paths: [src/**]
    forbidden_paths: [.nuclio/**]
    acceptance: ok
    verify: ok
    review_focus: ok
  - id: T2
    type: verification
    risk: low
    depends_on: [T1]
    source: spec.md#requirements
    allowed_paths: [tests/**]
    forbidden_paths: [.nuclio/**]
    acceptance: ok
    verify: ok
    review_focus: ok
global_acceptance:
  - ok
`);
  const cycleResult = runNode(validatePlanScript, [cyclePlan, '--section', 'tasks'], { cwd });
  assert.notEqual(cycleResult.status, 0, 'dependency cycle must fail');
  assert.match(cycleResult.stderr, /dependency cycle/i);

  const missingGlobalAcceptancePlan = path.join(cwd, 'missing-global-acceptance-plan.yaml');
  writeFileSync(missingGlobalAcceptancePlan, `tasks:
  - id: T1
    type: implementation
    risk: low
    depends_on: []
    source: spec.md#requirements
    allowed_paths: [src/**]
    forbidden_paths: [.nuclio/**]
    acceptance: ok
    verify: ok
    review_focus: ok
`);
  assert.notEqual(runNode(validatePlanScript, [missingGlobalAcceptancePlan, '--section', 'tasks'], { cwd }).status, 0, 'tasks plans require global_acceptance');

  const emptyStringGlobalAcceptancePlan = path.join(cwd, 'empty-string-global-acceptance-plan.yaml');
  writeFileSync(emptyStringGlobalAcceptancePlan, `tasks:
  - id: T1
    type: implementation
    risk: low
    depends_on: []
    source: spec.md#requirements
    allowed_paths: [src/**]
    forbidden_paths: [.nuclio/**]
    acceptance: ok
    verify: ok
    review_focus: ok
global_acceptance: ""
`);
  assert.notEqual(runNode(validatePlanScript, [emptyStringGlobalAcceptancePlan, '--section', 'tasks'], { cwd }).status, 0, 'tasks plans require non-empty global_acceptance');

  const scaffoldMissingReviewFocusPlan = path.join(cwd, 'scaffold-missing-review-focus-plan.yaml');
  writeFileSync(scaffoldMissingReviewFocusPlan, `scaffold_tasks:
  - id: P1
    type: implementation
    risk: medium
    depends_on: []
    source: .nuclio/project/architecture-baseline.md#scaffold
    allowed_paths: [src/**]
    forbidden_paths: [.dev-docs/**]
    acceptance: ok
    verify: ok
`);
  assert.notEqual(runNode(validatePlanScript, [scaffoldMissingReviewFocusPlan, '--section', 'scaffold_tasks'], { cwd }).status, 0, 'scaffold_tasks require review_focus');

  const validIndex = path.join(cwd, '.dev-docs/index.md');
  mkdirSync(path.dirname(validIndex), { recursive: true });
  writeFileSync(validIndex, `# Dev Docs Index

| Path | Load Mode | Visible In | Load When |
| --- | --- | --- | --- |
| architecture/index.md | index | spec, design | Architecture context is needed |
| product/overview.md | leaf | spec | Product behavior is relevant |
`);
  assert.equal(runNode(validateDevDocsIndexScript, [validIndex], { cwd }).status, 0);

  const invalidIndex = path.join(cwd, '.dev-docs/invalid-index.md');
  writeFileSync(invalidIndex, `# Dev Docs Index

| Path | Load Mode | Visible In | Load When |
| --- | --- | --- | --- |
| ../secrets.md | leaf | spec | Bad traversal |
| architecture/index.md | sometimes | spec | Bad mode |
`);
  assert.notEqual(runNode(validateDevDocsIndexScript, [invalidIndex], { cwd }).status, 0, 'unsafe paths and invalid load modes must fail');

  const validContextReport = path.join(cwd, 'context-report.md');
  writeFileSync(validContextReport, `# Context Report: c1

| index | selected_path | load_mode | visible_in | load_when | decision | reason |
| --- | --- | --- | --- | --- | --- | --- |
| .dev-docs/index.md | .dev-docs/index.md | index | spec, design | Root routing index | loaded | Required root index |
| .dev-docs/index.md | .dev-docs/old.md | leaf | spec | Legacy docs | skipped | stale |
`);
  assert.equal(runNode(validateContextReportScript, [validContextReport], { cwd }).status, 0);

  const invalidContextReport = path.join(cwd, 'invalid-context-report.md');
  writeFileSync(invalidContextReport, `# Context Report: c1

| index | selected_path | load_mode | visible_in | load_when | decision | reason |
| --- | --- | --- | --- | --- | --- | --- |
| .dev-docs/feature/index.md | .dev-docs/feature.md | sometimes | spec | Feature docs | loaded | invalid mode |
`);
  assert.notEqual(runNode(validateContextReportScript, [invalidContextReport], { cwd }).status, 0, 'context report must require root index and valid load modes');
});

test('plan parser validates task items that start with non-id keys', () => {
  const cwd = workspace();

  const invalidIgnoredTaskPlan = path.join(cwd, 'invalid-ignored-task-plan.yaml');
  writeFileSync(invalidIgnoredTaskPlan, `tasks:
  - id: T1
    type: implementation
    risk: low
    depends_on: []
    source: spec.md#requirements
    allowed_paths: [src/**]
    forbidden_paths: [.nuclio/**]
    acceptance: ok
    verify: ok
    review_focus: ok
  - type: verification
    risk: low
    depends_on: []
    source: spec.md#requirements
    allowed_paths: [tests/**]
    forbidden_paths: [.nuclio/**]
    acceptance: ok
    verify: ok
    review_focus: ok
global_acceptance:
  - ok
`);
  assert.notEqual(runNode(validatePlanScript, [invalidIgnoredTaskPlan, '--section', 'tasks'], { cwd }).status, 0, 'task item starting with type and missing id must fail instead of being ignored');

  const validTypeFirstTaskPlan = path.join(cwd, 'valid-type-first-task-plan.yaml');
  writeFileSync(validTypeFirstTaskPlan, `tasks:
  - type: implementation
    id: T1
    risk: low
    depends_on: []
    source: spec.md#requirements
    allowed_paths: [src/**]
    forbidden_paths: [.nuclio/**]
    acceptance: ok
    verify: ok
    review_focus: ok
global_acceptance:
  - ok
`);
  assert.equal(runNode(validatePlanScript, [validTypeFirstTaskPlan, '--section', 'tasks'], { cwd }).status, 0, 'task item starting with type and later id must be parsed');
});

test('guard build path parser honors validator-accepted type-first plan tasks', () => {
  const cwd = workspace();
  writeJson(path.join(cwd, '.nuclio/changes/c1/state.json'), changeState({
    phase: 'build',
    current_task: 'T1',
    approved: { spec: true, design: true, final: false, memory: false },
  }));
  const planPath = path.join(cwd, '.nuclio/changes/c1/plan.yaml');
  mkdirSync(path.dirname(planPath), { recursive: true });
  writeFileSync(planPath, `tasks:
  - type: implementation
    id: T1
    risk: low
    depends_on: []
    source: spec.md#requirements
    allowed_paths: [src/**]
    forbidden_paths: [.nuclio/**]
    acceptance: ok
    verify: node --check src/a.mjs
    review_focus: correctness
global_acceptance:
  - ok
`);

  assert.equal(runNode(validatePlanScript, [planPath, '--section', 'tasks'], { cwd }).status, 0, 'validator must accept type-first plan');
  assertAllowed(runGuard(cwd, 'Write', { file_path: 'src/a.mjs', content: 'x' }));
  assertBlocked(runGuard(cwd, 'Write', { file_path: 'tests/a.mjs', content: 'x' }), 'outside task T1 allowed_paths');
});

test('context report validator rejects selected_path traversal under .dev-docs', () => {
  const cwd = workspace();
  const contextReport = path.join(cwd, 'context-report-traversal.md');
  writeFileSync(contextReport, `# Context Report: c1

| index | selected_path | load_mode | visible_in | load_when | decision | reason |
| --- | --- | --- | --- | --- | --- | --- |
| .dev-docs/index.md | .dev-docs/index.md | index | spec, design | Root routing index | loaded | Required root index |
| .dev-docs/index.md | .dev-docs/../secrets.md | leaf | spec | Traversal path | skipped | unsafe |
`);

  assert.notEqual(runNode(validateContextReportScript, [contextReport], { cwd }).status, 0, 'selected_path traversal must fail');
});

test('path validators reject Windows drive absolute paths', () => {
  const cwd = workspace();

  const windowsAllowedPathPlan = path.join(cwd, 'windows-allowed-path-plan.yaml');
  writeFileSync(windowsAllowedPathPlan, `tasks:
  - id: T1
    type: implementation
    risk: low
    depends_on: []
    source: spec.md#requirements
    allowed_paths: [C:\\secrets\\**]
    forbidden_paths: [.nuclio/**]
    acceptance: ok
    verify: ok
    review_focus: ok
global_acceptance:
  - ok
`);
  assert.notEqual(runNode(validatePlanScript, [windowsAllowedPathPlan, '--section', 'tasks'], { cwd }).status, 0, 'Windows absolute allowed_paths must fail');

  const windowsForbiddenPathPlan = path.join(cwd, 'windows-forbidden-path-plan.yaml');
  writeFileSync(windowsForbiddenPathPlan, `tasks:
  - id: T1
    type: implementation
    risk: low
    depends_on: []
    source: spec.md#requirements
    allowed_paths: [src/**]
    forbidden_paths: [C:\\secrets\\**]
    acceptance: ok
    verify: ok
    review_focus: ok
global_acceptance:
  - ok
`);
  assert.notEqual(runNode(validatePlanScript, [windowsForbiddenPathPlan, '--section', 'tasks'], { cwd }).status, 0, 'Windows absolute forbidden_paths must fail');

  const windowsIndex = path.join(cwd, '.dev-docs/windows-index.md');
  mkdirSync(path.dirname(windowsIndex), { recursive: true });
  writeFileSync(windowsIndex, `# Dev Docs Index

| Path | Load Mode | Visible In | Load When |
| --- | --- | --- | --- |
| C:\\secrets\\doc.md | leaf | spec | Bad Windows absolute |
`);
  assert.notEqual(runNode(validateDevDocsIndexScript, [windowsIndex], { cwd }).status, 0, 'Windows absolute dev-docs index Path must fail');
});

test('workflow helper validators accept minimal valid artifacts and reject invalid ones', () => {
  const cwd = workspace();
  writeJson(path.join(cwd, '.nuclio/project/init-state.json'), projectState());
  mkdirSync(path.join(cwd, '.dev-docs'), { recursive: true });
  writeFileSync(path.join(cwd, '.dev-docs/index.md'), '# Dev Docs\n');
  writeJson(path.join(cwd, '.nuclio/changes/c1/state.json'), changeState({ status: 'done' }));
  writeJson(path.join(cwd, '.nuclio/changes/c2/state.json'), changeState({ status: 'active' }));

  const bootstrap = runNode(bootstrapCheckScript, ['--requested-skill', 'spec'], { cwd });
  assert.equal(bootstrap.status, 0);
  const bootstrapJson = JSON.parse(bootstrap.stdout);
  assert.equal(bootstrapJson.ok, true);
  assert.equal(bootstrapJson.requested_skill, 'spec');
  assert.equal(bootstrapJson.repository_stage, 'existing_app_with_foundation');
  assert.equal(bootstrapJson.has_nuclio_dir, true);
  assert.equal(bootstrapJson.has_dev_docs, true);
  assert.equal(bootstrapJson.project_init_state?.valid, true);
  assert.equal(bootstrapJson.recommendation, 'continue_current_change');
  assert.equal(bootstrapJson.foundation, 'ready');
  assert.equal(bootstrapJson.next_action, 'continue_current_change');
  assert.equal(bootstrapJson.active_changes.length, 1);

  const planPath = path.join(cwd, '.nuclio/changes/c2/plan.yaml');
  writePlan(cwd, 'c2');
  assert.equal(runNode(validatePlanScript, [planPath, '--section', 'tasks'], { cwd }).status, 0);
  assert.equal(runNode(validatePlanScript, [path.join(repoRoot, 'plugins/nuclio/skills/design/templates/plan-template.yaml'), '--section', 'tasks'], { cwd }).status, 0);
  assert.equal(runNode(validatePlanScript, [path.join(repoRoot, 'plugins/nuclio/skills/project-init/templates/scaffold-plan-template.yaml'), '--section', 'scaffold_tasks'], { cwd }).status, 0);

  const contextReport = path.join(cwd, '.nuclio/changes/c2/context-report.md');
  writeFileSync(contextReport, `# Context Report

| index | selected_path | load_mode | visible_in | load_when | decision | reason |
| --- | --- | --- | --- | --- | --- | --- |
| .dev-docs/index.md | .dev-docs/index.md | index | spec, design | Root routing index | loaded | relevant |
| .dev-docs/index.md | .dev-docs/old.md | leaf | spec | Legacy docs | skipped | stale |
`);
  assert.equal(runNode(validateContextReportScript, [contextReport], { cwd }).status, 0);
  assert.equal(runNode(validateContextReportScript, [contextReportTemplate], { cwd }).status, 0);

  const memoryPatch = path.join(cwd, '.nuclio/changes/c2/memory.patch.md');
  writeFileSync(memoryPatch, `# Memory Patch: c2

## Proposed Updates

| id | target | operation | reason | confidence |
| --- | --- | --- | --- | --- |
| U1 | .dev-docs/index.md | update | Refresh index | high |
| U2 | .dev-docs/topic.md | create | Add topic note | medium |

### Update U1

- id: U1
- target: .dev-docs/index.md
- operation: update
- reason: Refresh index
- confidence: high

\`\`\`diff
--- before
+++ after
@@
- old
+ new
\`\`\`

### Update U2

- id: U2
- target: .dev-docs/topic.md
- operation: create
- reason: Add topic note
- confidence: medium

\`\`\`markdown
# Topic
\`\`\`

## Human Approval Decisions

| id | decision | approved_content_ref | note |
| --- | --- | --- | --- |
| U1 | accept | Update U1 | approved as-is |
| U2 | defer |  | later |
`);
  assert.equal(runNode(validateMemoryPatchScript, [memoryPatch], { cwd }).status, 0);
  assert.equal(runNode(validateMemoryPatchScript, [path.join(repoRoot, 'plugins/nuclio/skills/close/templates/memory-patch-template.md')], { cwd }).status, 0);
  assert.equal(runNode(validateMemoryPatchScript, [path.join(repoRoot, 'plugins/nuclio/skills/project-init/templates/initial-dev-docs-patch-template.md')], { cwd }).status, 0);

  writeFileSync(memoryPatch, `# Memory Patch: c2

## Proposed Updates

| id | target | operation | reason | confidence |
| --- | --- | --- | --- | --- |
| U1 | README.md | update | Bad target | high |

### Update U1

- id: U1
- target: README.md
- operation: update
- reason: Bad target
- confidence: high

\`\`\`diff
--- before
+++ after
@@
- old
+ new
\`\`\`
`);
  assert.notEqual(runNode(validateMemoryPatchScript, [memoryPatch], { cwd }).status, 0);
});

function validMemoryPatchWithDecision(decisionRow) {
  return `# Memory Patch: c1

## Proposed Updates

| id | target | operation | reason | confidence |
| --- | --- | --- | --- | --- |
| U1 | .dev-docs/index.md | update | Refresh index | high |
| U2 | .dev-docs/topic.md | update | Refresh topic | high |

### Update U1

- id: U1
- target: .dev-docs/index.md
- operation: update
- reason: Refresh index
- confidence: high

\`\`\`diff
--- before
+++ after
@@
- old
+ new
\`\`\`

### Update U2

- id: U2
- target: .dev-docs/topic.md
- operation: update
- reason: Refresh topic
- confidence: high

\`\`\`diff
--- before
+++ after
@@
- old
+ new
\`\`\`

## Human Approval Decisions

| id | decision | approved_content_ref | note |
| --- | --- | --- | --- |
${decisionRow}
`;
}

test('memory patch validator rejects accept decisions with empty approved_content_ref', () => {
  const cwd = workspace();
  const memoryPatch = path.join(cwd, 'memory.patch.md');

  writeFileSync(memoryPatch, validMemoryPatchWithDecision('| U1 | accept |  | empty ref must fail |'));

  assert.notEqual(runNode(validateMemoryPatchScript, [memoryPatch], { cwd }).status, 0, 'accept requires non-empty approved_content_ref');
});

test('memory patch validator rejects edit decisions with bogus approved_content_ref', () => {
  const cwd = workspace();
  const memoryPatch = path.join(cwd, 'memory.patch.md');

  writeFileSync(memoryPatch, validMemoryPatchWithDecision('| U2 | edit | bogus-ref | bogus ref must fail |'));

  assert.notEqual(runNode(validateMemoryPatchScript, [memoryPatch], { cwd }).status, 0, 'edit requires approved_content_ref to point to existing content');
});

test('guard only treats Human Approval Decisions as accepted memory patch targets', () => {
  const cwd = workspace();
  writeJson(path.join(cwd, '.nuclio/changes/c1/state.json'), changeState({
    phase: 'close',
    current_task: null,
    approved: { spec: true, design: true, final: true, memory: true },
  }));
  mkdirSync(path.join(cwd, '.nuclio/changes/c1'), { recursive: true });
  writeFileSync(path.join(cwd, '.nuclio/changes/c1/memory.patch.md'), `# Memory Patch: c1

## Proposed Updates

| id | target | operation | reason | confidence | decision |
| --- | --- | --- | --- | --- | --- |
| U1 | .dev-docs/proposal-only.md | update | Proposal table must not authorize writes | high | accept |

### Update U1

- id: U1
- target: .dev-docs/proposal-only.md
- operation: update
- reason: Proposal table must not authorize writes
- confidence: high

\`\`\`diff
--- before
+++ after
@@
- old
+ new
\`\`\`
`);

  assertBlocked(runGuard(cwd, 'Write', { file_path: '.dev-docs/proposal-only.md', content: 'x' }), 'writing .dev-docs requires canonical Nucl.io approval state');
});

test('memory patch validator separates proposals from approval decisions', () => {
  const cwd = workspace();
  const memoryPatch = path.join(cwd, 'memory.patch.md');

  writeFileSync(memoryPatch, `# Memory Patch: c1

## Proposed Updates

| id | target | operation | reason | confidence |
| --- | --- | --- | --- | --- |
| U1 | .dev-docs/index.md | update | Refresh index | high |

### Update U1

- id: U1
- target: .dev-docs/index.md
- operation: update
- reason: Refresh index
- confidence: high

\`\`\`diff
--- before
+++ after
@@
- old
+ new
\`\`\`

## Human Approval Decisions

| id | decision | approved_content_ref | note |
| --- | --- | --- | --- |
`);
  assert.equal(runNode(validateMemoryPatchScript, [memoryPatch], { cwd }).status, 0, 'proposal rows must not require decision');

  writeFileSync(memoryPatch, `# Memory Patch: c1

## Proposed Updates

| id | target | operation | reason | confidence |
| --- | --- | --- | --- | --- |
| U1 | .dev-docs/index.md | update | Refresh index | high |

### Update U1

- id: U1
- target: .dev-docs/index.md
- operation: update
- reason: Refresh index
- confidence: high

\`\`\`diff
--- before
+++ after
@@
- old
+ new
\`\`\`

## Human Approval Decisions

| id | decision | approved_content_ref | note |
| --- | --- | --- | --- |
| U1 |  | Update U1 | missing decision |
`);
  assert.notEqual(runNode(validateMemoryPatchScript, [memoryPatch], { cwd }).status, 0, 'approval rows must require decision');

  writeFileSync(memoryPatch, `# Memory Patch: c1

## Proposed Updates

| id | target | operation | reason | confidence |
| --- | --- | --- | --- | --- |
| U1 | .dev-docs/index.md | update | Refresh index | high |

### Update U1

- id: U1
- target: .dev-docs/index.md
- operation: update
- reason: Refresh index
- confidence: high
`);
  assert.notEqual(runNode(validateMemoryPatchScript, [memoryPatch], { cwd }).status, 0, 'non-delete proposals require fenced content or diff');
});
