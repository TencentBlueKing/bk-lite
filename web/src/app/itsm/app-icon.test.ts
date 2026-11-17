import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { expect, it } from 'vitest';

it('ITSM 应用配置引用的图标在公共 SVG 图标库中有实际图形', () => {
  const menu = JSON.parse(readFileSync(resolve(process.cwd(), '../server/support-files/system_mgmt/menus/itsm.json'), 'utf8'));
  const sprite = readFileSync(resolve(process.cwd(), 'public/iconfont.js'), 'utf8');
  const symbol = sprite.match(new RegExp(`<symbol id="icon-${menu.icon}"[^>]*>(.*?)</symbol>`));
  expect(symbol).not.toBeNull();
  expect(symbol?.[1]).toMatch(/<(path|rect|circle|polygon)\b/);
});
