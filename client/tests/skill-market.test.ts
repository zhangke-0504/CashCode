import assert from 'node:assert/strict';
import test from 'node:test';

import { APP_VIEWS, type SkillSummary } from '../src/types.ts';
import {
  buildApiRequestInit,
  buildInvalidSkillDeletePath,
  buildSkillsQuery,
} from '../src/lib/api.ts';
import {
  skillCanManage,
  skillDisplayName,
  skillEditorError,
  skillInvalidCanDelete,
  skillInvalidDiagnostics,
  skillPageCount,
  skillSelectionReceipt,
  skillSourceLabel,
  skillStatusLabel,
  validateSkillZipName,
} from '../src/lib/skill-market.ts';

function skill(overrides: Partial<SkillSummary> = {}): SkillSummary {
  return {
    name: 'review',
    display_name: 'review',
    description: 'Review code',
    version: 1,
    tags: ['code'],
    triggers: ['review'],
    always: false,
    source: 'user',
    enabled: true,
    availability: 'available',
    missing: [],
    mutable: true,
    hash: 'abc',
    shadowed_sources: [],
    validation_errors: [],
    requires: { tools: [], mcp_servers: [], bins: [], env: [] },
    optional: { tools: [], mcp_servers: [], bins: [], env: [] },
    ...overrides,
  };
}

test('includes the Skill market in application views', () => {
  assert.deepEqual(APP_VIEWS, ['chat', 'mcp-market', 'skill-market']);
});

test('builds encoded paginated Skill queries', () => {
  assert.equal(
    buildSkillsQuery({ query: '  code review  ', page: 2, page_size: 20, enabled: false }),
    '?enabled=false&query=code+review&page=2&page_size=20',
  );
  assert.equal(buildSkillsQuery(), '');
});

test('keeps multipart boundaries under browser control', () => {
  const form = new FormData();
  form.append('file', new Blob(['zip']), 'skill.zip');
  const multipart = buildApiRequestInit({ method: 'POST', body: form });
  assert.equal(new Headers(multipart.headers).has('Content-Type'), false);

  const json = buildApiRequestInit({ method: 'PUT', body: '{}' });
  assert.equal(new Headers(json.headers).get('Content-Type'), 'application/json');
});

test('maps ownership and status to protected market actions', () => {
  const builtin = skill({ source: 'builtin', mutable: false });
  const agent = skill({ source: 'agent' });
  const disabled = skill({ enabled: false, availability: 'disabled' });

  assert.equal(skillSourceLabel(builtin), '内置');
  assert.equal(skillCanManage(builtin), false);
  assert.equal(skillSourceLabel(agent), '聊天创建');
  assert.equal(skillCanManage(agent), true);
  assert.equal(skillStatusLabel(disabled), '已禁用');
});

test('uses localized labels while preserving canonical selection identity', () => {
  const localized = skill({ name: 'renzhi-niuqu', display_name: '认知扭曲' });
  const fallback = skill({ name: 'plain-skill', display_name: '' });

  assert.equal(skillDisplayName(localized), '认知扭曲');
  assert.equal(skillDisplayName(fallback), 'plain-skill');
  assert.deepEqual(skillSelectionReceipt(localized), {
    name: 'renzhi-niuqu',
    label: '认知扭曲',
  });
});

test('bounds invalid diagnostics and keeps them non-selectable and protected', () => {
  const diagnostics = skillInvalidDiagnostics({
    [`agent:${'d'.repeat(120)}`]: ['x'.repeat(500), 'second', 'third', 'ignored'],
  });

  assert.equal(diagnostics.length, 1);
  assert.equal(diagnostics[0].source, 'agent');
  assert.equal(diagnostics[0].directory.length, 80);
  assert.equal(diagnostics[0].errors.length, 3);
  assert.equal(diagnostics[0].errors[0].length, 240);
  assert.equal(diagnostics[0].selectable, false);
  assert.equal(diagnostics[0].manageable, false);
  assert.equal(skillInvalidCanDelete(diagnostics[0]), true);

  const builtin = skillInvalidDiagnostics({ 'builtin:broken': ['invalid'] })[0];
  assert.equal(skillInvalidCanDelete(builtin), false);
  assert.equal(
    buildInvalidSkillDeletePath('agent', '中文 invalid'),
    '/skills/invalid/agent/%E4%B8%AD%E6%96%87%20invalid',
  );
});

test('validates upload names, paging, and edit conflicts', () => {
  assert.equal(validateSkillZipName('workflow.ZIP'), null);
  assert.match(validateSkillZipName('workflow.tar.gz') ?? '', /\.zip/);
  assert.equal(skillPageCount(0, 20), 1);
  assert.equal(skillPageCount(41, 20), 3);
  assert.match(skillEditorError(409, 'conflict'), /重新加载/);
  assert.equal(skillEditorError(422, 'bad yaml'), 'bad yaml');
});
