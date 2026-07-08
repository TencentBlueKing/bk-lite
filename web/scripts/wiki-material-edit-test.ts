import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';

const root = process.cwd();
const read = (file: string) => fs.readFileSync(path.join(root, file), 'utf8');

const materialTab = read('src/app/opspilot/components/wiki/MaterialTab.tsx');
const wikiApi = read('src/app/opspilot/api/wiki.ts');
const zh = JSON.parse(read('src/app/opspilot/locales/zh.json'));
const en = JSON.parse(read('src/app/opspilot/locales/en.json'));

// API 层必须提供资料更新端点
assert.match(wikiApi, /const updateMaterial\s*=\s*\(id:\s*number,\s*data:\s*Partial<Material>\):\s*Promise<Material>\s*=>\s*put\(`\$\{BASE\}\/material\/\$\{id\}\/`,\s*data\)/);
assert.match(wikiApi, /updateMaterial,/);

// MaterialTab:提供编辑状态与编辑入口,列表按钮只展示“编辑”
assert.match(materialTab, /const \[editingMaterial,\s*setEditingMaterial\]/);
assert.match(materialTab, /const isEditing = Boolean\(editingMaterial\)/);
assert.match(materialTab, /const openEdit = \(record: Material\) =>/);
assert.match(materialTab, /onClick=\{\(\) => openEdit\(record\)\}/);
assert.match(materialTab, /\{t\('common\.edit'\)\}/);
assert.match(materialTab, /title=\{isEditing \? t\('wiki\.editMaterial'\) : t\('wiki\.addMaterial'\)\}/);

// 编辑弹窗不能点遮罩误关闭,类型不可改;文件类基础信息也要回填只读展示
assert.match(materialTab, /maskClosable=\{false\}/);
assert.match(materialTab, /disabled=\{isEditing\}/);
assert.match(materialTab, /\{\(type !== 'file' \|\| isEditing\) && \(/);
assert.match(materialTab, /<Input disabled=\{isEditing && type === 'file'\} \/>/);

// 文件编辑只保留图片增强,不展示上传区
assert.match(materialTab, /type === 'file' && !isEditing/);
assert.match(materialTab, /\(!isEditing \|\| type === 'file'\)/);

// 网页编辑允许名称和同步策略,但 URL 只读且更新 payload 不携带 url
assert.match(materialTab, /name="url"/);
assert.match(materialTab, /disabled=\{isEditing\}/);
assert.match(materialTab, /editingMaterial\.material_type === 'web'/);
assert.match(materialTab, /sync_policy: \{ enabled: !!values\.sync_enabled, interval_hours: values\.sync_interval_hours \?\? 24 \}/);
assert.doesNotMatch(materialTab, /editingMaterial\.material_type === 'web'[\s\S]{0,500}url:/);

// 文本编辑允许正文,保存后由后端标记待更新
assert.match(materialTab, /editingMaterial\.material_type === 'text'/);
assert.match(materialTab, /text_content: values\.text_content \?\? ''/);

// 详情 AI 解读按 Markdown 渲染,避免以纯文本方式展示 md 内容
assert.match(materialTab, /import MarkdownRenderer from '@\/components\/markdown'/);
assert.match(materialTab, /<MarkdownRenderer content=\{detail\.ai_summary\} \/>/);
assert.doesNotMatch(materialTab, /<span className="whitespace-pre-wrap text-xs">\{detail\.ai_summary \|\| '--'\}<\/span>/);

// 详情抽屉需要比默认 600px 更宽,并在窄屏时自动收敛
assert.match(materialTab, /width="min\(960px, calc\(100vw - 48px\)\)"/);
assert.match(materialTab, /labelStyle=\{\{ width: 144, whiteSpace: 'nowrap' \}\}/);
assert.match(materialTab, /contentStyle=\{\{ minWidth: 0 \}\}/);

for (const key of ['editMaterial']) {
  assert.ok(zh.wiki[key], `missing zh wiki.${key}`);
  assert.ok(en.wiki[key], `missing en wiki.${key}`);
}

console.log('wiki material edit validation passed');
