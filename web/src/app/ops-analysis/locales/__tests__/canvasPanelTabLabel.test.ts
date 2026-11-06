import assert from 'node:assert/strict';
import { readdirSync, readFileSync, statSync } from 'node:fs';
import { join } from 'node:path';
import test from 'node:test';
import { fileURLToPath } from 'node:url';

const readLocale = (locale: 'en' | 'zh') =>
  JSON.parse(readFileSync(new URL(`../${locale}.json`, import.meta.url), 'utf8'));

const sourceFiles = (dir: string, out: string[] = []): string[] => {
  for (const entry of readdirSync(dir)) {
    if (entry === '__tests__') {
      continue;
    }
    const path = join(dir, entry);
    if (statSync(path).isDirectory()) {
      sourceFiles(path, out);
      continue;
    }
    if (entry.endsWith('.ts') || entry.endsWith('.tsx')) {
      out.push(path);
    }
  }
  return out;
};

test('canvas panel tab is 画布 / Canvases and directory copy stays put', () => {
  const zh = readLocale('zh');
  const en = readLocale('en');

  assert.equal(zh.opsCarousel.directory, '画布');
  assert.equal(en.opsCarousel.directory, 'Canvases');
  assert.equal(zh.opsCarousel.carousel, '轮播');
  assert.equal(en.opsCarousel.carousel, 'Carousel');

  assert.equal(zh.opsAnalysisSidebar.title, '目录管理');
  assert.equal(en.opsAnalysisSidebar.title, 'Directory Management');
  assert.equal(zh.opsAnalysisSidebar.expandDirectory, '展开目录');
  assert.equal(zh.opsAnalysisSidebar.collapseDirectory, '收起目录');
  assert.equal(zh.opsAnalysisSidebar.editDir, '编辑目录');
  assert.equal(zh.opsAnalysisSidebar.addDir, '新增目录');
  assert.equal(zh.opsAnalysisSidebar.selectItem, '请选择一个画布');
  assert.equal(
    zh.opsAnalysisSidebar.selectItemHint,
    '从最近访问继续，或从左侧目录选择',
  );
  assert.equal(zh.opsCarousel.treeLoadFailed, '目录加载失败，请关闭后重试');

  const appRoot = fileURLToPath(new URL('../..', import.meta.url));
  const hits = sourceFiles(appRoot).flatMap((path) => {
    const text = readFileSync(path, 'utf8');
    const count = text.match(/opsCarousel\.directory/g)?.length ?? 0;
    return count === 0 ? [] : [{ path, count, text }];
  });

  assert.equal(hits.length, 1);
  assert.equal(hits[0].count, 1);
  assert.match(hits[0].path, /components\/sidebar\.tsx$/);
  assert.match(
    hits[0].text,
    /label: t\('opsCarousel\.directory'\), value: 'directory'/,
  );
});
