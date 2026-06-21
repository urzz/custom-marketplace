import { existsSync, readFileSync } from 'node:fs';
import path from 'node:path';

const filePath = process.argv[2];
const OPERATIONS = ['create', 'update', 'append', 'delete'];
const CONFIDENCES = ['high', 'medium', 'low'];
const DECISIONS = ['accept', 'reject', 'edit', 'defer'];

function fail(message) {
  console.error(message);
  process.exit(1);
}

if (!filePath) {
  fail('usage: node validate-memory-patch.mjs <memory.patch.md>');
}

if (!existsSync(filePath)) {
  fail(`missing memory patch: ${filePath}`);
}

function normalize(value) {
  return path.posix.normalize(String(value || '').replace(/\\/g, '/')).replace(/^\.\//, '');
}

function validTarget(target) {
  const raw = String(target || '').replace(/\\/g, '/').trim();
  const normalized = normalize(raw);
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

function section(raw, headingNames) {
  const names = new Set(headingNames.map((name) => name.toLowerCase()));
  const headingRegex = /^##\s+(.+?)\s*$/gim;
  let match;
  while ((match = headingRegex.exec(raw)) !== null) {
    if (!names.has(match[1].trim().toLowerCase())) continue;
    const start = headingRegex.lastIndex;
    headingRegex.lastIndex = start;
    const next = headingRegex.exec(raw);
    return raw.slice(start, next ? next.index : raw.length);
  }
  return null;
}

function splitTableLine(line) {
  return line.slice(1, -1).split('|').map((cell) => cell.trim());
}

function parseFirstTable(rawSection) {
  if (!rawSection) return { headers: [], rows: [] };
  const lines = rawSection.split(/\r?\n/);
  let start = -1;
  for (let i = 0; i < lines.length; i += 1) {
    const line = lines[i].trim();
    if (line.startsWith('|') && line.endsWith('|')) {
      start = i;
      break;
    }
  }
  if (start === -1) return { headers: [], rows: [] };

  const tableLines = [];
  for (let i = start; i < lines.length; i += 1) {
    const line = lines[i].trim();
    if (!line.startsWith('|') || !line.endsWith('|')) break;
    tableLines.push(line);
  }
  if (tableLines.length < 2) return { headers: [], rows: [] };

  const headers = splitTableLine(tableLines[0]).map((cell) => cell.toLowerCase());
  const rows = [];
  for (const line of tableLines.slice(2)) {
    const cells = splitTableLine(line);
    if (cells.every((cell) => /^:?-+:?$/.test(cell))) continue;
    const row = {};
    for (const [index, header] of headers.entries()) row[header] = cells[index] ?? '';
    if (Object.values(row).some((cell) => String(cell).trim())) rows.push(row);
  }
  return { headers, rows };
}

function parseProposalRows(raw) {
  const proposalSection = section(raw, ['Proposed Updates', 'Proposed Files']);
  const table = parseFirstTable(proposalSection);
  return table.rows.map((row) => ({
    id: row.id,
    target: row.target ?? row.path ?? row.target_path,
    operation: row.operation,
    reason: row.reason,
    confidence: row.confidence,
    hasDecisionColumn: table.headers.includes('decision'),
  }));
}

function parseApprovalRows(raw) {
  const approvalSection = section(raw, ['Human Approval Decisions']);
  if (approvalSection === null) return [];
  return parseFirstTable(approvalSection).rows.map((row) => ({
    id: row.id,
    decision: row.decision,
    approvedContentRef: row.approved_content_ref ?? row.content_ref ?? row.approved_content ?? '',
    note: row.note ?? '',
  }));
}

function metadataValue(block, keyAlternatives) {
  for (const key of keyAlternatives) {
    const escaped = key.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    const match = block.match(new RegExp(`^\\s*(?:[-*]\\s*)?${escaped}:\\s*(.+?)\\s*$`, 'im'));
    if (match) return match[1].trim();
  }
  return '';
}

function parseUpdateBlocks(raw) {
  const blocks = new Map();
  const headingRegex = /^###\s+Update\s+(\S+)\s*$/gim;
  const matches = [...raw.matchAll(headingRegex)];
  for (const [index, match] of matches.entries()) {
    const start = match.index;
    const end = matches[index + 1]?.index ?? raw.length;
    const block = raw.slice(start, end);
    const fenced = [...block.matchAll(/```([^\n`]*)\n([\s\S]*?)```/g)];
    blocks.set(match[1], {
      headingId: match[1],
      id: metadataValue(block, ['id']),
      target: metadataValue(block, ['target', 'target_path', 'path']),
      operation: metadataValue(block, ['operation']),
      reason: metadataValue(block, ['reason']),
      confidence: metadataValue(block, ['confidence']),
      anchors: anchorsInUpdateBlock(block),
      hasFence: fenced.some((fence) => fence[2].trim().length > 0),
      block,
    });
  }
  return blocks;
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

function validApprovedContentRef(ref, proposalId, proposalIds, updateBlocks) {
  const trimmed = String(ref || '').trim();
  if (!trimmed || !proposalId || !proposalIds.has(proposalId)) return false;
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

const raw = readFileSync(filePath, 'utf8');
const proposals = parseProposalRows(raw);
const approvals = parseApprovalRows(raw);
const updateBlocks = parseUpdateBlocks(raw);
const errors = [];

if (!proposals.length) errors.push('memory patch must include a proposal table under ## Proposed Updates or ## Proposed Files');

const proposalIds = new Set();
for (const [index, row] of proposals.entries()) {
  const label = `proposal row ${index + 1}`;
  const operation = String(row.operation || '').toLowerCase();
  const confidence = String(row.confidence || '').toLowerCase();

  if (row.hasDecisionColumn) errors.push(`${label} must not include decision column; use ## Human Approval Decisions for human decisions`);
  if (!row.id) errors.push(`${label} missing id`);
  if (row.id && proposalIds.has(row.id)) errors.push(`${label} duplicate id: ${row.id}`);
  if (row.id) proposalIds.add(row.id);
  if (!row.target || !validTarget(row.target)) errors.push(`${label} target must be under .dev-docs`);
  if (!operation || !OPERATIONS.includes(operation)) errors.push(`${label} operation must be one of: ${OPERATIONS.join(', ')}`);
  if (!row.reason) errors.push(`${label} missing reason`);
  if (!confidence || !CONFIDENCES.includes(confidence)) errors.push(`${label} confidence must be one of: ${CONFIDENCES.join(', ')}`);

  const block = updateBlocks.get(row.id);
  if (!block) {
    errors.push(`${label} missing matching ### Update ${row.id} block`);
    continue;
  }

  if (block.headingId !== row.id || block.id !== row.id) errors.push(`Update ${row.id} block metadata id must match proposal id`);
  if (!block.target || normalize(block.target) !== normalize(row.target)) errors.push(`Update ${row.id} block target must match proposal target`);
  if (!block.operation || block.operation.toLowerCase() !== operation) errors.push(`Update ${row.id} block operation must match proposal operation`);
  if (!block.reason) errors.push(`Update ${row.id} block missing reason`);
  if (!block.confidence || block.confidence.toLowerCase() !== confidence) errors.push(`Update ${row.id} block confidence must match proposal confidence`);
  if (operation !== 'delete' && !block.hasFence) errors.push(`Update ${row.id} block must include fenced content or diff for ${operation}`);
}

for (const [index, row] of approvals.entries()) {
  const label = `approval row ${index + 1}`;
  const decision = String(row.decision || '').toLowerCase();
  if (!row.id) errors.push(`${label} missing id`);
  if (row.id && !proposalIds.has(row.id)) errors.push(`${label} id must refer to a proposal id`);
  if (!decision || !DECISIONS.includes(decision)) errors.push(`${label} decision must be one of: ${DECISIONS.join(', ')}`);
  if (['accept', 'edit'].includes(decision) && !validApprovedContentRef(row.approvedContentRef, row.id, proposalIds, updateBlocks)) {
    errors.push(`${label} accept/edit requires approved_content_ref to reference existing approved content for ${row.id}`);
  }
}

if (errors.length) fail(errors.join('\n'));
console.log(`valid memory patch: ${filePath}`);
