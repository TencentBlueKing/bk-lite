import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import test from 'node:test';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { buildSync } from 'esbuild';
import React from 'react';
import { act, create } from 'react-test-renderer';

const rootDir = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const sourcePath = path.join(
  rootDir,
  'packages/webchat-ui/src/components/ToolCallDisplay.tsx'
);
const outputDir = path.join(rootDir, '.test-dist', 'tool-call-display');
fs.mkdirSync(outputDir, { recursive: true });
const outputPath = path.join(outputDir, 'ToolCallDisplay.mjs');

buildSync({
  entryPoints: [sourcePath],
  bundle: true,
  platform: 'node',
  format: 'esm',
  jsx: 'automatic',
  outfile: outputPath,
  external: ['react', 'react/jsx-runtime'],
  loader: { '.css': 'empty' },
});
process.on('exit', () => {
  fs.rmSync(outputDir, { recursive: true, force: true });
});

const { ToolCallDisplay, extractToolCallSummary, formatToolCallJson } = await import(
  pathToFileURL(outputPath)
);

const CMDB_ARGS =
  '{"model_id":"host","query_list":[{"field":"inst_name","value":"fusion-collector-default"}]}';
const EMPTY_RESULT = '{"success":true,"data":{"count":0,"items":[]}}';

test('summarizes CMDB query_list so guessed filters are visible before expand', () => {
  assert.match(extractToolCallSummary(CMDB_ARGS), /fusion-collector-default/);
  assert.match(formatToolCallJson(CMDB_ARGS, { hideEmptyObject: true }), /"model_id": "host"/);
});

test('expanded tool row shows 参数 and 结果', () => {
  let renderer;
  act(() => {
    renderer = create(
      React.createElement(ToolCallDisplay, {
        toolCalls: [
          {
            id: 'tc-1',
            name: 'cmdb_search_instances',
            args: CMDB_ARGS,
            result: EMPTY_RESULT,
            status: 'completed',
          },
        ],
      })
    );
  });

  const tree = renderer.toJSON();
  const serialized = JSON.stringify(tree);
  assert.match(serialized, /已使用/);
  assert.match(serialized, /cmdb_search_instances/);
  assert.match(serialized, /fusion-collector-default/);

  const button = renderer.root.findByType('button');
  assert.equal(button.props['aria-expanded'], false);
  act(() => {
    button.props.onClick();
  });

  assert.equal(renderer.root.findByType('button').props['aria-expanded'], true);
  const expanded = JSON.stringify(renderer.toJSON());
  assert.match(expanded, /参数:/);
  assert.match(expanded, /结果:/);
  const pres = renderer.root.findAllByType('pre');
  assert.match(String(pres[0].props.children), /"model_id": "host"/);
  assert.match(String(pres[1].props.children), /"count": 0/);
});

test('args without result still expand so parameters are inspectable', () => {
  let renderer;
  act(() => {
    renderer = create(
      React.createElement(ToolCallDisplay, {
        toolCalls: [
          {
            id: 'tc-2',
            name: 'cmdb_search_instances',
            args: '{"model_id":"host"}',
            status: 'running',
          },
        ],
      })
    );
  });
  const button = renderer.root.findByType('button');
  assert.equal(button.props.disabled, false);
  act(() => {
    button.props.onClick();
  });
  const expanded = JSON.stringify(renderer.toJSON());
  assert.match(expanded, /参数:/);
  assert.doesNotMatch(expanded, /结果:/);
});
