import assert from 'node:assert/strict';
import test from 'node:test';

import {
  MAX_CAPABILITY_SELECTIONS,
  addMcpSelection,
  addSkillSelection,
  buildMessageFrame,
  filterCapabilities,
  movePickerIndex,
  normalizePersistedMessage,
  normalizeSelectionDraft,
  optimisticMessageFromFrame,
  parseCapabilityTrigger,
  pickerBackLevel,
  replaceCapabilityTrigger,
} from '../src/lib/selections.ts';

const emptyDraft = () => ({ skills: [], mcps: [] });

test('deduplicates canonical selections and preserves typed identities', () => {
  const draft = addSkillSelection(emptyDraft(), { name: 'code-review', label: '代码审查' });
  const duplicate = addSkillSelection(draft, { name: 'code-review', label: '其他标签' });
  const withMcp = addMcpSelection(duplicate, { server: 'github', label: 'GitHub MCP' });

  assert.deepEqual(withMcp, {
    skills: [{ name: 'code-review', label: '代码审查' }],
    mcps: [{ server: 'github', label: 'GitHub MCP' }],
  });
});

test('rejects invalid identities and more than eight combined selections', () => {
  assert.throws(
    () => addSkillSelection(emptyDraft(), { name: 'Bad Skill' }),
    /Skill 标识无效/,
  );

  const tooMany = {
    skills: Array.from({ length: MAX_CAPABILITY_SELECTIONS }, (_, index) => ({ name: `skill-${index}` })),
    mcps: [{ server: 'ninth' }],
  };
  assert.throws(() => normalizeSelectionDraft(tooMany), /最多选择 8 个/);
});

test('parses only boundary triggers and removes the active query', () => {
  assert.equal(parseCapabilityTrigger('mail@example.com', 16), null);
  assert.deepEqual(parseCapabilityTrigger('请使用 @git 完成', 7), {
    start: 4,
    end: 7,
    query: 'gi',
  });
  assert.deepEqual(
    replaceCapabilityTrigger('请使用 @git 完成', { start: 4, end: 8, query: 'git' }),
    { text: '请使用  完成', caret: 4 },
  );
});

test('builds plain content with canonical metadata and omits empty metadata', () => {
  assert.deepEqual(buildMessageFrame('chat-1', '  执行任务  ', emptyDraft()), {
    type: 'message',
    chat_id: 'chat-1',
    content: '执行任务',
  });

  assert.deepEqual(
    buildMessageFrame('chat-1', '执行任务', {
      skills: [{ name: 'review', label: '审查' }],
      mcps: [{ server: 'github', label: 'GitHub' }],
    }),
    {
      type: 'message',
      chat_id: 'chat-1',
      content: '执行任务',
      metadata: {
        mentioned_skills: [{ name: 'review', label: '审查' }],
        selected_mcp_connectors: [{ server: 'github', label: 'GitHub' }],
      },
    },
  );
});

test('filters picker rows across display name, identity, and description', () => {
  const rows = [
    { name: 'github-tools', label: '代码平台', description: 'Issues and pull requests' },
    { name: 'weather', label: '天气', description: 'Forecast data' },
  ];
  const searchable = (item: (typeof rows)[number]) => [item.name, item.label, item.description];

  assert.deepEqual(filterCapabilities(rows, '代码', searchable), [rows[0]]);
  assert.deepEqual(filterCapabilities(rows, 'FORECAST', searchable), [rows[1]]);
  assert.deepEqual(filterCapabilities(rows, 'github', searchable), [rows[0]]);
});

test('wraps keyboard navigation and returns from a second-level picker', () => {
  assert.equal(movePickerIndex(0, 'previous', 3), 2);
  assert.equal(movePickerIndex(2, 'next', 3), 0);
  assert.equal(movePickerIndex(4, 'next', 0), 0);
  assert.equal(pickerBackLevel('mcp'), 'category');
  assert.equal(pickerBackLevel('skill'), 'category');
  assert.equal(pickerBackLevel('category'), null);
});

test('creates optimistic messages with the same receipts as the outbound frame', () => {
  const frame = buildMessageFrame('chat-2', '检查状态', {
    skills: [{ name: 'review', label: '代码审查' }],
    mcps: [{ server: 'github', label: 'GitHub' }],
  });

  assert.deepEqual(optimisticMessageFromFrame(frame, 'message-1'), {
    id: 'message-1',
    role: 'user',
    content: '检查状态',
    mentioned_skills: [{ name: 'review', label: '代码审查' }],
    selected_mcp_connectors: [{ server: 'github', label: 'GitHub' }],
  });
});

test('normalizes persisted receipts, deduplicates identities, and falls back from bad labels', () => {
  const message = normalizePersistedMessage({
    role: 'user',
    content: '历史消息',
    mentioned_skills: [
      { name: 'review', label: '审查' },
      { name: 'review', label: '重复' },
      { name: 'weather', label: 'x'.repeat(101) },
      { name: 'Invalid Skill', label: '忽略' },
    ],
    selected_mcp_connectors: [
      { server: 'github', label: 'GitHub' },
      { server: 'Bad MCP', label: '忽略' },
    ],
  });

  assert.deepEqual(message, {
    role: 'user',
    content: '历史消息',
    mentioned_skills: [{ name: 'review', label: '审查' }, { name: 'weather' }],
    selected_mcp_connectors: [{ server: 'github', label: 'GitHub' }],
  });
});
