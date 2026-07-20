import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';

const root = process.cwd();
const read = (file: string) => fs.readFileSync(path.join(root, file), 'utf8');

const wikiApi = read('src/app/opspilot/api/wiki.ts');
const assistant = read('src/app/opspilot/components/wiki/WikiQaAssistant.tsx');
const wikiTypes = read('src/app/opspilot/types/wiki.ts');
const zh = JSON.parse(read('src/app/opspilot/locales/zh.json'));
const en = JSON.parse(read('src/app/opspilot/locales/en.json'));

assert.match(wikiTypes, /export interface SaveAnswerPageInput/);
assert.match(wikiTypes, /source_conversation_id: string/);
assert.doesNotMatch(wikiTypes, /as_candidate\?: boolean/);
assert.match(wikiTypes, /page_type: string/);
assert.match(wikiTypes, /tags\?: string\[\]/);

assert.match(wikiApi, /const saveAnswerPage = \(data: SaveAnswerPageInput\): Promise<SaveAnswerPageResult> =>/);
assert.match(wikiApi, /\/page\/save_answer\//);
assert.match(wikiApi, /saveAnswerPage,/);

assert.match(assistant, /SaveOutlined/);
assert.match(assistant, /saveAnswerPage/);
assert.doesNotMatch(assistant, /as_candidate/);
assert.match(assistant, /source_conversation_id/);
assert.match(assistant, /conversationIdRef/);
assert.match(assistant, /name="page_type"/);
assert.match(assistant, /name="tags"/);
assert.match(assistant, /t\('wiki\.saveAnswerToWiki'\)/);
assert.doesNotMatch(assistant, /wiki\.saveAnswerAsCandidate/);
assert.match(assistant, /wiki\.saveAnswerDone/);
assert.doesNotMatch(assistant, /wiki\.saveAnswerCandidateDone/);
assert.equal(zh.wiki.saveAnswerAsCandidate, undefined);
assert.equal(en.wiki.saveAnswerAsCandidate, undefined);
assert.equal(zh.wiki.saveAnswerCandidateDone, undefined);
assert.equal(en.wiki.saveAnswerCandidateDone, undefined);

for (const key of [
  'saveAnswerToWiki',
  'saveAnswerTitle',
  'saveAnswerType',
  'saveAnswerTags',
  'saveAnswerBody',
  'saveAnswerDone',
  'saveAnswerFailed',
]) {
  assert.ok(zh.wiki[key], `missing zh wiki.${key}`);
  assert.ok(en.wiki[key], `missing en wiki.${key}`);
}

console.log('wiki qa save answer validation passed');
