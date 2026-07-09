import { readFileSync } from 'node:fs';
import { join } from 'node:path';

const root = process.cwd();
const read = (path: string) => readFileSync(join(root, path), 'utf8');
const assertIncludes = (content: string, needle: string, label: string) => {
  if (!content.includes(needle)) {
    throw new Error(`${label} missing: ${needle}`);
  }
};

const api = read('src/app/opspilot/api/wiki.ts');
const types = read('src/app/opspilot/types/wiki.ts');
const pageTab = read('src/app/opspilot/components/wiki/PageTab.tsx');
const zh = read('src/app/opspilot/locales/zh.json');
const en = read('src/app/opspilot/locales/en.json');

assertIncludes(types, 'export interface WikiPageSource', 'page source type');
assertIncludes(types, 'export interface WikiPageSourcesResult', 'page sources result type');
assertIncludes(types, 'locator_raw?: string', 'raw locator fallback');
assertIncludes(types, 'material_version', 'material version source detail');


if (pageTab.includes('source.material_version.content_hash')) {
  throw new Error('PageTab should not expose material content_hash in user-facing source cards');
}

assertIncludes(api, 'fetchPageSources', 'page sources api');
assertIncludes(api, '/sources/', 'page sources endpoint');
assertIncludes(api, 'WikiPageSourcesResult', 'api return type');

assertIncludes(pageTab, 'fetchPageSources', 'PageTab api usage');
assertIncludes(pageTab, 'pageSourcesVisible', 'PageTab source drawer/modal state');
assertIncludes(pageTab, 'width="min(960px, calc(100vw - 48px))"', 'PageTab source drawer width matches material detail');
assertIncludes(pageTab, "t('wiki.pageSources')", 'PageTab source action label');
assertIncludes(pageTab, 'source.locator?.chunk_index', 'PageTab chunk locator rendering');
assertIncludes(pageTab, 'source.snippet', 'PageTab snippet rendering');
assertIncludes(pageTab, 'fetchMaterialInfo', 'PageTab material detail api usage');
assertIncludes(pageTab, 'sourceMaterialDetail', 'PageTab source material detail modal state');
assertIncludes(pageTab, 'openSourceMaterialDetail(source.material.id)', 'PageTab source material detail action');
const materialDetailActionCount = (pageTab.match(/openSourceMaterialDetail\(source\.material\.id\)/g) || []).length;
if (materialDetailActionCount !== 1) {
  throw new Error(`PageTab should only open material detail from the material name, got ${materialDetailActionCount} actions`);
}
assertIncludes(pageTab, '<Modal', 'PageTab source material detail modal');
if (pageTab.includes("<Drawer\n        title={`${t('wiki.detail')}: ${sourceMaterialDetail?.material?.name")) {
  throw new Error('PageTab should not render source material detail as a nested drawer');
}
if (pageTab.includes('wiki.webSyncPolicy')) {
  throw new Error('PageTab should use the existing wiki.webSyncEnabled i18n key, not an unmapped webSyncPolicy key');
}
assertIncludes(pageTab, "t('wiki.webSyncEnabled')", 'PageTab mapped web sync label');
assertIncludes(pageTab, "t('wiki.sourceMaterial')", 'PageTab source material label');
assertIncludes(pageTab, 'sourceMaterialDetail?.material?.name', 'PageTab source material detail title');
assertIncludes(pageTab, "import MarkdownRenderer from '@/components/markdown'", 'PageTab MarkdownRenderer import');
assertIncludes(pageTab, '<MarkdownRenderer content={source.snippet} />', 'PageTab source snippet markdown rendering');
assertIncludes(pageTab, 'source.locator_raw', 'PageTab raw locator rendering');

if (pageTab.includes('whitespace-pre-wrap break-words text-sm text-[var(--color-text-2)]">{source.snippet}</div>')) {
  throw new Error('PageTab should not render source snippets as plain pre-wrapped text');
}

assertIncludes(zh, '"pageSources": "来源"', 'zh page sources label');
assertIncludes(zh, '"sourceSnippet": "来源片段"', 'zh source snippet label');
assertIncludes(zh, '"webSyncEnabled": "定时刷新网页资料"', 'zh mapped web sync label');
assertIncludes(en, '"pageSources": "Sources"', 'en page sources label');
assertIncludes(en, '"sourceSnippet": "Source Snippet"', 'en source snippet label');
assertIncludes(en, '"webSyncEnabled": "Scheduled web refresh"', 'en mapped web sync label');

console.log('wiki-page-sources static checks passed');
