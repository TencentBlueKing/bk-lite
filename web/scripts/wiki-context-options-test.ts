import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';

const root = process.cwd();
const read = (file: string) => fs.readFileSync(path.join(root, file), 'utf8');

const wikiApi = read('src/app/opspilot/api/wiki.ts');
const wikiTypes = read('src/app/opspilot/types/wiki.ts');

assert.match(wikiTypes, /export type WikiRetrievalMode = 'keyword' \| 'hybrid' \| 'chunk'/);
assert.match(wikiTypes, /export interface WikiContextOptions/);
assert.match(wikiTypes, /top_k\?: number/);
assert.match(wikiTypes, /token_budget\?: number/);
assert.match(wikiTypes, /graph_hops\?: number/);
assert.match(wikiTypes, /retrieval_mode\?: WikiRetrievalMode/);
assert.match(wikiTypes, /export interface WikiContextResult/);
assert.match(wikiTypes, /budget: WikiContextBudget/);
assert.match(wikiTypes, /retrieval_mode: WikiRetrievalMode \| string/);
assert.match(wikiTypes, /id: number \| string/);

assert.match(wikiApi, /WikiContextOptions/);
assert.match(wikiApi, /WikiContextResult/);
assert.match(
  wikiApi,
  /const buildContext = \(\s*kb_ids: number\[\],\s*query: string,\s*options: WikiContextOptions = {}\s*\): Promise<WikiContextResult> =>/
);
assert.match(wikiApi, /top_k: options\.top_k \?\? 5/);
assert.match(wikiApi, /token_budget: options\.token_budget/);
assert.match(wikiApi, /graph_hops: options\.graph_hops/);
assert.match(wikiApi, /retrieval_mode: options\.retrieval_mode/);

console.log('wiki context options validation passed');
