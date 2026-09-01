import { describe, expect, it } from 'vitest';

import en from '@/locales/en.json';
import zh from '@/locales/zh.json';
import {
  resolveAppDescription,
  resolveAppDisplayName,
  resolveAppTag,
} from '../appDisplayName';

type LocaleTable = Record<string, unknown>;

const lookup = (table: LocaleTable, id: string): string | undefined => {
  const parts = id.split('.');
  let current: unknown = table;
  for (const part of parts) {
    if (!current || typeof current !== 'object') {
      return undefined;
    }
    current = (current as LocaleTable)[part];
  }
  return typeof current === 'string' ? current : undefined;
};

const makeT = (table: LocaleTable) => (id: string, fallback?: string) =>
  lookup(table, id) || fallback || id;

const tZh = makeT(zh as LocaleTable);
const tEn = makeT(en as LocaleTable);

describe('resolveAppDisplayName', () => {
  it('uses product Chinese names for built-in Console apps', () => {
    expect(resolveAppDisplayName({ name: 'monitor', display_name: 'Monitor', is_build_in: true }, tZh)).toBe('监控中心');
    expect(resolveAppDisplayName({ name: 'log', display_name: 'Log', is_build_in: true }, tZh)).toBe('日志中心');
    expect(resolveAppDisplayName({ name: 'cmdb', display_name: 'CMDB', is_build_in: true }, tZh)).toBe('CMDB');
    expect(resolveAppDisplayName({ name: 'alarm', display_name: 'Alarm', is_build_in: true }, tZh)).toBe('告警中心');
    expect(resolveAppDisplayName({ name: 'job', display_name: 'Job', is_build_in: true }, tZh)).toBe('作业管理');
    expect(resolveAppDisplayName({ name: 'ops-analysis', display_name: 'OpsAnalysis', is_build_in: true }, tZh)).toBe('运营分析');
    expect(resolveAppDisplayName({ name: 'ops-console', display_name: 'OpsConsole', is_build_in: true }, tZh)).toBe('控制台');
    expect(resolveAppDisplayName({ name: 'system-manager', display_name: 'Setting', is_build_in: true }, tZh)).toBe('系统管理');
    expect(resolveAppDisplayName({ name: 'node', display_name: 'Node', is_build_in: true }, tZh)).toBe('节点管理');
    expect(resolveAppDisplayName({ name: 'opspilot', display_name: 'OpsPilot', is_build_in: true }, tZh)).toBe('OpsPilot');
    expect(resolveAppDisplayName({ name: 'mlops', display_name: 'MLOps', is_build_in: true }, tZh)).toBe('MLOps');
  });

  it('keeps custom app display names', () => {
    expect(resolveAppDisplayName({ name: 'acme', display_name: 'Acme Ops', is_build_in: false }, tZh)).toBe('Acme Ops');
  });

  it('falls back to display_name when the app is unknown', () => {
    expect(resolveAppDisplayName({ name: 'unknown', display_name: 'Stored Name' }, tZh)).toBe('Stored Name');
  });

  it('keeps English product names in locale files', () => {
    expect(en.apps.monitor).toBe('Monitor Center');
    expect(en.apps.alarm).toBe('Alert Center');
    expect(en.apps['system-manager']).toBe('System Management');
    expect(zh.apps.monitor).toBe('监控中心');
    expect(zh.apps.alarm).toBe('告警中心');
    expect(zh.apps['system-manager']).toBe('系统管理');
  });
});

describe('resolveAppDescription', () => {
  it('translates a cached Chinese description when the UI locale is English', () => {
    expect(
      resolveAppDescription(
        {
          name: 'system-manager',
          description: '涵盖用户和组织角色权限管理，通过精细化权限控制，确保资源访问安全',
          is_build_in: true,
        },
        tEn
      )
    ).toBe(en.app['system-manager']);
    expect(
      resolveAppDescription(
        {
          name: 'monitor',
          description: '用于实时监测和管理系统运行状态的平台',
          is_build_in: true,
        },
        tEn
      )
    ).toBe(en.app.monitor);
  });

  it('keeps custom app descriptions such as ITSM placeholders', () => {
    expect(
      resolveAppDescription(
        { name: 'itsm', description: 'test', is_build_in: false },
        tEn
      )
    ).toBe('test');
  });
});

describe('resolveAppTag', () => {
  it('translates tag keys and already-localized Chinese tags into English', () => {
    expect(resolveAppTag('tag.user_management', tEn)).toBe('User Management');
    expect(resolveAppTag('用户管理', tEn)).toBe('User Management');
    expect(resolveAppTag('多对象接入', tEn)).toBe('Multi-Object Access');
    expect(resolveAppTag('补丁扫描', tEn)).toBe('Patch Scanning');
  });

  it('keeps unknown custom tags', () => {
    expect(resolveAppTag('Release Train', tEn)).toBe('Release Train');
  });
});
