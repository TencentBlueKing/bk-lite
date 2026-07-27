import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

const page = readFileSync(
  resolve(process.cwd(), 'src/app/patch-manager/(pages)/risk-pending/page.tsx'),
  'utf8',
);

if (!/className="install-impact-summary"/.test(page)) {
  throw new Error('预计连带变更摘要缺少固定的省略样式入口');
}

if (!/maxWidth:\s*'100%'/.test(page) || !/textOverflow:\s*'ellipsis'/.test(page)) {
  throw new Error('预计连带变更摘要没有限制宽度并显示省略号');
}

if (!/const InstallImpactColumnTitle/.test(page)
  || !/borderBottom:\s*'1px dashed currentColor'/.test(page)
  || !/tabIndex=\{0\}/.test(page)) {
  throw new Error('预计连带变更表头缺少可聚焦的虚线 Tooltip 触发区');
}

if (/message="预计连带变更来自 Linux 包管理器 dry-run"/.test(page)) {
  throw new Error('治理抽屉仍显示预计连带变更的大块 Alert');
}

console.log('预计连带变更长文本省略约束通过');
