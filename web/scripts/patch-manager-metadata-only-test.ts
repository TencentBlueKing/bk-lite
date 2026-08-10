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
  'saveManualWindowsPatch',
  'package_info',
  '<Upload.Dragger',
  "accept=\".msu,.cab\"",
  "activeTab === 'win'",
]) {
  if (!`${libraryPage}\n${api}\n${types}`.includes(required)) {
    throw new Error(`Windows 手工补丁包链路缺少: ${required}`);
  }
}

assertAbsent(libraryPage, /uploadWindowsPatchPackage/, 'Windows 手工补丁页面单请求写入');
for (const required of [
  "body.append('metadata', JSON.stringify(data))",
  "body.append('file', file)",
  'api.saveManualWindowsPatch(patchPayload, file)',
  'api.saveManualWindowsPatch(payload, replacement, editingPatch.id)',
  'const [createSaving, setCreateSaving] = useState(false)',
  'loading={createSaving}',
]) {
  if (!`${libraryPage}\n${api}`.includes(required)) {
    throw new Error(`Windows 手工补丁单请求约束缺少: ${required}`);
  }
}

if (!libraryPage.includes("{activeTab === 'win' && (")) {
  throw new Error('新增补丁入口未限制为 Windows，Linux MVP 入口不应显示');
}

if (existsSync(resolve(root, 'src/app/patch-manager/components/catalog-search-modal.tsx'))) {
  throw new Error('Catalog 搜索弹窗组件仍存在');
}

const candidateColumns = libraryPage.match(
  /const candidateColumns:[\s\S]*?= \[([\s\S]*?)\n\s*\];/,
)?.[1] || '';
if (candidateColumns.includes('批量修改严重级别')) {
  throw new Error('同步入库表头不应显示批量修改严重级别入口');
}

const createDrawer = libraryPage.match(
  /<OperateDrawer\s+title=\{t\('patchManager\.libraryPage\.addPatch'\)\}([\s\S]*?)<OperateDrawer\s+title=\{t\('patchManager\.libraryPage\.syncIngest'\)\}/,
)?.[1] || '';
const windowsFieldOrder = [
  'name="name"',
  'name="package_file"',
  'name="desc"',
  'name="severity"',
  'name="version"',
  'name="arch"',
].map((field) => createDrawer.indexOf(field));
if (windowsFieldOrder.some((index) => index < 0)
  || windowsFieldOrder.some((index, position) => position > 0 && index <= windowsFieldOrder[position - 1])) {
  throw new Error('Windows 新增补丁字段顺序必须是：KB 号、补丁文件、描述、严重级别、适用版本、架构');
}
if (/label=\{t\('patchManager\.libraryPage\.description'\)\} name="desc" rules=/.test(createDrawer)) {
  throw new Error('Windows 新增补丁的描述应为非必填');
}
if (/label=\{t\('patchManager\.libraryPage\.applicableVersion'\)\} name="version" rules=/.test(createDrawer)) {
  throw new Error('Windows 新增补丁的适用版本应为非必填');
}

const editDialog = libraryPage.match(
  /<Modal\s+title=\{t\('patchManager\.libraryPage\.editPatch'\)\}([\s\S]*?)<\/Modal>/,
)?.[1] || '';
const editWindowsFieldOrder = [
  'name="name"',
  'name="package_file"',
  'name="title"',
  'name="severity"',
  'name="version"',
  'name="arch"',
].map((field) => editDialog.indexOf(field));
if (editWindowsFieldOrder.some((index) => index < 0)
  || editWindowsFieldOrder.some((index, position) => position > 0 && index <= editWindowsFieldOrder[position - 1])) {
  throw new Error('Windows 编辑补丁字段顺序必须与新增一致');
}
if (/label=\{t\('patchManager\.libraryPage\.description'\)\} name="title" rules=/.test(editDialog)) {
  throw new Error('Windows 编辑补丁的描述应为非必填');
}

for (const required of [
  'os_type: editingPatch.os_type',
  'team: editingPatch.team',
  'kb_number: values.name',
  'normalizeRepoType(editingPatch.linux_detail?.repo_type)',
  "case 'yum_repo':",
  "case 'dnf_repo':",
  "case 'apt_repo':",
]) {
  if (!libraryPage.includes(required)) {
    throw new Error(`补丁编辑请求缺少: ${required}`);
  }
}

for (const required of [
  'const [editSaving, setEditSaving] = useState(false)',
  'confirmLoading={editSaving}',
  'cancelButtonProps={{ disabled: editSaving }}',
  'setEditSaving(true)',
  'setEditSaving(false)',
]) {
  if (!libraryPage.includes(required)) {
    throw new Error(`Windows 编辑补丁保存 loading 约束缺少: ${required}`);
  }
}

for (const required of [
  'silent = false',
  'coordinator.begin({ visible: !silent })',
  'coordinator.shouldApply(ticket)',
  'coordinator.finish(ticket)',
  'loadData(undefined, undefined, undefined, true)',
]) {
  if (!libraryPage.includes(required)) {
    throw new Error(`补丁状态轮询缺少静默刷新约束: ${required}`);
  }
}

console.log('补丁管理 Linux 元数据与 Windows 手工包前端约束通过');
