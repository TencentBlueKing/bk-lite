import { describe, expect, it, vi } from 'vitest';
import {
  getSkillPackageKey,
  loadSkillSettingsAuxiliary,
  mergeSkillPackageCatalog,
} from '../skillSettingsBootstrap';
import type { SkillPackage } from '@/app/opspilot/types/skill';
import type { WikiKnowledgeBase } from '@/app/opspilot/types/wiki';

const pkg = (overrides: Partial<SkillPackage>): SkillPackage => ({
  id: 1,
  package_id: 'k8s',
  name: 'K8s',
  version: '1.0.0',
  ...overrides,
});

const kb = (overrides: Partial<WikiKnowledgeBase>): WikiKnowledgeBase => ({
  id: 1,
  name: '运维知识库',
  team: [1],
  ...overrides,
});

const httpError = (status: number) => Object.assign(new Error(`http ${status}`), { status });

describe('skillSettingsBootstrap', () => {
  it('keeps loading models and knowledge bases when skill packages 404', async () => {
    const fetchKnowledgeBases = vi.fn().mockResolvedValue([kb({ id: 3 })]);
    const result = await loadSkillSettingsAuxiliary({
      fetchLlmModels: vi.fn().mockResolvedValue([{ id: 9, name: 'gpt', enabled: true }]),
      fetchSkillPackages: vi.fn().mockRejectedValue(httpError(404)),
      fetchKnowledgeBases,
    });

    expect(fetchKnowledgeBases).toHaveBeenCalledTimes(1);
    expect(result.llmModels).toEqual([{ id: 9, name: 'gpt', enabled: true }]);
    expect(result.skillPackages).toEqual([]);
    expect(result.knowledgeBases).toEqual([kb({ id: 3 })]);
  });

  it('keeps loading packages when the knowledge base list 404s', async () => {
    const fetchSkillPackages = vi.fn().mockResolvedValue({
      items: [pkg({ id: 2 })],
      count: 1,
    });
    const result = await loadSkillSettingsAuxiliary({
      fetchLlmModels: vi.fn().mockResolvedValue([]),
      fetchSkillPackages,
      fetchKnowledgeBases: vi.fn().mockRejectedValue(httpError(404)),
    });

    expect(fetchSkillPackages).toHaveBeenCalledTimes(1);
    expect(result.skillPackages).toEqual([pkg({ id: 2 })]);
    expect(result.knowledgeBases).toEqual([]);
  });

  it('keeps loading packages when the model list is forbidden', async () => {
    const result = await loadSkillSettingsAuxiliary({
      fetchLlmModels: vi.fn().mockRejectedValue(httpError(403)),
      fetchSkillPackages: vi.fn().mockResolvedValue({
        items: [pkg({ id: 2 })],
        count: 1,
      }),
      fetchKnowledgeBases: vi.fn().mockResolvedValue([]),
    });

    expect(result.llmModels).toEqual([]);
    expect(result.skillPackages).toEqual([pkg({ id: 2 })]);
  });

  it('merges selected packages into an empty catalog so attached skills still render', () => {
    const selected = [pkg({ id: 7, name: '已挂接' })];
    const merged = mergeSkillPackageCatalog([], selected);
    expect(merged.map(getSkillPackageKey)).toEqual(['7']);
    expect(merged[0].name).toBe('已挂接');
  });
});
