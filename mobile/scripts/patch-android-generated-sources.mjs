#!/usr/bin/env node

import { readFile, writeFile } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const scriptDirectory = path.dirname(fileURLToPath(import.meta.url));
const projectRoot = path.resolve(scriptDirectory, '..');
const generatedSourceDirectory = path.join(
  projectRoot,
  'src-tauri',
  'gen',
  'android',
  'app',
  'src',
  'main',
  'java',
  'org',
  'bklite',
  'mobile',
  'generated',
);

async function updateFile(filePath, updater) {
  const source = await readFile(filePath, 'utf8');
  const updated = updater(source);
  if (updated !== source) {
    await writeFile(filePath, updated, 'utf8');
  }
}

export function patchRustBridge(source) {
  const noArgCreate = '@JvmStatic external fun create()';
  const activityCreate = '@JvmStatic external fun create(activity: WryActivity)';

  if (source.includes(activityCreate)) {
    return source;
  }
  if (!source.includes(noArgCreate)) {
    throw new Error('Rust.kt 中未找到无参 create 声明');
  }

  return source.replace(noArgCreate, activityCreate);
}

export function patchWryActivity(source) {
  let updated = source.replace(
    /\n\s*Rust\.create\(\)\n\s*Rust\.wryCreate\(\)/,
    '',
  );

  const createCall = '        Rust.create(this)\n        Rust.wryCreate()\n';
  if (updated.includes(createCall)) {
    return updated;
  }

  const anchor = /(\n\s*id = savedInstanceState\?\.[^\n]+\n)/;
  if (!anchor.test(updated)) {
    throw new Error('WryActivity.kt 中未找到 Activity id 初始化位置');
  }

  updated = updated.replace(anchor, `$1${createCall}`);
  return updated;
}

export async function patchAndroidGeneratedSources(sourceDirectory = generatedSourceDirectory) {
  await Promise.all([
    updateFile(path.join(sourceDirectory, 'Rust.kt'), patchRustBridge),
    updateFile(path.join(sourceDirectory, 'WryActivity.kt'), patchWryActivity),
  ]);
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  await patchAndroidGeneratedSources();
}
