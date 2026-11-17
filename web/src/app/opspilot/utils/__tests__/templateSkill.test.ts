import { describe, expect, it, vi } from 'vitest';
import { bindTemplateTools, collectSkillNames, nextTemplateSkillName } from '../templateSkill';

describe('nextTemplateSkillName', () => {
  it('uses the template name when the organization does not already have it', () => {
    expect(nextTemplateSkillName('Kubernetes 助手', ['Postgres DB 助手'])).toBe('Kubernetes 助手');
  });

  it('adds 副本 and then a number when the name is taken', () => {
    const base = 'Kubernetes 助手';
    expect(nextTemplateSkillName(base, [base])).toBe('Kubernetes 助手 副本');
    expect(nextTemplateSkillName(base, [base, 'Kubernetes 助手 副本'])).toBe('Kubernetes 助手 副本2');
    expect(nextTemplateSkillName(base, [base, 'Kubernetes 助手 副本', 'Kubernetes 助手 副本2'])).toBe('Kubernetes 助手 副本3');
  });
});

describe('bindTemplateTools', () => {
  it('attaches the catalog tool by name with empty connection parameters', () => {
    expect(bindTemplateTools([{ name: 'kubernetes' }], [{ id: 8, name: 'kubernetes', icon: 'k8s' }])).toEqual([
      { id: 8, name: 'kubernetes', icon: 'k8s', kwargs: [] },
    ]);
  });
});

describe('collectSkillNames', () => {
  it('walks every page of the current organization', async () => {
    const fetchPage = vi.fn(async (page: number) => {
      if (page === 1) {
        return { items: [{ name: 'Kubernetes 助手' }], count: 2 };
      }
      return { items: [{ name: 'Kubernetes 助手 副本' }], count: 2 };
    });
    await expect(collectSkillNames(fetchPage, 1)).resolves.toEqual(['Kubernetes 助手', 'Kubernetes 助手 副本']);
  });
});
