import assert from "node:assert/strict";
import { mkdir, mkdtemp, rm, writeFile } from "node:fs/promises";
import { join } from "node:path";
import { tmpdir } from "node:os";
import {
  MarketplaceSkillProvider,
  apply,
  parseSkillDocument,
  toDshSkillName
} from "./index.mjs";

const root = await mkdtemp(join(tmpdir(), "cc-marketplace-dsh-"));
const invalid = `---\nname: broken\ndescription: broken\nuser-invocable: maybe\n---\nignored`;

try {
  await writeSkill(root, "alpha-one", "alpha", "demo", `---
name: demo
description: Demo skill
whenToUse: Use this demo
metadata:
  owner: test
disable-model-invocation: true
---
Demo body
`);
  await writeSkill(root, "alpha-one", "alpha", "changed", `---
name: changed
description: Changed skill
---
Changed body
`);
  await writeSkill(root, "alpha-two", "alpha", "demo", `---
name: demo
description: Duplicate skill
---
Duplicate body
`);
  await writeSkill(root, "alpha-two", "alpha", "broken", invalid);
  await writeSkill(root, "beta", "beta", "valid", `---
name: valid
description: Valid skill
user-invocable: false
---
Valid body
`);
  await mkdir(join(root, "plugins", "no-skills"), { recursive: true });

  assert.equal(toDshSkillName("Nuclio", "Work"), "nuclio-work");
  assert.equal(parseSkillDocument("# missing frontmatter"), undefined);
  assert.equal(parseSkillDocument(invalid), undefined);
  const explicit = parseSkillDocument(`---
name: work
description: Work
disable-model-invocation: true
---
body`);
  assert.deepEqual(explicit.invocation, { modelInvocable: false, userInvocable: true });

  const invalidations = [];
  const controller = new AbortController();
  const provider = new MarketplaceSkillProvider(
    { logger: { warn(message) { invalidations.push(message); } } },
    { signal: controller.signal, invalidate() {} },
    { root, watch: false }
  );
  let catalog = await provider.list();
  assert.deepEqual(catalog.map((entry) => entry.name).sort(), ["alpha-changed", "alpha-demo", "beta-valid"]);
  const demo = catalog.find((entry) => entry.name === "alpha-demo");
  assert.equal(demo.invocation.modelInvocable, false);
  assert.equal(demo.invocation.userInvocable, true);
  assert.equal(demo.resourceBase.kind, "directory");
  assert.equal(demo.resourceBase.path.endsWith("/demo"), true);
  assert.equal(demo.metadata.owner, "test");
  assert.equal((await provider.get(demo)).content, "Demo body");
  assert.equal(catalog.find((entry) => entry.name === "beta-valid").invocation.userInvocable, false);
  assert.equal(invalidations.some((message) => message.includes("duplicate")), true);

  await writeSkill(root, "alpha-one", "alpha", "added", `---
name: added
description: Added skill
---
Added body
`);
  catalog = await provider.list();
  assert.equal(catalog.some((entry) => entry.name === "alpha-added"), true);
  await rm(join(root, "plugins", "alpha-one", "skills", "added", "SKILL.md"));
  catalog = await provider.list();
  assert.equal(catalog.some((entry) => entry.name === "alpha-added"), false);
  await provider.dispose();

  let registeredFactory;
  let registeredEffect;
  const applyContext = {
    skills: {
      registerProvider(factory) {
        registeredFactory = factory;
        return () => {};
      }
    },
    effect(factory) {
      registeredEffect = factory;
      return () => {};
    }
  };
  apply(applyContext, { root, watch: false });
  const appliedProvider = registeredFactory({ signal: new AbortController().signal, invalidate() {} });
  assert.equal(appliedProvider.name, "jade-tools-marketplace");
  const cleanup = registeredEffect().next().value;
  await cleanup();
  assert.equal(appliedProvider.closed, true);

  let watcherInvalidated = 0;
  const watched = new MarketplaceSkillProvider(
    { logger: { warn() {} } },
    { signal: new AbortController().signal, invalidate() { watcherInvalidated += 1; } },
    { root, watch: true }
  );
  await new Promise((resolve) => setTimeout(resolve, 300));
  await writeSkill(root, "beta", "beta", "watched", `---
name: watched
description: Watched skill
---
Watched body
`);
  await waitFor(() => watcherInvalidated > 0, 3000);
  assert.equal(watcherInvalidated > 0, true);
  await watched.dispose();
  controller.abort();
  console.log("dsh provider tests passed");
} finally {
  await rm(root, { recursive: true, force: true });
}

async function writeSkill(rootDir, pluginDir, pluginName, skillName, content) {
  const pluginRoot = join(rootDir, "plugins", pluginDir);
  await mkdir(join(pluginRoot, "skills", skillName), { recursive: true });
  await mkdir(join(pluginRoot, ".codex-plugin"), { recursive: true });
  await writeFile(join(pluginRoot, ".codex-plugin", "plugin.json"), JSON.stringify({ name: pluginName }));
  await writeFile(join(pluginRoot, "skills", skillName, "SKILL.md"), content);
}

async function waitFor(predicate, timeoutMs) {
  const started = Date.now();
  while (!predicate()) {
    if (Date.now() - started > timeoutMs) throw new Error("timed out waiting for watcher invalidation");
    await new Promise((resolve) => setTimeout(resolve, 40));
  }
}
