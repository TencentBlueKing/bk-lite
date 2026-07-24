import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';

const pagePath = path.resolve(import.meta.dirname, '../src/app/system-manager/(pages)/integration-center/detail/page.tsx');
const page = fs.readFileSync(pagePath, 'utf8');

assert.match(page, /import \{ Alert, Badge,/);
assert.match(page, /const \[lastTestResult, setLastTestResult\]/);
assert.match(page, /getIntegrationBaseCapabilityStatusItems/);
assert.match(page, /system\.integrationCenter\.capabilityStatus/);
assert.doesNotMatch(page, /verifiedCapabilityCount/);
assert.match(page, /item\.enableValue\} · \{item\.value/);
assert.match(page, /<Badge\s+status=\{item\.tone === 'success' \? 'success' : item\.tone === 'error' \? 'error' : 'default'\}/s);
assert.match(page, /text=\{<span className="whitespace-nowrap text-\[14px\] text-\[var\(--color-text\)\]">\{item\.enableValue\} · \{item\.value\}<\/span>\}/);
assert.doesNotMatch(page, /max-w-\[65%\]/);
assert.match(page, /capabilityStatusItems\.length > 0 \? \(\s*<div className="mt-5 border-t border-\[var\(--color-border\)\] pt-4">/s);
assert.match(page, /<div className="mb-2 text-sm font-medium text-\[var\(--color-text\)\]">\s*\{t\('system\.integrationCenter\.capabilityStatus'\)\}/s);
assert.match(page, /capabilityStatusItems\.map\(\(item\) => \(\s*<div\s+key=\{item\.label\}\s+className="rounded-md border border-\[var\(--color-border\)\] bg-\[var\(--color-bg\)\] px-3 py-2"/s);
assert.match(page, /const testDisabled = activeTab !== 'base' && instance\.status !== 'ready';/);
assert.match(page, /const testSucceeded = result\.data\.success;/);
assert.match(page, /setLastTestResult\(\{ \.\.\.result, result: testSucceeded \}\);/);
assert.match(page, /okText: t\('system\.integrationCenter\.saveAndTest'\)/);
assert.match(page, /onOk: async \(\) => \{\s*setTesting\(true\);\s*message\.loading\(/s);
assert.match(page, /const saved = await saveConfig\(\{ showSuccess: false, refresh: false \}\);\s*if \(saved\) \{\s*await runTestRequest\(\{ savedBeforeTest: true, isPipeline: true \}\);\s*\} else \{\s*message\.destroy\(saveAndTestMessageKey\);\s*setTesting\(false\);\s*\}/s);
assert.match(page, /const saved = await saveConfig\(\{ showSuccess: false, refresh: false \}\);/);
assert.match(page, /if \(refresh\) \{\s*await fetchDetailData\(\);\s*\}/s);
assert.match(page, /message\.loading\(\{\s*key: saveAndTestMessageKey,\s*content: t\('system\.integrationCenter\.savingAndTesting'\),\s*duration: 0,\s*\}\);/s);
assert.match(page, /message\.destroy\(saveAndTestMessageKey\);/);
assert.match(
  page,
  /const successMessage = savedBeforeTest\s*\? t\('system\.integrationCenter\.saveAndTestSuccess'\)\s*:\s*t\('system\.integrationCenter\.testSuccess'\);/s,
);
assert.match(page, /showSuccess = true/);
assert.match(page, /if \(showSuccess\) \{\s*message\.success\(t\('common\.saveSuccess'\)\);\s*\}/s);
assert.match(page, /lastTestResult && !lastTestResult\.result/);
assert.match(page, /system\.integrationCenter\.errorSummary/);
assert.match(page, /diagnostic\?\.message/);
assert.match(page, /const diagnosticDetail = diagnostic\?\.detail \|\| diagnostic\?\.message \|\| '';/);
assert.match(page, /backgroundColor: 'color-mix\(in srgb, var\(--color-fail\) 6%, var\(--color-bg\)\)'/);
assert.doesNotMatch(page, /type="error"/);
assert.match(page, /className="break-words"/);
assert.match(page, /system\.integrationCenter\.testRequest/);

console.log('integration center test request UI tests passed');
