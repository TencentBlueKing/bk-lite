#!/usr/bin/env node

import { copyFile, mkdir, readFile, writeFile } from 'node:fs/promises';
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
const backupRulesSourceDirectory = path.join(
  projectRoot,
  'src-tauri',
  'android',
  'app',
  'src',
  'main',
  'res',
  'xml',
);

function setAndroidAttribute(element, name, value) {
  const attributePattern = new RegExp(`${name}="[^"]*"`);
  if (attributePattern.test(element)) {
    return element.replace(attributePattern, `${name}="${value}"`);
  }
  return element.replace(/>$/, ` ${name}="${value}">`);
}

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

export function applyMobilePlatformSettings(manifest) {
  let updated = applyAdjustResize(manifest);

  if (!/android\.permission\.RECORD_AUDIO/.test(updated)) {
    const permission = '    <uses-permission android:name="android.permission.RECORD_AUDIO" />';
    const internetPermissionPattern = /(^\s*<uses-permission\b[^>]*android:name="android\.permission\.INTERNET"[^>]*>)/m;
    if (!internetPermissionPattern.test(updated)) {
      throw new Error('AndroidManifest.xml 中未找到 INTERNET 权限声明');
    }
    updated = updated.replace(internetPermissionPattern, `$1\n${permission}`);
  }

  const applicationPattern = /<application\b[^>]*>/s;
  const application = updated.match(applicationPattern)?.[0];
  if (!application) {
    throw new Error('AndroidManifest.xml 中未找到 application');
  }

  const securedApplication = [
    ['android:allowBackup', 'false'],
    ['android:fullBackupContent', '@xml/backup_rules'],
    ['android:dataExtractionRules', '@xml/data_extraction_rules'],
  ].reduce(
    (element, [name, value]) => setAndroidAttribute(element, name, value),
    application,
  );

  return updated.replace(application, securedApplication);
}

async function installBackupRules(targetManifestPath) {
  const targetDirectory = path.join(path.dirname(targetManifestPath), 'res', 'xml');
  await mkdir(targetDirectory, { recursive: true });
  await Promise.all([
    'backup_rules.xml',
    'data_extraction_rules.xml',
  ].map((fileName) => copyFile(
    path.join(backupRulesSourceDirectory, fileName),
    path.join(targetDirectory, fileName),
  )));
}

export async function patchAndroidManifest(targetPath = manifestPath) {
  const source = await readFile(targetPath, 'utf8');
  const updated = applyMobilePlatformSettings(source);

  if (updated !== source) {
    await writeFile(targetPath, updated, 'utf8');
  }
  await installBackupRules(targetPath);
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  await patchAndroidManifest();
}
