#!/usr/bin/env node
import { spawn } from 'node:child_process';
import { createRequire } from 'node:module';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { prepareBuildAssets } from './prepare-build-assets.mjs';

const require = createRequire(import.meta.url);
const nextCliPath = require.resolve('next/dist/bin/next');
export const BUILD_HEARTBEAT_INTERVAL_MS = 10_000;

const formatDuration = (milliseconds) => {
  if (milliseconds < 60_000) {
    return `${(milliseconds / 1000).toFixed(1)}s`;
  }

  const totalSeconds = Math.floor(milliseconds / 1000);
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${minutes}m ${seconds}s`;
};

export const runCommandWithProgress = (
  command,
  args,
  {
    heartbeatIntervalMs = BUILD_HEARTBEAT_INTERVAL_MS,
    log = console.log,
    stdio = 'inherit',
  } = {}
) => new Promise((resolve, reject) => {
  const startedAt = Date.now();
  const child = spawn(command, args, {
    cwd: process.cwd(),
    env: process.env,
    stdio,
  });
  const heartbeat = setInterval(() => {
    log(`⏳ Next.js 仍在构建，已用时 ${formatDuration(Date.now() - startedAt)}`);
  }, heartbeatIntervalMs);
  heartbeat.unref();

  const forwardSigint = () => child.kill('SIGINT');
  const forwardSigterm = () => child.kill('SIGTERM');
  process.once('SIGINT', forwardSigint);
  process.once('SIGTERM', forwardSigterm);

  const cleanup = () => {
    clearInterval(heartbeat);
    process.off('SIGINT', forwardSigint);
    process.off('SIGTERM', forwardSigterm);
  };

  child.once('error', (error) => {
    cleanup();
    reject(error);
  });
  child.once('close', (code, signal) => {
    cleanup();
    resolve({
      code,
      signal,
      durationMs: Date.now() - startedAt,
    });
  });
});

export async function runBuild(args = process.argv.slice(2)) {
  const analyze = args.includes('--analyze');
  const nextArgs = args.filter(arg => arg !== '--analyze');
  const prepareStartedAt = Date.now();
  console.log('🚧 [1/2] 正在准备构建资源...');
  await prepareBuildAssets();
  console.log(`✅ [1/2] 构建资源准备完成（${formatDuration(Date.now() - prepareStartedAt)}）`);

  const buildStartedAt = Date.now();
  console.log('🏗️ [2/2] 正在执行 Next.js 生产构建...');
  const previousAnalyze = process.env.ANALYZE;
  if (analyze) {
    process.env.ANALYZE = 'true';
  }

  let result;
  try {
    result = await runCommandWithProgress(
      process.execPath,
      [nextCliPath, 'build', ...nextArgs]
    );
  } finally {
    if (analyze) {
      if (previousAnalyze === undefined) {
        delete process.env.ANALYZE;
      } else {
        process.env.ANALYZE = previousAnalyze;
      }
    }
  }

  if (result.code === 0) {
    console.log(`✅ Next.js 构建完成，总用时 ${formatDuration(Date.now() - buildStartedAt)}`);
  }

  return result;
}

const currentFile = fileURLToPath(import.meta.url);
const isMain = process.argv[1] && path.resolve(process.argv[1]) === currentFile;

if (isMain) {
  runBuild().then(({ code, signal }) => {
    if (signal) {
      process.kill(process.pid, signal);
      return;
    }
    process.exitCode = code ?? 1;
  }).catch((error) => {
    console.error('❌ Web 构建启动失败:', error);
    process.exitCode = 1;
  });
}
