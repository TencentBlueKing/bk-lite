import { describe, expect, it } from 'vitest';

import english from '../locales/en.json';
import chinese from '../locales/zh.json';
import { localizeAtom } from '../lib/atom-localization';


function flatten(value: Record<string, unknown>, prefix = ''): Map<string, string> {
  const result = new Map<string, string>();
  Object.entries(value).forEach(([key, item]) => {
    const path = prefix ? `${prefix}.${key}` : key;
    if (item && typeof item === 'object') {
      flatten(item as Record<string, unknown>, path).forEach((message, nestedPath) => result.set(nestedPath, message));
    } else {
      result.set(path, String(item));
    }
  });
  return result;
}

function placeholders(message: string): string[] {
  return [...message.matchAll(/\{(\w+)\}/g)].map((match) => match[1]).sort();
}

describe('编排中心双语契约', () => {
  it('中英文 key 和占位符保持一致', () => {
    const zh = flatten(chinese);
    const en = flatten(english);

    expect([...zh.keys()].sort()).toEqual([...en.keys()].sort());
    zh.forEach((message, key) => {
      expect(placeholders(message), key).toEqual(placeholders(en.get(key) || ''));
    });
  });

  it('将 OpsPilot 原子名称、说明和 Schema 字段切换为英文', () => {
    const messages = flatten(english);
    const atom = localizeAtom({
      key: 'bklite_memory_read',
      name: '记忆读取',
      category: '记忆',
      description: '读取记忆',
      input_schema: { type: 'object', properties: { query: { type: 'string', title: '检索内容' } } },
      output_schema: { type: 'object', properties: { memory_context: { type: 'string', title: '记忆上下文' } } },
    }, (key, fallback) => messages.get(key) || fallback || key);

    expect(atom.name).toBe('Memory Read');
    expect(atom.category).toBe('Memory');
    expect(atom.input_schema?.properties?.query.title).toBe('Query');
    expect(atom.output_schema?.properties?.memory_context.title).toBe('Memory Context');
  });
});
