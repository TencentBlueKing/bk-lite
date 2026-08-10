import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';

import {
  combineLocales,
  combineMenus
} from '../src/utils/dynamicsMerged.mjs';

const temporaryRoot = fs.mkdtempSync(
  path.join(os.tmpdir(), 'build-assets-error-')
);
const baseLocalesRoot = path.join(temporaryRoot, 'base-locales');
const communityAppRoot = path.join(temporaryRoot, 'apps');
const appLocalesRoot = path.join(communityAppRoot, 'demo', 'locales');
const appMenuRoot = path.join(communityAppRoot, 'demo', 'constants');
const originalConsoleError = console.error;
let errorLog = '';

try {
  fs.mkdirSync(baseLocalesRoot, { recursive: true });
  fs.mkdirSync(appLocalesRoot, { recursive: true });
  fs.mkdirSync(appMenuRoot, { recursive: true });
  fs.writeFileSync(path.join(baseLocalesRoot, 'en.json'), '{}');
  fs.writeFileSync(path.join(baseLocalesRoot, 'zh.json'), '{}');
  fs.writeFileSync(path.join(appLocalesRoot, 'en.json'), '{broken json');
  fs.writeFileSync(path.join(appMenuRoot, 'menu.json'), '{broken json');

  console.error = (...args) => {
    errorLog += args.map(String).join(' ');
  };

  await assert.rejects(
    combineLocales({
      communityAppRoots: [communityAppRoot],
      enterpriseAppRoot: path.join(temporaryRoot, 'missing-enterprise-apps'),
      baseLocalesRoot,
      destinationRoot: path.join(temporaryRoot, 'public-locales')
    })
  );
  await assert.rejects(
    combineMenus({
      communityAppRoots: [communityAppRoot],
      enterpriseMenusManifestPath: path.join(
        temporaryRoot,
        'missing-enterprise-menus.json'
      ),
      destinationRoot: path.join(temporaryRoot, 'public-menus')
    })
  );
} finally {
  console.error = originalConsoleError;
  fs.rmSync(temporaryRoot, { recursive: true, force: true });
}

assert.match(errorLog, /Error loading locale for demo/);
assert.match(errorLog, /Failed to load menu for demo/);
console.log('locale and menu asset failures stop the build');
