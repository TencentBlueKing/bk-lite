import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

const sourcePath = resolve(
  process.cwd(),
  'src/app/opspilot/components/chatflow/components/nodeConfigs/WebChatNodeConfig.tsx'
);
const source = readFileSync(sourcePath, 'utf8');

const assertions: Array<[boolean, string]> = [
  [
    /<a[\s\S]*href=\{webAccessUrl\}[\s\S]*>\s*\{webAccessUrl\}\s*<\/a>/.test(source),
    '访问地址应由 URL 文本自身渲染为可点击链接',
  ],
  [
    !source.includes('window.open(webAccessUrl'),
    '不应保留独立的 window.open 打开按钮',
  ],
  [
    !source.includes('ExportOutlined'),
    '不应保留独立打开图标',
  ],
];

const failed = assertions.filter(([passed]) => !passed).map(([, message]) => message);

if (failed.length > 0) {
  throw new Error(failed.join('\n'));
}
