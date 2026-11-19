import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const web = join(dirname(fileURLToPath(import.meta.url)), '../../../..');
const zh = JSON.parse(readFileSync(join(web, 'src/app/workflow/locales/zh.json'), 'utf8'));
const en = JSON.parse(readFileSync(join(web, 'src/app/workflow/locales/en.json'), 'utf8'));
const commonZh = JSON.parse(readFileSync(join(web, 'src/locales/zh.json'), 'utf8')).common;
const commonEn = JSON.parse(readFileSync(join(web, 'src/locales/en.json'), 'utf8')).common;
const editorKeys = [
  'invalidReportTemplateType', 'reportTemplateTooLarge', 'everyDay', 'publishedAndEnabled', 'noMatchingReferences',
];
for (const key of editorKeys) {
  assert.equal(typeof zh.workflowOrchestration.editor[key], 'string', key);
  assert.notEqual(zh.workflowOrchestration.editor[key], en.workflowOrchestration.editor[key], key);
}
for (const key of ['status', 'test', 'details', 'viewAll', 'readOnly', 'submit']) {
  assert.equal(typeof commonZh[key], 'string', key);
  assert.notEqual(commonZh[key], commonEn[key], key);
}
assert.match(zh.workflowOrchestration.editor.publishedAndEnabled, /\{version\}/);
console.log('workflow keys ok');
