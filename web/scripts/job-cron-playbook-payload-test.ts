import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import path from 'node:path';

import {
  buildScheduledTaskTemplatePayload,
  restoreScheduledTaskTemplateUi,
} from '../src/app/job/utils/scheduledTaskPayload';

const root = process.cwd();
const read = (relativePath: string) => readFileSync(path.join(root, relativePath), 'utf8');

const createSource = read('src/app/job/(pages)/execution/cron-task/create/page.tsx');
const editSource = read('src/app/job/(pages)/execution/cron-task/edit/page.tsx');
const zh = JSON.parse(read('src/app/job/locales/zh.json'));
const menu = JSON.parse(read('src/app/job/constants/menu.json'));

const executionMenu = menu.zh.find((item: { name: string }) => item.name === 'execution');
const cronTaskMenu = executionMenu?.children?.find((item: { name: string }) => item.name === 'cron_task');

assert.equal(executionMenu?.title, '作业执行');
assert.equal(cronTaskMenu?.title, '定时任务');
assert.equal(zh.job.editTask, '编辑定时任务');
assert.equal(zh.job.jobType, '作业类型');
assert.equal(zh.job.scriptExecution, '脚本执行');
assert.equal(zh.job.selectTemplate, '选择模版');
assert.equal(zh.job.scriptLibrary, '脚本库');
assert.equal(zh.job.playbook, 'Playbook');
assert.equal(zh.job.saveAndEnable, '保存并启用');
assert.equal(zh.job.saveOnly, '仅保存');
assert.equal(zh.job.cancel, '取消');

const switchToPlaybook = buildScheduledTaskTemplatePayload({
  jobType: 'script',
  templateType: 'playbook',
  script: 11,
  playbook: 22,
});
assert.deepEqual(switchToPlaybook, {
  job_type: 'playbook',
  script: null,
  playbook: 22,
});
assert.equal(JSON.parse(JSON.stringify(switchToPlaybook)).script, null);

const switchBackToScript = buildScheduledTaskTemplatePayload({
  jobType: 'script',
  templateType: 'script',
  script: 11,
  playbook: 22,
});
assert.deepEqual(switchBackToScript, {
  job_type: 'script',
  script: 11,
  playbook: null,
});
assert.equal(JSON.parse(JSON.stringify(switchBackToScript)).playbook, null);

const createPlaybook = buildScheduledTaskTemplatePayload({
  jobType: 'script',
  templateType: 'playbook',
  playbook: 33,
});
assert.deepEqual(createPlaybook, {
  job_type: 'playbook',
  script: null,
  playbook: 33,
});

const restoredPlaybook = restoreScheduledTaskTemplateUi({
  job_type: 'playbook',
  script: 11,
  playbook: 22,
});
assert.deepEqual(restoredPlaybook, {
  jobType: 'script',
  templateType: 'playbook',
});

const dirtyScriptWithPlaybook = restoreScheduledTaskTemplateUi({
  job_type: 'script',
  script: 11,
  playbook: 22,
});
assert.deepEqual(dirtyScriptWithPlaybook, {
  jobType: 'script',
  templateType: 'script',
});

assert.match(createSource, /from '@\/app\/job\/utils\/scheduledTaskPayload'/);
assert.match(editSource, /from '@\/app\/job\/utils\/scheduledTaskPayload'/);
assert.match(createSource, /buildScheduledTaskTemplatePayload\(/);
assert.match(editSource, /buildScheduledTaskTemplatePayload\(/);
assert.match(editSource, /restoreScheduledTaskTemplateUi\(/);
assert.match(editSource, /<Radio value="script">\{t\('job\.scriptExecution'\)\}<\/Radio>/);
assert.doesNotMatch(
  editSource,
  /task\.job_type === 'script'[\s\S]{0,180}task[\s\S]{0,40}\.playbook/,
);

console.log('job-cron-playbook-payload-test passed');
