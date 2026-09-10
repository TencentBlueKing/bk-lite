import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import path from 'node:path';
import { pathToFileURL } from 'node:url';

type SseLogStreamModule = typeof import('../src/app/log/(pages)/search/logTerminal/sseLogStream');

function parseChunks(
  parseSseLogChunk: SseLogStreamModule['parseSseLogChunk'],
  createSseLogStreamState: SseLogStreamModule['createSseLogStreamState'],
  chunks: string[],
): string[] {
  const state = createSseLogStreamState();
  return chunks.flatMap((chunk) => parseSseLogChunk(chunk, state));
}

async function main() {
  const terminalSource = readFileSync(
    path.resolve(process.cwd(), 'src/app/log/(pages)/search/logTerminal/index.tsx'),
    'utf8',
  );
  assert.doesNotMatch(
    terminalSource,
    /chunk\.split\(['"]data:['"]\)/,
    '终端源码不得再用 chunk.split("data:") 当事件边界',
  );
  assert.match(
    terminalSource,
    /parseSseLogChunk/,
    '终端源码必须调用 SSE 分帧解析器',
  );
  assert.match(
    terminalSource,
    /const MAX_LOGS_COUNT = 1000/,
    '1000 条保留上限不得改动',
  );
  assert.match(
    terminalSource,
    /\/api\/proxy\/log\/search\/tail/,
    'tail 代理路径不得改动',
  );

  const moduleUrl = pathToFileURL(
    path.resolve(process.cwd(), 'src/app/log/(pages)/search/logTerminal/sseLogStream.ts'),
  );
  const {
    parseSseLogChunk,
    createSseLogStreamState,
    MAX_SSE_LEFTOVER_BYTES,
  } = (await import(moduleUrl.href)) as SseLogStreamModule;

  assert.equal(
    parseChunks(parseSseLogChunk, createSseLogStreamState, [
      'data: {"message":"hello"}\n\n',
    ]).join('\n'),
    'hello',
    '完整普通事件必须输出 1 条',
  );

  assert.deepEqual(
    parseChunks(parseSseLogChunk, createSseLogStreamState, [
      'data: {"message":"metadata: configuration loaded"}\n\n',
    ]),
    ['metadata: configuration loaded'],
    'message 含 metadata: 的完整 JSON 必须输出 1 条，不能按 data: 切开',
  );

  assert.deepEqual(
    parseChunks(parseSseLogChunk, createSseLogStreamState, [
      'data: {"message":"hello',
      ' world"}\n\n',
    ]),
    ['hello world'],
    '同一 JSON 被拆成两块必须拼出 1 条',
  );

  assert.deepEqual(
    parseChunks(parseSseLogChunk, createSseLogStreamState, [
      'data: {"message":"foo data: bar"}\n\n',
    ]),
    ['foo data: bar'],
    '只认行首 data:，正文中的 data: 不得当分帧符',
  );

  assert.deepEqual(
    parseChunks(parseSseLogChunk, createSseLogStreamState, [
      'data: {"message":"a"}\n\ndata: {"_msg":"b"}\n\n',
    ]),
    ['a', 'b'],
    '同一块内多个事件必须全部输出',
  );

  assert.deepEqual(
    parseChunks(parseSseLogChunk, createSseLogStreamState, [
      ':heartbeat\n\ndata: {"message":"ok"}\n\n',
    ]),
    ['ok'],
    '心跳注释必须跳过，后续事件仍要输出',
  );

  const overflowState = createSseLogStreamState();
  parseSseLogChunk(`data: ${'x'.repeat(MAX_SSE_LEFTOVER_BYTES + 8)}`, overflowState);
  assert.ok(
    overflowState.leftover.length <= MAX_SSE_LEFTOVER_BYTES,
    '残片缓存必须有界，禁止无限缓冲',
  );

  console.log('log-terminal-sse-parse-test: GREEN');
}

main().catch((error: unknown) => {
  console.error(error instanceof Error ? error.stack || error.message : error);
  process.exit(1);
});
