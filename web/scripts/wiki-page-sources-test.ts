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

assertIncludes(api, 'fetchPageSources', 'page sources api');
assertIncludes(api, '/sources/', 'page sources endpoint');
assertIncludes(api, 'WikiPageSourcesResult', 'api return type');

assertIncludes(pageTab, 'fetchPageSources', 'PageTab api usage');
assertIncludes(pageTab, 'pageSourcesVisible', 'PageTab source drawer/modal state');
assertIncludes(pageTab, "t('wiki.pageSources')", 'PageTab source action label');
assertIncludes(pageTab, 'source.locator?.chunk_index', 'PageTab chunk locator rendering');
assertIncludes(pageTab, 'source.snippet', 'PageTab snippet rendering');
assertIncludes(pageTab, 'source.locator_raw', 'PageTab raw locator rendering');

assertIncludes(zh, '"pageSources": "来源"', 'zh page sources label');
assertIncludes(zh, '"sourceSnippet": "来源片段"', 'zh source snippet label');
assertIncludes(en, '"pageSources": "Sources"', 'en page sources label');
assertIncludes(en, '"sourceSnippet": "Source Snippet"', 'en source snippet label');

console.log('wiki-page-sources static checks passed');
