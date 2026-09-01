import fs from 'node:fs';
import path from 'node:path';
import assert from 'node:assert/strict';
import { fileURLToPath } from 'node:url';

/**
 * 接线回归：模型管理弹窗可维护应用拓扑层级，拓扑按节点字段落带。
 */
const webRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const modalPath = path.join(
  webRoot,
  'src/app/cmdb/(pages)/assetManage/management/list/modelModal.tsx'
);
const overviewPath = path.join(
  webRoot,
  'src/app/cmdb/(pages)/assetData/detail/relationships/applicationResourceOverview/index.tsx'
);
const resolveLayerPath = path.join(
  webRoot,
  'src/app/cmdb/(pages)/assetData/detail/relationships/applicationResourceOverview/resolveLayer.ts'
);
const zhPath = path.join(webRoot, 'src/app/cmdb/locales/zh.json');
const enPath = path.join(webRoot, 'src/app/cmdb/locales/en.json');

const modalSrc = fs.readFileSync(modalPath, 'utf8');
const overviewSrc = fs.readFileSync(overviewPath, 'utf8');
const resolveLayerSrc = fs.readFileSync(resolveLayerPath, 'utf8');
const zh = JSON.parse(fs.readFileSync(zhPath, 'utf8'));
const en = JSON.parse(fs.readFileSync(enPath, 'utf8'));

const failures: string[] = [];

if (!/name="app_topo_layer"/.test(modalSrc)) {
  failures.push('[modelModal.tsx] 缺少 Form.Item name="app_topo_layer"');
}
if (!/<Radio\.Group/.test(modalSrc)) {
  failures.push('[modelModal.tsx] 应用拓扑层级必须是 Radio.Group 单选');
}
for (const value of ['system', 'service', 'host', 'appService', 'infrastructure', 'none']) {
  if (!new RegExp(`<Radio\\s+value="${value}"`).test(modalSrc)) {
    failures.push(`[modelModal.tsx] 缺少 Radio value="${value}"`);
  }
}
if (/<Radio\s+value="root"/.test(modalSrc)) {
  failures.push('[modelModal.tsx] 不应提供系统层 root 选项');
}
if (!/app_topo_layer:\s*params\.app_topo_layer/.test(modalSrc)) {
  failures.push('[modelModal.tsx] 编辑 payload 未提交 app_topo_layer');
}
if (!/type === 'add'[\s\S]{0,80}app_topo_layer = 'none'/.test(modalSrc)) {
  failures.push('[modelModal.tsx] 新建缺省未落到 none');
}

const layoutPath = path.join(
  webRoot,
  'src/app/cmdb/(pages)/assetManage/management/detail/layout.tsx'
);
const layoutSrc = fs.readFileSync(layoutPath, 'utf8');
if (!/shoModelModal\(\s*'edit'[\s\S]{0,500}app_topo_layer:\s*modelDetail\.app_topo_layer/.test(layoutSrc)) {
  failures.push('[detail/layout.tsx] 编辑弹窗未回填 modelDetail.app_topo_layer');
}
if (!/shoModelModal\(\s*'edit'[\s\S]{0,500}is_pre:\s*modelDetail\.is_pre/.test(layoutSrc)) {
  failures.push('[detail/layout.tsx] 编辑弹窗未传入 is_pre');
}
if (!/EditTwoTone[\s\S]{0,1200}\{\s*!isPre && \(/.test(layoutSrc)) {
  failures.push('[detail/layout.tsx] 有编辑权限时应显示内置模型编辑入口');
}
if (/\{\s*!isPre && \([\s\S]{0,400}EditTwoTone/.test(layoutSrc)) {
  failures.push('[detail/layout.tsx] 内置模型编辑入口仍被 is_pre 挡住');
}
if (!/\{\s*!isPre && \([\s\S]{0,400}DeleteTwoTone/.test(layoutSrc)) {
  failures.push('[detail/layout.tsx] 内置模型删除入口必须仍被挡住');
}

if (!/\? \{ app_topo_layer: params\.app_topo_layer \}/.test(modalSrc)) {
  failures.push('[modelModal.tsx] 内置模型更新必须只提交 app_topo_layer');
}
if (!/disabled=\{type === 'edit' && isBuiltinEdit\(\)\}/.test(modalSrc)) {
  failures.push('[modelModal.tsx] 内置模型名称/组织必须只读');
}

if (!/from '\.\/resolveLayer'/.test(overviewSrc)) {
  failures.push('[index.tsx] 未从 resolveLayer 接入落带');
}
if (!/if \(node\.id === rootNode\.id\) return 'root'/.test(resolveLayerSrc)) {
  failures.push('[resolveLayer.ts] 中心节点必须固定系统带');
}
if (!/node\.app_topo_layer === 'system'/.test(resolveLayerSrc)) {
  failures.push('[resolveLayer.ts] 系统层模型必须落入系统带');
}
if (!/node\.app_topo_layer === 'none'/.test(resolveLayerSrc)) {
  failures.push('[resolveLayer.ts] 不分类节点不得落入五条展示带');
}
if (!/if \(!layer\) return/.test(overviewSrc)) {
  failures.push('[index.tsx] 不分类节点必须从分层画布排除');
}

const requiredKeys = [
  'appTopoLayer',
  'appTopoLayerSystem',
  'appTopoLayerService',
  'appTopoLayerHost',
  'appTopoLayerAppService',
  'appTopoLayerInfrastructure',
  'appTopoLayerNone',
] as const;
for (const key of requiredKeys) {
  if (!zh.Model?.[key] || !en.Model?.[key]) {
    failures.push(`[locales] 缺少 Model.${key}`);
  }
}
if (zh.Model?.appTopoLayerSystem !== '系统层') {
  failures.push('[zh.json] Model.appTopoLayerSystem 应为「系统层」');
}
if (zh.Model?.appTopoLayerService !== '服务层') {
  failures.push('[zh.json] Model.appTopoLayerService 应为「服务层」');
}
if (zh.Model?.appTopoLayerNone !== '不分类') {
  failures.push('[zh.json] Model.appTopoLayerNone 应为「不分类」');
}
if (zh.Model?.appTopoLayerInfrastructure !== '基础设施层') {
  failures.push('[zh.json] Model.appTopoLayerInfrastructure 应为「基础设施层」');
}

assert.equal(
  failures.length,
  0,
  '\n应用拓扑模型层级接线失败:\n  - ' + failures.join('\n  - ')
);

console.log('cmdb-app-topo-model-layer-wiring test passed');
