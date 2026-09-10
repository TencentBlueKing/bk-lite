import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import path from 'node:path';

import { resolveScheduledTaskConcurrencyPolicy } from '../src/app/job/utils/scheduledTaskPayload';

const root = process.cwd();
const read = (relativePath: string) => readFileSync(path.join(root, relativePath), 'utf8');

const createSource = read('src/app/job/(pages)/execution/cron-task/create/page.tsx');
const editSource = read('src/app/job/(pages)/execution/cron-task/edit/page.tsx');
const zh = JSON.parse(read('src/app/job/locales/zh.json'));
const menu = JSON.parse(read('src/app/job/constants/menu.json'));

const executionMenu = menu.zh.find((item: { name: string }) => item.name === 'execution');
const cronTaskMenu = executionMenu?.children?.find((item: { name: string }) => item.name === 'cron_task');
const createMenu = executionMenu?.children?.find((item: { name: string }) => item.name === 'cron_task_create');
const editMenu = executionMenu?.children?.find((item: { name: string }) => item.name === 'cron_task_edit');

assert.equal(executionMenu?.title, '作业执行');
assert.equal(cronTaskMenu?.title, '定时任务');
assert.equal(createMenu?.title, '创建定时任务');
assert.equal(editMenu?.title, '编辑定时任务');
assert.equal(zh.job.concurrencyStrategy, '并发策略');
assert.equal(zh.job.skipIfRunning, '跳过（上次未完成则跳过本次）');
assert.equal(zh.job.runAnyway, '运行（无论上次是否完成）');
assert.equal(zh.job.queueWait, '排队（等待上次完成后执行）');
assert.equal(zh.job.saveAndEnable, '保存并启用');
assert.equal(zh.job.saveOnly, '仅保存');
assert.equal(zh.job.cancel, '取消');

function buildCreatePayload(concurrencyPolicy: unknown) {
  return {
    name: 'create-task',
    concurrency_policy: resolveScheduledTaskConcurrencyPolicy(concurrencyPolicy),
  };
}

function buildEditPayload(existingPolicy: unknown, nextPolicy: unknown) {
  const current = resolveScheduledTaskConcurrencyPolicy(existingPolicy);
  return {
    name: 'edit-task',
    concurrency_policy: resolveScheduledTaskConcurrencyPolicy(nextPolicy ?? current),
  };
}

const createQueue = buildCreatePayload('queue');
assert.equal(createQueue.concurrency_policy, 'queue');

const createRun = buildCreatePayload('run');
assert.equal(createRun.concurrency_policy, 'run');

const createSkip = buildCreatePayload('skip');
assert.equal(createSkip.concurrency_policy, 'skip');

const createDefault = buildCreatePayload(undefined);
assert.equal(createDefault.concurrency_policy, 'skip');

const editSkipToRun = buildEditPayload('skip', 'run');
assert.equal(editSkipToRun.concurrency_policy, 'run');

const editSkipToQueue = buildEditPayload('skip', 'queue');
assert.equal(editSkipToQueue.concurrency_policy, 'queue');

assert.equal(resolveScheduledTaskConcurrencyPolicy('bogus'), 'skip');
assert.equal(resolveScheduledTaskConcurrencyPolicy(''), 'skip');
assert.equal(resolveScheduledTaskConcurrencyPolicy(null), 'skip');
assert.equal(resolveScheduledTaskConcurrencyPolicy(undefined), 'skip');
assert.equal(resolveScheduledTaskConcurrencyPolicy(1), 'skip');

assert.match(createSource, /from '@\/app\/job\/utils\/scheduledTaskPayload'/);
assert.match(editSource, /from '@\/app\/job\/utils\/scheduledTaskPayload'/);
assert.match(createSource, /resolveScheduledTaskConcurrencyPolicy/);
assert.match(editSource, /resolveScheduledTaskConcurrencyPolicy/);
assert.match(
  createSource,
  /const formData: ScheduledTaskFormData = \{[\s\S]*concurrency_policy:\s*resolveScheduledTaskConcurrencyPolicy\(values\.concurrency_policy\)/,
);
assert.match(
  editSource,
  /const formData: ScheduledTaskFormData = \{[\s\S]*concurrency_policy:\s*resolveScheduledTaskConcurrencyPolicy\(values\.concurrency_policy\)/,
);
assert.match(
  createSource,
  /initialValues=\{\{[\s\S]*concurrency_policy:\s*'skip'/,
);
assert.doesNotMatch(
  createSource,
  /<Form\.Item label=\{t\('job\.concurrencyStrategy'\)\} name="concurrency_policy">\s*<Select defaultValue="skip">/,
);

console.log('job-cron-concurrency-policy-test passed');
