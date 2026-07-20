import { readFileSync } from 'node:fs';
import { join } from 'node:path';

const root = process.cwd();
const read = (path: string) => readFileSync(join(root, path), 'utf8');
const assertIncludes = (content: string, needle: string, label: string) => {
  if (!content.includes(needle)) {
    throw new Error(`${label} missing: ${needle}`);
  }
};

const wikiTypes = read('src/app/opspilot/types/wiki.ts');
const globalTypes = read('src/app/opspilot/types/global.ts');
const citations = read('src/app/opspilot/components/custom-chat-sse/WikiCitations.tsx');
const zh = read('src/app/opspilot/locales/zh.json');
const en = read('src/app/opspilot/locales/en.json');

assertIncludes(wikiTypes, 'export interface WikiSearchExplanation', 'wiki search explanation type');
assertIncludes(wikiTypes, "matched_by: Array<'keyword' | 'vector' | 'chunk_vector' | string>", 'matched_by type');
assertIncludes(wikiTypes, 'keyword_score?: number', 'keyword score type');
assertIncludes(wikiTypes, 'vector_score?: number', 'vector score type');
assertIncludes(wikiTypes, 'explanation?: WikiSearchExplanation', 'search hit explanation field');
assertIncludes(wikiTypes, 'explanation?: WikiSearchExplanation', 'citation explanation field');

assertIncludes(globalTypes, 'WikiSearchExplanation', 'global explanation type');
assertIncludes(globalTypes, 'explanation?: WikiSearchExplanation', 'global citation explanation field');

assertIncludes(citations, 'c.explanation?.matched_by', 'citation explanation rendering');
assertIncludes(citations, "t('wiki.retrievalKeyword')", 'keyword explanation label');
assertIncludes(citations, "t('wiki.retrievalVector')", 'vector explanation label');
assertIncludes(citations, "t('wiki.retrievalChunkVector')", 'chunk vector explanation label');
assertIncludes(citations, "t('wiki.retrievalGraph')", 'graph explanation label');

assertIncludes(zh, '"retrievalKeyword": "关键词"', 'zh keyword label');
assertIncludes(zh, '"retrievalVector": "向量"', 'zh vector label');
assertIncludes(zh, '"retrievalChunkVector": "分块向量"', 'zh chunk vector label');
assertIncludes(zh, '"retrievalGraph": "图谱扩展"', 'zh graph label');
assertIncludes(en, '"retrievalKeyword": "Keyword"', 'en keyword label');
assertIncludes(en, '"retrievalVector": "Vector"', 'en vector label');
assertIncludes(en, '"retrievalChunkVector": "Chunk Vector"', 'en chunk vector label');
assertIncludes(en, '"retrievalGraph": "Graph Expansion"', 'en graph label');

console.log('wiki-search-explanation static checks passed');
