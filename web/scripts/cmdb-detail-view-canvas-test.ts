import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { startAlignTranslateX } from '../src/app/cmdb/components/networkTopology/x6FitView';
import {
  CANVAS_PAD_X,
  LAYOUT_NODE,
  LAYER_LABEL_RAIL_PX,
  ORIGIN_X,
} from '../src/app/cmdb/(pages)/assetData/detail/relationships/applicationResourceOverview/layerLayout';

/**
 * 详情页与视图工作台共用画布。详情侧栏会变窄，不能再用 100vw 估宽，
 * 也不能让 zoomToFit 居中把节点从层标签上拉开。
 */

const webRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const read = (rel: string) => fs.readFileSync(path.join(webRoot, rel), 'utf8');

const failures: string[] = [];

const layoutScss = read('src/app/cmdb/(pages)/assetData/detail/layout.module.scss');
if (/section[\s\S]{0,120}100vw/.test(layoutScss)) {
  failures.push('[layout.module.scss] 详情内容区不能用 100vw 估宽，会比侧栏后的真实槽更宽并截断');
}
if (!/min-width:\s*0/.test(layoutScss)) {
  failures.push('[layout.module.scss] 详情内容区需要 min-width: 0 才能在 flex 里收缩');
}

const subLayout = read('src/app/cmdb/(pages)/assetData/components/sub-layout/index.tsx');
if (!/<section[^>]*min-w-0/.test(subLayout)) {
  failures.push('[sub-layout] 内容 section 需要 min-w-0，避免 flex 子项撑破侧栏后的槽');
}

const pageSrc = read('src/app/cmdb/(pages)/assetData/detail/relationships/page.tsx');
if (!/<ApplicationResourceOverview[\s\S]*?fillContainer/.test(pageSrc)) {
  failures.push('[relationships/page.tsx] 应用拓扑在详情里也要 fillContainer');
}
if (!/<NetworkTopo[\s\S]*?fillContainer/.test(pageSrc)) {
  failures.push('[relationships/page.tsx] 网络拓扑在详情里也要 fillContainer');
}
if (!/styles\.pageFill|pageFill/.test(pageSrc)) {
  failures.push('[relationships/page.tsx] 画布类 Tab 需要撑满剩余高度');
}
if (!/activeTab === 'ipam'[\s\S]{0,180}scrollCanvas/.test(pageSrc)) {
  failures.push('[relationships/page.tsx] IP 视图需要在剩余高度内滚动，而不是被外层裁切');
}
if (!/activeTab === 'rackView'[\s\S]{0,220}scrollCanvas/.test(pageSrc)) {
  failures.push('[relationships/page.tsx] 机柜视图需要在剩余高度内滚动');
}
if (!/activeTab === 'roomView'[\s\S]{0,220}scrollCanvas/.test(pageSrc)) {
  failures.push('[relationships/page.tsx] 机房视图需要在剩余高度内滚动');
}

if (!/headerCanvas/.test(pageSrc)) {
  failures.push('[relationships/page.tsx] 画布类 Tab 不能沿用列表的粘性遮罩，否则会切掉工具条按钮');
}

const relScss = read('src/app/cmdb/(pages)/assetData/detail/relationships/index.module.scss');
if (!/\.header\.headerCanvas::after[\s\S]{0,80}display:\s*none/.test(relScss)) {
  failures.push('[relationships/index.module.scss] 画布 Tab 必须用更高优先级关掉列表底部遮罩，否则仍会切掉「拓扑图」按钮');
}
if (!/\.canvasBody[\s\S]{0,80}padding-top:/.test(relScss)) {
  failures.push('[relationships/index.module.scss] .canvasBody 需要与 Tab 留出间距，避免切到「拓扑图」按钮');
}
if (!/\.pageFill[\s\S]{0,80}height:\s*100%/.test(relScss)) {
  failures.push('[relationships/index.module.scss] .pageFill 必须吃满详情内容区高度');
}
if (!/\.canvasBody[\s\S]{0,120}min-width:\s*0/.test(relScss)) {
  failures.push('[relationships/index.module.scss] .canvasBody 需要 min-width: 0');
}

const overviewSrc = read(
  'src/app/cmdb/(pages)/assetData/detail/relationships/applicationResourceOverview/index.tsx'
);
if (!/align:\s*'start'/.test(overviewSrc)) {
  failures.push('[applicationResourceOverview] 应用拓扑 fitView 必须左对齐，层标签才跟得上节点');
}
if (!/LAYER_LABEL_RAIL_PX/.test(overviewSrc)) {
  failures.push('[applicationResourceOverview] 车道宽度应按层标签轨宽从容器扣减');
}

const overviewScss = read(
  'src/app/cmdb/(pages)/assetData/detail/relationships/applicationResourceOverview/index.module.scss'
);
if (!/\.overviewFill[\s\S]{0,80}min-width:\s*0/.test(overviewScss)) {
  failures.push('[applicationResourceOverview scss] fill 模式不能再锁 640px min-width');
}

const hostSrc = read('src/app/cmdb/(pages)/views/components/ViewCanvasHost.tsx');
if (!/viewType === 'application'[\s\S]{0,280}fillContainer/.test(hostSrc)) {
  failures.push('[ViewCanvasHost] 应用拓扑在工作台应 fillContainer');
}

const ipPage = read('src/app/cmdb/(pages)/assetData/detail/ipView/page.tsx');
if (!/h-full min-h-0 min-w-0 overflow-auto/.test(ipPage)) {
  failures.push('[ipView/page.tsx] 独立 IP 视图页也要按剩余高度滚动');
}

assert.equal(ORIGIN_X - LAYOUT_NODE.width / 2, CANVAS_PAD_X);
assert.equal(LAYER_LABEL_RAIL_PX, 132);

assert.equal(
  startAlignTranslateX({ contentX: 24, scale: 1, translateX: 180, padding: 48 }),
  48 - 24
);
assert.equal(
  startAlignTranslateX({ contentX: 0, scale: 0.5, translateX: 200, padding: 48 }),
  48
);

assert.equal(failures.length, 0, failures.join('\n'));
console.log('cmdb-detail-view-canvas test passed');
