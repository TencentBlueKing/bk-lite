#!/usr/bin/env node

import { readFile, writeFile } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const scriptDirectory = path.dirname(fileURLToPath(import.meta.url));
const projectRoot = path.resolve(scriptDirectory, '..');
const manifestPath = path.join(
  projectRoot,
  'src-tauri',
  'gen',
  'android',
  'app',
  'src',
  'main',
  'AndroidManifest.xml',
);

export function applyAdjustResize(manifest) {
  const mainActivityPattern = /<activity\b[^>]*android:name="\.MainActivity"[^>]*>/s;
  const mainActivity = manifest.match(mainActivityPattern)?.[0];

  if (!mainActivity) {
    throw new Error('AndroidManifest.xml 中未找到 .MainActivity');
  }

  let updatedActivity;
  if (/android:windowSoftInputMode="[^"]*"/.test(mainActivity)) {
    updatedActivity = mainActivity.replace(
      /android:windowSoftInputMode="[^"]*"/,
      'android:windowSoftInputMode="adjustResize"',
    );
  } else if (/\n(\s*)android:exported=/.test(mainActivity)) {
    updatedActivity = mainActivity.replace(
      /\n(\s*)android:exported=/,
      '\n$1android:windowSoftInputMode="adjustResize"\n$1android:exported=',
    );
  } else {
    updatedActivity = mainActivity.replace(
      />$/,
      ' android:windowSoftInputMode="adjustResize">',
    );
  }

  return manifest.replace(mainActivity, updatedActivity);
}

export async function patchAndroidManifest(targetPath = manifestPath) {
  const source = await readFile(targetPath, 'utf8');
  const updated = applyAdjustResize(source);

  if (updated !== source) {
    await writeFile(targetPath, updated, 'utf8');
  }
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  await patchAndroidManifest();
}
