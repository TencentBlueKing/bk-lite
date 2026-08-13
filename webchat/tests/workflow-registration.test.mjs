import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import test from 'node:test';
import { fileURLToPath } from 'node:url';

const rootDir = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const repositoryRoot = path.resolve(rootDir, '..');
const workflowPath = path.join(repositoryRoot, '.github/workflows/webchat-tests.yml');
const obsoleteWorkflowPath = path.join(rootDir, '.github/workflows/build.yml');

test('WebChat quality gate is registered at repository root for master', () => {
  const workflow = fs.readFileSync(workflowPath, 'utf8');
  const pullRequestBlock = workflow.match(/ {2}pull_request:\n(?<body>(?: {4}.*\n)*)/)?.groups?.body;
  const pushBlock = workflow.match(/ {2}push:\n(?<body>(?: {4}.*\n)*)/)?.groups?.body;

  assert.equal(fs.existsSync(obsoleteWorkflowPath), false);
  assert.ok(pullRequestBlock);
  assert.doesNotMatch(pullRequestBlock, /branches:/);
  assert.ok(pushBlock);
  assert.match(pushBlock, /branches: \[master\]/);
  assert.match(workflow, /node-version: \['18\.18\.0', '20'\]/);
  assert.match(workflow, /working-directory: webchat/);
  assert.match(workflow, /permissions:\n {2}contents: read/);
});

test('pull request quality gate cannot publish packages or receive npm credentials', () => {
  const workflow = fs.readFileSync(workflowPath, 'utf8');
  const publishJob = workflow.match(/  publish:\n(?<body>[\s\S]*)/)?.groups?.body;

  assert.ok(publishJob);
  assert.match(
    publishJob,
    /github\.event_name == 'workflow_dispatch'/
  );
  assert.match(publishJob, /github\.ref == 'refs\/heads\/master'/);
  assert.match(publishJob, /NODE_AUTH_TOKEN: \$\{\{ secrets\.NPM_TOKEN \}\}/);
  assert.doesNotMatch(publishJob, /github\.event_name == 'pull_request'/);
});
