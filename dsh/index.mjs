import { readdir, readFile } from "node:fs/promises";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { parse as parseYaml } from "yaml";
import chokidar from "chokidar";

const PACKAGE_ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const PLUGIN_ROOT = "plugins";
const SKILL_FILE = "SKILL.md";
const PROVIDER_NAME = "jade-tools-marketplace";
const BUNDLED_RANK = 600;
const SKILL_NAME = /^[a-z0-9]+(?:-[a-z0-9]+)*$/;

export const name = PROVIDER_NAME;
export const inject = ["skills"];

/** Register Marketplace skills with DSH without changing its built-in providers. */
export function apply(ctx, config = {}) {
  let provider;
  ctx.skills.registerProvider((control) => {
    provider = new MarketplaceSkillProvider(ctx, control, config);
    return provider;
  });
  ctx.effect(function* () {
    yield async () => {
      await provider?.dispose();
    };
  }, `${PROVIDER_NAME} watcher`);
}

export class MarketplaceSkillProvider {
  constructor(ctx, control, config = {}) {
    this.ctx = ctx;
    this.control = control;
    this.root = resolve(config.root ?? process.env.DSH_MARKETPLACE_ROOT ?? PACKAGE_ROOT);
    this.providerName = config.providerName ?? PROVIDER_NAME;
    this.name = this.providerName;
    this.watching = config.watch !== false;
    this.watcher = undefined;
    this.closed = false;
    control.signal.addEventListener("abort", () => {
      void this.dispose();
    }, { once: true });
    if (this.watching) this.startWatcher();
  }

  async list(options = {}) {
    options.signal?.throwIfAborted();
    const skills = [];
    const seen = new Set();
    for (const plugin of await listPlugins(this.root, options.signal)) {
      for (const entry of await listSkillEntries(plugin.skillsRoot, options.signal)) {
        options.signal?.throwIfAborted();
        const document = await readSkillDocument(entry.path, options.signal);
        if (document === undefined) continue;
        if (document.name === undefined || document.description === undefined) {
          this.warn(`skill file ${entry.path} ignored: frontmatter requires name and description`);
          continue;
        }
        if (!SKILL_NAME.test(document.name)) {
          this.warn(`skill file ${entry.path} ignored: invalid skill name "${document.name}"`);
          continue;
        }
        const name = toDshSkillName(plugin.name, document.name);
        if (seen.has(name)) {
          this.warn(`skill file ${entry.path} ignored: duplicate DSH skill name "${name}"`);
          continue;
        }
        seen.add(name);
        skills.push(candidateFor(name, plugin.name, entry.path, document, this.providerName));
      }
    }
    return skills;
  }

  async get(candidate, options = {}) {
    options.signal?.throwIfAborted();
    const locator = candidate?.locator;
    if (locator === undefined || typeof locator.path !== "string") return undefined;
    const document = await readSkillDocument(locator.path, options.signal);
    if (document === undefined) return undefined;
    if (document.name === undefined || document.description === undefined) return undefined;
    const name = toDshSkillName(locator.pluginName, document.name);
    if (name !== candidate.name) return undefined;
    return definitionFor(name, locator.pluginName, locator.path, document, this.providerName);
  }

  startWatcher() {
    const root = join(this.root, PLUGIN_ROOT);
    this.watcher = chokidar.watch(root, {
      ignoreInitial: true,
      followSymlinks: true,
      awaitWriteFinish: {
        stabilityThreshold: 120,
        pollInterval: 40
      }
    });
    this.watcher.on("all", () => {
      if (!this.closed) this.control.invalidate();
    });
    this.watcher.on("error", (error) => {
      this.warn(`failed to watch ${root}: ${errorMessage(error)}`);
    });
  }

  async dispose() {
    if (this.closed) return;
    this.closed = true;
    if (this.watcher !== undefined) {
      await this.watcher.close();
      this.watcher = undefined;
    }
  }

  warn(message) {
    this.ctx.logger?.warn?.(message);
  }
}

export function toDshSkillName(pluginName, skillName) {
  return `${pluginName}-${skillName}`.toLowerCase();
}

export function parseSkillDocument(raw) {
  const match = /^(?:\uFEFF)?---\r?\n([\s\S]*?)\r?\n---(?:\r?\n|$)([\s\S]*)$/.exec(raw);
  if (match === null) return undefined;
  let data;
  try {
    data = parseYaml(match[1]);
  } catch {
    return undefined;
  }
  if (data === null || typeof data !== "object" || Array.isArray(data)) return undefined;
  const name = typeof data.name === "string" ? data.name.trim() : undefined;
  const description = typeof data.description === "string" ? data.description.trim() : undefined;
  const whenToUse = typeof data.whenToUse === "string" ? data.whenToUse.trim() : undefined;
  const metadata = data.metadata && typeof data.metadata === "object" && !Array.isArray(data.metadata)
    ? data.metadata
    : undefined;
  let modelInvocable = true;
  let userInvocable = true;
  try {
    if (data["disable-model-invocation"] !== undefined) {
      modelInvocable = !parseBoolean(data["disable-model-invocation"]);
    }
    if (data["user-invocable"] !== undefined) {
      userInvocable = parseBoolean(data["user-invocable"]);
    }
  } catch {
    return undefined;
  }
  return {
    name,
    description,
    whenToUse,
    metadata,
    invocation: { modelInvocable, userInvocable },
    content: match[2].trim()
  };
}

async function listPlugins(root, signal) {
  const pluginsRoot = join(root, PLUGIN_ROOT);
  const entries = await readDirectory(pluginsRoot, signal);
  const plugins = [];
  for (const entry of entries) {
    signal?.throwIfAborted();
    if (!entry.isDirectory()) continue;
    const pluginRoot = join(pluginsRoot, entry.name);
    const manifest = await readPluginManifest(pluginRoot, signal);
    const pluginName = manifest?.name ?? entry.name;
    if (!SKILL_NAME.test(pluginName)) continue;
    plugins.push({
      name: pluginName,
      skillsRoot: join(pluginRoot, "skills")
    });
  }
  return plugins;
}

async function listSkillEntries(skillsRoot, signal) {
  const entries = await readDirectory(skillsRoot, signal);
  return entries
    .filter((entry) => entry.isDirectory())
    .map((entry) => ({ name: entry.name, path: join(skillsRoot, entry.name, SKILL_FILE) }));
}

async function readPluginManifest(pluginRoot, signal) {
  for (const relativePath of [".codex-plugin/plugin.json", ".claude-plugin/plugin.json"]) {
    const path = join(pluginRoot, relativePath);
    try {
      signal?.throwIfAborted();
      const raw = await readFile(path, { encoding: "utf8", signal });
      const data = JSON.parse(raw);
      if (data && typeof data.name === "string") return data;
    } catch (error) {
      if (!isAbsent(error)) throw error;
    }
  }
  return undefined;
}

async function readSkillDocument(path, signal) {
  try {
    const raw = await readFile(path, { encoding: "utf8", signal });
    return parseSkillDocument(raw);
  } catch (error) {
    if (isAbsent(error)) return undefined;
    throw error;
  }
}

async function readDirectory(path, signal) {
  try {
    return await readdir(path, { withFileTypes: true, encoding: "utf8" });
  } catch (error) {
    if (isAbsent(error)) return [];
    throw error;
  }
}

function candidateFor(name, pluginName, path, document, providerName) {
  return {
    ...summaryFor(name, pluginName, path, document, providerName),
    rank: BUNDLED_RANK,
    locator: { pluginName, path }
  };
}

function definitionFor(name, pluginName, path, document, providerName) {
  return {
    ...summaryFor(name, pluginName, path, document, providerName),
    content: document.content
  };
}

function summaryFor(name, pluginName, path, document, providerName) {
  return {
    name,
    description: document.description,
    ...(document.whenToUse === undefined ? {} : { whenToUse: document.whenToUse }),
    invocation: document.invocation,
    source: "bundled",
    provider: providerName,
    path,
    resourceBase: { kind: "directory", path: dirname(path) },
    ...(document.metadata === undefined ? {} : { metadata: document.metadata })
  };
}

function parseBoolean(value) {
  if (typeof value === "boolean") return value;
  if (value === 1 || value === "1" || (typeof value === "string" && ["true", "yes", "on"].includes(value.toLowerCase()))) return true;
  if (value === 0 || value === "0" || (typeof value === "string" && ["false", "no", "off"].includes(value.toLowerCase()))) return false;
  throw new TypeError("skill invocation frontmatter must be boolean");
}

function isAbsent(error) {
  return error?.code === "ENOENT" || error?.code === "ENOTDIR";
}

function errorMessage(error) {
  return error instanceof Error ? error.message : String(error);
}
