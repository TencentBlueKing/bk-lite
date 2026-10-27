import { describe, expect, it } from 'vitest';

import { localizedEnumLabel, localizedModelObject } from '../changeRecordLabel';

const catalog: Record<string, string> = {
  'OperationLog.scenarioOpts.ordinary_attribute_change': 'Attribute Change',
  'OperationLog.objectOpts.instance': 'Asset Instance',
};

const t = (id: string) => catalog[id] || id;

describe('localizedEnumLabel', () => {
  it('uses the UI catalog when the scenario key is known, even if the API returns Chinese', () => {
    expect(
      localizedEnumLabel(t, 'OperationLog.scenarioOpts', 'ordinary_attribute_change', {
        ordinary_attribute_change: '普通属性变更',
      }),
    ).toBe('Attribute Change');
  });

  it('falls back to the API label for an unknown key', () => {
    expect(
      localizedEnumLabel(t, 'OperationLog.scenarioOpts', 'future_scenario', {
        future_scenario: 'Future',
      }),
    ).toBe('Future');
  });
});

describe('localizedModelObject', () => {
  it('translates built-in object labels and leaves custom text unchanged', () => {
    expect(localizedModelObject(t, '资产实例')).toBe('Asset Instance');
    expect(localizedModelObject(t, '阿里云ECS')).toBe('阿里云ECS');
  });
});
