import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import test from 'node:test';
import { fileURLToPath, pathToFileURL } from 'node:url';
import ts from 'typescript';

const rootDir = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const sourcePath = path.join(rootDir, 'packages/webchat-ui/src/sessionFiles.ts');
const outputDir = fs.mkdtempSync(path.join(os.tmpdir(), 'webchat-session-files-'));
const outputPath = path.join(outputDir, 'sessionFiles.mjs');
const compiled = ts.transpileModule(fs.readFileSync(sourcePath, 'utf8'), {
  compilerOptions: { module: ts.ModuleKind.ES2020, target: ts.ScriptTarget.ES2020 },
  fileName: sourcePath,
});
fs.writeFileSync(outputPath, compiled.outputText);
process.on('exit', () => fs.rmSync(outputDir, { recursive: true, force: true }));

const { collectSessionAttachmentFiles } = await import(pathToFileURL(outputPath).href);

const fileUrl = '/api/proxy/opspilot/bot_mgmt/workflow_attachment/download/token/';

test('collects attachment files from the current conversation, including history chunks', () => {
  const files = collectSessionAttachmentFiles([
    { id: 'hi', metadata: { contentChunks: [{ type: 'text', content: '你好' }] } },
    {
      id: 'old',
      metadata: {
        contentChunks: [
          {
            type: 'toolCalls',
            toolCalls: [
              {
                id: 'call-1',
                name: 'generate_attachment_file',
                result: JSON.stringify({ filename: '子网地址使用率.xlsx', file_url: fileUrl }),
              },
            ],
          },
        ],
      },
    },
  ]);
  assert.equal(files.length, 1);
  assert.equal(files[0].filename, '子网地址使用率.xlsx');
  assert.equal(files[0].fileUrl, fileUrl);
  assert.equal(files[0].ext, 'xlsx');
});

test('omits the bar source when the conversation has no generated files', () => {
  assert.deepEqual(collectSessionAttachmentFiles([{ id: 'hi' }]), []);
});
