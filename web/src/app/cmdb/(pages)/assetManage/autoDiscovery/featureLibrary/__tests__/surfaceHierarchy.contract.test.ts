import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

import { describe, expect, it } from 'vitest';

const here = dirname(fileURLToPath(import.meta.url));
const layoutSource = readFileSync(resolve(here, '../layout.tsx'), 'utf8');
const soidSource = readFileSync(resolve(here, '../soid/page.tsx'), 'utf8');
const portSource = readFileSync(resolve(here, '../port/page.tsx'), 'utf8');
const processSource = readFileSync(resolve(here, '../process/page.tsx'), 'utf8');

describe('特征库工作面层级', () => {
  it('标题说明直接落在既有工作面，不再嵌套 TopSection 卡片', () => {
    expect(soidSource).not.toContain("import TopSection");
    expect(portSource).not.toContain("import TopSection");
    expect(processSource).not.toContain("import TopSection");
    expect(soidSource).not.toContain('<TopSection');
    expect(portSource).not.toContain('<TopSection');
    expect(processSource).not.toContain('<TopSection');
  });

  it('路由 Tabs 只保留自身导航线并隐藏空内容槽', () => {
    expect(layoutSource).not.toContain('border-b');
    expect(layoutSource).toContain('[&>.ant-tabs-content-holder]:hidden');
  });

  it('特征库包含 SOID / 端口指纹 / 进程指纹三个 Tab', () => {
    expect(layoutSource).toContain('/featureLibrary/soid');
    expect(layoutSource).toContain('/featureLibrary/port');
    expect(layoutSource).toContain('/featureLibrary/process');
    expect(layoutSource).toContain("t('OidLibrary.processTab')");
  });
});
