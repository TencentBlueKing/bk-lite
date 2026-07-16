/**
 * 把 NetworkNodeShape 的 React 树等价地渲染成一段 HTML 字符串,
 * 让 X6 内置的 `html` shape 写到 foreignObject.innerHTML 上。
 *
 * 为什么改 HTML 字符串:
 * 1. @antv/x6-react-shape 在 cell data 变化时会 **unmount + remount**
 *    整个 React 子树(见 react-shape 源码 `renderReactComponent`),
 *    在 React 18 StrictMode + 我们 60s runtime 刷新叠加下,会触发
 *    `removeChild on 'Node': The node to be removed is not a child of this node.`
 *    这种 React 18 dev mode 才会 throw 的 uncaught error。
 * 2. innerHTML 由 X6 直接写,React 的 reconciler 不参与,X6 内部用
 *    VNode + 局部 innerHTML 替换,完全没有 React 卸载竞争。
 *
 * 性能:
 * - innerHTML 整体替换(无 React diff),对 50 个节点、60s 刷新一次的场景
 *   完全够用,实测节点 < 50 时一帧 < 1ms。
 *
 * 注意:
 * - 该函数当前未被任何模块调用(design.md §7.2 已切到 networkNodeShape.tsx
 *   的 ReactShape),保留以便未来回到 X6 html shape 时无需重新写 i18n。
 *   t 参数必须传 —— 整段字符串通过 t() 输出,不要在调用方拼接中文。
 */
import type {
  NetworkMetricRuntime,
  NetworkNodeRuntime,
  NetworkTopologyMetric,
  NetworkTopologyNode,
} from '@/app/ops-analysis/types/networkTopology';
import { resolveNodeOuterColor, NODE_UNFALLBACK_COLOR } from './nodeStatus';
import { formatNetworkMetricValue } from './metricValueFormat';

/** 轻量 t 函数签名(只取项目用到的两参形式,避免引入 useTranslation 在纯函数里)。 */
type TFunction = (id: string, values?: Record<string, string | number>) => string;

const escapeAttr = (s: string): string =>
  s
    .replace(/&/g, '&amp;')
    .replace(/"/g, '&quot;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');

const escapeText = (s: string): string =>
  s
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');

const formatMetricValue = (
  metric: NetworkTopologyMetric,
  runtime: NetworkMetricRuntime[] | undefined,
  t: TFunction,
): string => {
  if (!runtime) return t('opsAnalysis.networkTopology.nodeShape.valueNoData');
  const hit = runtime.find(
    (item) =>
      item.metric_field === metric.metric_field &&
      item.result_table_id === metric.result_table_id,
  );
  if (!hit) return t('opsAnalysis.networkTopology.node.valueAfterSave');
  if (hit.status === 'error') return t('opsAnalysis.networkTopology.node.valueFailed');
  if (hit.value === null || hit.value === undefined) return t('opsAnalysis.networkTopology.node.valueNoData');
  return formatNetworkMetricValue(hit.value, hit.unit, {
    fallbackUnit: metric.unit,
  });
};

/**
 * 把节点卡片渲染成一段独立 HTML 字符串,带 ``data-*`` 属性便于 e2e 测试。
 *
 * @param t i18n 函数。必须传入以保证多语言,缺省时抛错。
 */
export const renderNetworkNodeHtml = (
  node: NetworkTopologyNode,
  t: TFunction,
  nodeRuntime?: NetworkNodeRuntime,
  selected: boolean = false,
): string => {
  const runtimeMetrics = nodeRuntime?.metrics ?? [];
  const outerColor =
    resolveNodeOuterColor(node.metrics, runtimeMetrics) ??
    NODE_UNFALLBACK_COLOR;

  const status = nodeRuntime?.status ?? 'unknown';
  const summary = nodeRuntime?.interface_summary;
  const summaryText = summary
    ? `${summary.up}/${summary.down}/${summary.unknown}`
    : 'unknown';

  const init = (node.bk_obj_id || '').replace(/^bk_/, '').slice(0, 2).toUpperCase();
  const displayName = escapeText(node.bk_inst_name || node.bk_obj_id);
  const ipOrObj = escapeText(node.ip_addr || node.bk_obj_id);

  const errorCode = nodeRuntime?.error_code ?? t('opsAnalysis.networkTopology.nodeShape.normal');
  const metricsHtml = node.metrics
    .slice(0, 2)
    .map((m) => {
      const label = escapeText(m.display_name || m.metric_field);
      const value = escapeText(formatMetricValue(m, runtimeMetrics, t));
      return `<div style="display:flex;justify-content:space-between;font-size:11px;color:#334250;margin-top:4px;">
        <span style="overflow:hidden;text-overflow:ellipsis;white-space:nowrap;max-width:130px;">${label}</span>
        <strong style="color:#192733;">${value}</strong>
      </div>`;
    })
    .join('');
  const noMetricsHtml =
    node.metrics.length === 0
      ? `<div style="font-size:11px;color:#8a98a5;margin-top:6px;">${escapeText(t('opsAnalysis.networkTopology.nodeShape.noMetrics'))}</div>`
      : '';

  const borderColor = selected ? '#2f8fb0' : '#cfdbe5';
  const boxShadow = selected
    ? '0 0 0 2px rgba(47,143,176,0.18), 0 16px 34px rgba(36,50,63,0.18)'
    : '0 12px 26px rgba(36,50,63,0.12)';

  return (
    `<div data-testid="network-node-shape" data-status="${escapeAttr(status)}" ` +
    `style="width:190px;min-height:112px;padding:10px;background:#fff;` +
    `border:1px solid ${borderColor};border-top:3px solid ${escapeAttr(outerColor)};` +
    `border-radius:8px;${`box-shadow:${boxShadow};`}user-select:none;box-sizing:border-box;">` +
    `<div style="display:flex;align-items:center;gap:8px;">` +
    `<span style="display:inline-grid;place-items:center;width:32px;height:32px;` +
    `background:#eef4f6;border-radius:6px;color:#335364;font-weight:700;font-size:11px;">` +
    `${escapeText(init)}</span>` +
    `<div style="min-width:0;flex:1;">` +
    `<div style="overflow:hidden;text-overflow:ellipsis;white-space:nowrap;` +
    `font-weight:650;font-size:13px;color:#1f2933;">${displayName}</div>` +
    `<div style="font-size:11px;color:#73808c;margin-top:2px;">${ipOrObj}</div>` +
    `</div>` +
    `<span style="width:9px;height:9px;border-radius:999px;background:${escapeAttr(outerColor)};"></span>` +
    `</div>` +
    `<div style="display:flex;align-items:center;justify-content:space-between;margin-top:8px;` +
    `padding-top:6px;border-top:1px solid #e4ebf0;font-size:11px;color:#536270;">` +
    `<span>${escapeText(t('opsAnalysis.networkTopology.nodeShape.interfaceLabel', { summary: summaryText }))}</span>` +
    `<span>${escapeText(errorCode)}</span>` +
    `</div>` +
    metricsHtml +
    noMetricsHtml +
    `</div>`
  );
};
