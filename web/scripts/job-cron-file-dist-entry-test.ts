import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';

const root = process.cwd();
const read = (rel: string) => fs.readFileSync(path.join(root, rel), 'utf8');

const createPage = read('src/app/job/(pages)/execution/cron-task/create/page.tsx');
const editPage = read('src/app/job/(pages)/execution/cron-task/edit/page.tsx');
const zh = JSON.parse(read('src/app/job/locales/zh.json'));
const en = JSON.parse(read('src/app/job/locales/en.json'));
const menu = JSON.parse(read('src/app/job/constants/menu.json'));

function radioTags(source: string): string[] {
  return [...source.matchAll(/<Radio\b[^>]*>/g)].map((match) => match[0]);
}

function hasSavableFileRadio(source: string): boolean {
  return radioTags(source).some(
    (tag) => /value=["']file["']/.test(tag) && !/\bdisabled\b/.test(tag)
  );
}

function extractHandleSubmit(source: string): string {
  const start = source.indexOf('const handleSubmit');
  assert.ok(start >= 0, 'handleSubmit must exist');
  const end = source.indexOf('const handleHostConfirm', start);
  assert.ok(end > start, 'handleSubmit must end before handleHostConfirm');
  return source.slice(start, end);
}

function canSubmitFileJobType(submit: string): boolean {
  if (/job_type:\s*['"]file['"]/.test(submit)) {
    return true;
  }
  const buildsFilePayload = /else if\s*\(\s*jobType\s*===\s*['"]file['"]\s*\)/.test(submit);
  const assignsJobType = /job_type:\s*jobType/.test(submit);
  const rejectsFile =
    /if\s*\(\s*jobType\s*===\s*['"]file['"]\s*\)\s*\{[^}]*return;/.test(submit);
  return (assignsJobType && !rejectsFile) || buildsFilePayload;
}

const zhMenu = menu.zh.find((item: { name: string }) => item.name === 'execution');
const cronMenu = zhMenu?.children?.find((item: { name: string }) => item.name === 'cron_task');
assert.equal(zhMenu?.title, '作业执行');
assert.equal(cronMenu?.title, '定时任务');

assert.equal(zh.job.scriptExecution, '脚本执行');
assert.equal(zh.job.createTask, '新建定时任务');
assert.equal(zh.job.saveAndEnable, '保存并启用');
assert.equal(zh.job.saveOnly, '仅保存');
assert.equal(zh.job.cancel, '取消');
assert.equal(zh.job.fileDistribution, '文件分发');
assert.equal(zh.job.fileDistTitle, '文件分发');
assert.equal(en.job.fileDistribution, 'File Distribution');
assert.equal(en.job.fileDistTitle, 'File Distribution');

assert.match(zh.job.cronFileDistNotSupported, /暂不支持/);
assert.ok(en.job.cronFileDistNotSupported);

for (const [label, source] of [
  ['create', createPage],
  ['edit', editPage],
] as const) {
  assert.equal(
    hasSavableFileRadio(source),
    false,
    `${label} must not expose a savable Radio value=file`
  );
  assert.equal(
    canSubmitFileJobType(extractHandleSubmit(source)),
    false,
    `${label} must not submit job_type=file on the save path`
  );
  assert.match(source, /t\('job\.cronFileDistNotSupported'\)/);
  assert.match(source, /<Radio value="script">\{t\('job\.scriptExecution'\)\}<\/Radio>/);
  assert.match(source, /t\('job\.saveAndEnable'\)/);
  assert.match(source, /t\('job\.saveOnly'\)/);
  assert.match(source, /t\('job\.cancel'\)/);
  assert.doesNotMatch(source, /file_distribution/);
  assert.doesNotMatch(source, /\bfiles\s*:/);
}

assert.match(createPage, /t\('job\.createTask'\)/);

console.log('job-cron-file-dist-entry-test: ok');
