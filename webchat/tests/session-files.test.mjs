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

const { collectSessionAttachmentFiles, normalizeSafeDownloadUrl, openSafeDownload } = await import(pathToFileURL(outputPath).href);

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
  assert.equal(files[0].createdAt, undefined);
  assert.equal(files[0].source, undefined);
});

test('keeps the user prompt and message time with each generated file', () => {
  const files = collectSessionAttachmentFiles([
    {
      id: 'ask',
      sender: 'user',
      content: '列出主机并导出清单',
      timestamp: 1,
    },
    {
      id: 'answer',
      sender: 'bot',
      timestamp: 1_760_000_000_000,
      metadata: {
        contentChunks: [{
          type: 'toolCalls',
          toolCalls: [{
            id: 'call-2',
            name: 'generate_attachment_file',
            result: JSON.stringify({ filename: '主机清单.xlsx', file_url: fileUrl }),
          }],
        }],
      },
    },
  ]);
  assert.equal(files[0].source, '列出主机并导出清单');
  assert.equal(files[0].createdAt, 1_760_000_000_000);
});

test('omits the bar source when the conversation has no generated files', () => {
  assert.deepEqual(collectSessionAttachmentFiles([{ id: 'hi' }]), []);
});

test('rewrites api v1 downloads onto the proxy allowlist and drops everything else', () => {
  const origin = 'https://console.example';
  const previousWindow = globalThis.window;
  const previousDocument = globalThis.document;
  globalThis.window = { location: { origin } };
  const safe = collectSessionAttachmentFiles([
    {
      metadata: {
        contentChunks: [{
          type: 'toolCalls',
          toolCalls: [
            {
              id: 'proxy',
              name: 'generate_attachment_file',
              result: JSON.stringify({
                filename: 'report.docx',
                file_url: '/api/v1/opspilot/bot_mgmt/workflow_attachment/download/token/',
              }),
            },
            {
              id: 'same',
              name: 'generate_attachment_file',
              result: JSON.stringify({
                filename: 'same.docx',
                file_url: 'https://console.example/files/same.docx',
              }),
            },
            {
              id: 'evil',
              name: 'generate_attachment_file',
              result: JSON.stringify({
                filename: 'evil.docx',
                file_url: 'https://evil.example/api/proxy/opspilot/evil.docx',
              }),
            },
            {
              id: 'script',
              name: 'generate_attachment_file',
              result: JSON.stringify({ filename: 'x.docx', file_url: 'javascript:alert(1)' }),
            },
            {
              id: 'break',
              name: 'generate_attachment_file',
              result: JSON.stringify({ filename: 'y.docx', file_url: '/api/proxy/opspilot/down\nload/' }),
            },
          ],
        }],
      },
    },
  ]);
  assert.deepEqual(safe.map((file) => file.fileUrl), [
    '/api/proxy/opspilot/bot_mgmt/workflow_attachment/download/token/',
    'https://console.example/files/same.docx',
  ]);
  assert.equal(normalizeSafeDownloadUrl('//evil.example/api/proxy/file.docx', origin), '');
  assert.equal(normalizeSafeDownloadUrl('javascript:alert(1)', origin), '');
  assert.equal(normalizeSafeDownloadUrl('/api/proxy/opspilot/../../admin', origin), '');

  const clicks = [];
  globalThis.document = {
    createElement: () => ({
      setAttribute(name, value) {
        this[name] = value;
      },
      click() {
        clicks.push(this.href);
      },
    }),
    body: { appendChild() {}, removeChild() {} },
  };
  try {
    assert.equal(openSafeDownload({ fileUrl: 'javascript:alert(1)', filename: 'x.docx' }, origin), false);
    assert.equal(openSafeDownload({ fileUrl: '/api/v1/opspilot/file.docx', filename: 'file.docx' }, origin), true);
    assert.deepEqual(clicks, ['/api/proxy/opspilot/file.docx']);
  } finally {
    globalThis.window = previousWindow;
    globalThis.document = previousDocument;
  }
});
