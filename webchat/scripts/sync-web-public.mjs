#!/usr/bin/env node
/**
 * Sync UMD browser bundle into the main web app static assets.
 * Source: packages/webchat-ui/dist/browser/{webchat.js,style.css}
 * Target: ../web/public/webchat/
 */
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const rootDir = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const sourceDir = path.join(rootDir, 'packages/webchat-ui/dist/browser');
const targetDir = path.resolve(rootDir, '../web/public/webchat');

const files = ['webchat.js', 'style.css'];
const staticFiles = [
  {
    source: path.join(rootDir, 'packages/webchat-ui/src/assets/fab-whaledou.webp'),
    name: 'fab-whaledou.webp',
  },
  {
    source: path.join(rootDir, 'packages/webchat-ui/src/assets/fab-whaledou.png'),
    name: 'fab-whaledou.png',
  },
];

for (const file of files) {
  const source = path.join(sourceDir, file);
  if (!fs.existsSync(source)) {
    console.error(`[sync-web-public] missing build artifact: ${source}`);
    console.error('Run `npm run build:browser` first.');
    process.exit(1);
  }
}

fs.mkdirSync(targetDir, { recursive: true });

for (const file of files) {
  const source = path.join(sourceDir, file);
  const target = path.join(targetDir, file);
  fs.copyFileSync(source, target);
  console.log(
    `[sync-web-public] ${path.relative(rootDir, source)} -> ${path.relative(rootDir, target)}`,
  );
}

for (const asset of staticFiles) {
  if (!fs.existsSync(asset.source)) {
    console.error(`[sync-web-public] missing static asset: ${asset.source}`);
    process.exit(1);
  }
  const target = path.join(targetDir, asset.name);
  fs.copyFileSync(asset.source, target);
  console.log(
    `[sync-web-public] ${path.relative(rootDir, asset.source)} -> ${path.relative(rootDir, target)}`,
  );
}
