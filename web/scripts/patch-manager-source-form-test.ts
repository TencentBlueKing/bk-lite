import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

const root = process.cwd();
const read = (path: string) => readFileSync(resolve(root, path), 'utf8');
const settingsPage = read('src/app/patch-manager/(pages)/settings/page.tsx');
const targetPage = read('src/app/patch-manager/(pages)/target/page.tsx');
const types = read('src/app/patch-manager/types/index.ts');

for (const required of [
  "import Password from '@/components/password'",
  "const SAVED_SECRET = '********'",
  'record.has_auth_password ? SAVED_SECRET : undefined',
  'payload.auth_password === SAVED_SECRET',
  "sourceType !== 'wsus'",
  'has_auth_password?: boolean',
]) {
  if (!`${settingsPage}\n${types}`.includes(required)) {
    throw new Error(`补丁源编辑表单缺少约束: ${required}`);
  }
}

if (!settingsPage.includes('<Password') || settingsPage.includes('<Input.Password')) {
  throw new Error('补丁源认证密码必须使用项目 Password 组件');
}

const sourceFooter = settingsPage.match(/footer=\{([\s\S]*?)\}\s*>\s*<Form form=\{form\}/)?.[1] || '';
for (const label of ['取消', '测试连通性', '保存']) {
  if (!sourceFooter.includes(label)) throw new Error(`补丁源弹窗 footer 缺少“${label}”按钮`);
}
if (!(sourceFooter.indexOf('取消') < sourceFooter.indexOf('测试连通性')
  && sourceFooter.indexOf('测试连通性') < sourceFooter.indexOf('保存'))) {
  throw new Error('补丁源弹窗按钮顺序必须是：取消、测试连通性、保存');
}

const targetFooter = targetPage.match(/footer=\{([\s\S]*?)\}\s*>\s*<Form layout="vertical" form=\{form\}/)?.[1] || '';
if (!(targetFooter.indexOf('取消') < targetFooter.indexOf('测试连通性')
  && targetFooter.indexOf('测试连通性') < targetFooter.indexOf("editingTarget ? '保存' : '创建'"))) {
  throw new Error('目标录入抽屉按钮顺序必须是：取消、测试连通性、保存/创建');
}

console.log('补丁源与目标录入表单约束通过');
