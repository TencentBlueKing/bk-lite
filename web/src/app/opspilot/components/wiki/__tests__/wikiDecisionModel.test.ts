import { describe, expect, it } from 'vitest';
import type { CheckItem } from '@/app/opspilot/types/wiki';
import {
  buildDecisionViewModel,
  getKnowledgeConflictAlternatives,
  resolveSelectedConflictAlternative,
} from '../wikiDecisionModel';

const baseConflictItem = (): CheckItem => ({
  id: 11,
  knowledge_base: 1,
  check_type: 'cannot_merge',
  status: 'open',
  candidate_version: 102,
  candidate: { id: 102, body: 'candidate-b' },
  decision_key: 'a'.repeat(64),
  decision_type: 'knowledge_conflict',
  decision_context: {
    decision_type: 'knowledge_conflict',
    subject_key: 'page::concept::topic',
    schema_fingerprint: 'schema-1',
    locked_current_version_id: 1,
    current_body_hash: 'current-hash',
    candidate_body_hash: 'candidate-b-hash',
    candidate_version_id: 102,
    page_identity: { page_id: 9, title: '主题页', page_type: 'concept' },
    incoming: {
      material_id: 22,
      material_version_id: 222,
      content_hash: 'hash-b',
    },
    participants: [
      { material_id: 10, content_hash: 'hash-source' },
      { material_id: 21, content_hash: 'hash-a' },
      { material_id: 22, content_hash: 'hash-b' },
    ],
    alternatives: [
      {
        material_id: 21,
        material_name: '资料A',
        material_version_id: 211,
        content_hash: 'hash-a',
        candidate_version_id: 101,
        body_hash: 'candidate-a-hash',
      },
      {
        material_id: 22,
        material_name: '资料B',
        material_version_id: 222,
        content_hash: 'hash-b',
        candidate_version_id: 102,
        body_hash: 'candidate-b-hash',
      },
    ],
  },
  current_knowledge: {
    id: 9,
    title: '主题页',
    page_type: 'concept',
    body: 'current body',
    source_label: '来源',
    version_label: 'v1',
  },
  new_knowledge: {
    id: 9,
    title: '主题页',
    page_type: 'concept',
    body: 'candidate-b',
    source_label: '资料B',
    material_id: 22,
    version_label: 'v3',
  },
  alternatives: [
    {
      kind: 'current',
      id: 9,
      title: '主题页',
      page_type: 'concept',
      body: 'current body',
      source_label: '来源',
      material_id: undefined,
    },
    {
      kind: 'candidate',
      id: 9,
      title: '主题页',
      page_type: 'concept',
      body: 'candidate-a',
      source_label: '资料A',
      material_id: 21,
      material_version_id: 211,
      content_hash: 'hash-a',
      candidate_version_id: 101,
      body_hash: 'candidate-a-hash',
    },
    {
      kind: 'candidate',
      id: 9,
      title: '主题页',
      page_type: 'concept',
      body: 'candidate-b',
      source_label: '资料B',
      material_id: 22,
      material_version_id: 222,
      content_hash: 'hash-b',
      candidate_version_id: 102,
      body_hash: 'candidate-b-hash',
    },
  ],
});

describe('wikiDecisionModel multi-candidate', () => {
  it('exposes current + candidate alternatives for knowledge conflict', () => {
    const item = baseConflictItem();
    const alternatives = getKnowledgeConflictAlternatives(item);
    expect(alternatives).toHaveLength(3);
    expect(alternatives.filter((item) => item.kind === 'candidate')).toHaveLength(2);

    const model = buildDecisionViewModel(item);
    expect(model?.kind).toBe('knowledge_conflict');
    expect(model?.alternatives.filter((item) => item.kind === 'candidate')).toHaveLength(2);
  });

  it('resolves selected alternative by material_id for decide payload', () => {
    const item = baseConflictItem();
    const selected = resolveSelectedConflictAlternative(item, 21);
    expect(selected?.materialId).toBe(21);
    expect(selected?.body).toBe('candidate-a');
    expect(selected?.candidateVersionId).toBe(101);
  });
});
