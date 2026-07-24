import { existsSync, readFileSync } from 'node:fs';
import { resolve } from 'node:path';

const root = process.cwd();
const read = (path: string) => readFileSync(resolve(root, path), 'utf8');
const assertAbsent = (content: string, pattern: RegExp, scope: string) => {
  if (pattern.test(content)) throw new Error(`${scope} 仍包含已废弃代码: ${pattern}`);
};

const libraryPage = read('src/app/patch-manager/(pages)/library/page.tsx');
const api = read('src/app/patch-manager/api/index.ts');
const types = read('src/app/patch-manager/types/index.ts');

for (const [scope, content] of [['补丁库页面', libraryPage], ['补丁管理 API', api], ['补丁管理类型', types]] as const) {
  assertAbsent(content, /windows_catalog|CatalogEntry|catalogSearch|catalogIngest/, scope);
}

for (const pattern of [/uploadPatchPackage/, /patch_package/, /\bPatchPackage\b/, /DownloadStatus/]) {
  assertAbsent(`${libraryPage}\n${api}\n${types}`, pattern, '补丁包前端');
}

assertAbsent(`${libraryPage}\n${types}`, /upload_required/, '补丁就绪状态');
assertAbsent(libraryPage, /后台下载任务/, 'WSUS 入库提示');

for (const required of [
  'uploadWindowsPatchPackage',
  'package_info',
  '<Upload.Dragger',
  "accept=\".msu,.cab\"",
  "activeTab === 'win'",
]) {
  if (!`${libraryPage}\n${api}\n${types}`.includes(required)) {
    throw new Error(`Windows 手工补丁包链路缺少: ${required}`);
  }
}

if (!libraryPage.includes("{activeTab === 'win' && (")) {
  throw new Error('新增补丁入口未限制为 Windows，Linux MVP 入口不应显示');
}

if (existsSync(resolve(root, 'src/app/patch-manager/components/catalog-search-modal.tsx'))) {
  throw new Error('Catalog 搜索弹窗组件仍存在');
}

console.log('补丁管理 Linux 元数据与 Windows 手工包前端约束通过');
