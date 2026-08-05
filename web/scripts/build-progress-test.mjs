import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import {
  BUILD_HEARTBEAT_INTERVAL_MS,
  runCommandWithProgress,
} from './build.mjs';

assert.equal(BUILD_HEARTBEAT_INTERVAL_MS, 10_000);

const messages = [];
const result = await runCommandWithProgress(
  process.execPath,
  ['--eval', 'setTimeout(() => {}, 80)'],
  {
    heartbeatIntervalMs: 20,
    log: message => messages.push(message),
    stdio: 'ignore',
  }
);

assert.equal(result.code, 0);
assert.ok(
  messages.length >= 2,
  `a silent command should emit repeated heartbeat messages: ${messages.join('\n')}`
);
assert.match(messages[0], /^⏳ Next\.js 仍在构建，已用时 \d+(?:\.\d+)?s$/);

const failedResult = await runCommandWithProgress(
  process.execPath,
  ['--eval', 'process.exit(7)'],
  { stdio: 'ignore' }
);
assert.equal(failedResult.code, 7);

const buildModuleUrl = new URL('./build.mjs', import.meta.url).href;
const wrapperSource = `
  const { runCommandWithProgress } = await import(${JSON.stringify(buildModuleUrl)});
  const resultPromise = runCommandWithProgress(
    process.execPath,
    ['--eval', 'setInterval(() => {}, 1000)'],
    { stdio: 'ignore' }
  );
  console.log('READY');
  const result = await resultPromise;
  process.exit(result.signal === 'SIGTERM' ? 0 : 9);
`;

const signalResult = await new Promise((resolve, reject) => {
  const wrapper = spawn(
    process.execPath,
    ['--input-type=module', '--eval', wrapperSource],
    { stdio: ['ignore', 'pipe', 'pipe'] }
  );
  let stderr = '';
  let signalSent = false;

  wrapper.stdout.setEncoding('utf8');
  wrapper.stderr.setEncoding('utf8');
  wrapper.stderr.on('data', chunk => {
    stderr += chunk;
  });
  wrapper.stdout.on('data', chunk => {
    if (!signalSent && chunk.includes('READY')) {
      signalSent = true;
      wrapper.kill('SIGTERM');
    }
  });
  wrapper.once('error', reject);
  wrapper.once('close', (code, signal) => {
    resolve({ code, signal, stderr });
  });
});

assert.deepEqual(
  signalResult,
  { code: 0, signal: null, stderr: '' },
  'the wrapper must forward SIGTERM to the build child and wait for it to exit'
);

console.log('build command reports a heartbeat every 10 seconds');
