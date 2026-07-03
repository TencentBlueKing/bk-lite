import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const rootDir = path.resolve(__dirname, '..');
const stateMachinePath = path.join(rootDir, 'packages/webchat-core/src/stateMachine.ts');
const chatPath = path.join(rootDir, 'packages/webchat-ui/src/Chat.tsx');

const source = fs.readFileSync(stateMachinePath, 'utf8');
assert.match(source, /public transitionToChatting\(\): boolean/);
assert.match(source, /idle:\s*\['connecting', 'connected', 'chatting'\]/);
assert.match(source, /connecting:\s*\['connected', 'chatting'\]/);
assert.match(source, /connected:\s*\['chatting'\]/);
assert.match(source, /return path\.every\(\(state\) => this\.transition\(state\)\)/);

const chatSource = fs.readFileSync(chatPath, 'utf8');
assert.match(chatSource, /transitionToChatting\(\)/);
assert.doesNotMatch(chatSource, /transition\(['"]chatting['"]\)/);
