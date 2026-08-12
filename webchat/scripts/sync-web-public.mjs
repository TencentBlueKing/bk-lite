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

export function syncWebPublic({ check = false, source = sourceDir, target = targetDir } = {}) {
  for (const file of files) {
    const sourceFile = path.join(source, file);
    if (!fs.existsSync(sourceFile)) {
      throw new Error(`missing build artifact: ${sourceFile}\nRun \`npm run build:browser\` first.`);
    }
  }

  if (!check) {
    fs.mkdirSync(target, { recursive: true });
  }

  for (const file of files) {
    const sourceFile = path.join(source, file);
    const targetFile = path.join(target, file);
    if (check) {
      if (!fs.existsSync(targetFile) || !fs.readFileSync(sourceFile).equals(fs.readFileSync(targetFile))) {
        throw new Error(
          `stale public asset: ${path.relative(path.dirname(rootDir), targetFile)}\n` +
            'Run `npm run build:browser && npm run sync:web`, then commit both browser outputs.'
        );
      }
      console.log(`[sync-web-public] verified ${path.relative(path.dirname(rootDir), targetFile)}`);
      continue;
    }

    fs.copyFileSync(sourceFile, targetFile);
    console.log(
      `[sync-web-public] ${path.relative(rootDir, sourceFile)} -> ${path.relative(rootDir, targetFile)}`
    );
  }
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  try {
    syncWebPublic({ check: process.argv.slice(2).includes('--check') });
  } catch (error) {
    console.error(`[sync-web-public] ${error instanceof Error ? error.message : String(error)}`);
    process.exitCode = 1;
  }
}
