// Tag 配色与主场节点列表的 useTelegrafMap 同源：正常绿、异常红、停止/安装失败黄、
// 安装中蓝，未知与未启动走默认灰。
export type NodeStatusTagColor =
  | 'success'
  | 'error'
  | 'warning'
  | 'processing'
  | 'default';

export const COLLECTOR_STATUS_TAG_COLOR: Record<string, NodeStatusTagColor> = {
  '0': 'success',
  '1': 'default',
  '2': 'error',
  '3': 'warning',
  '4': 'default',
  '10': 'processing',
  '11': 'default',
  '12': 'warning',
};

export const COLLECTOR_STATUS_I18N: Record<string, string> = {
  '0': 'node-manager.cloudregion.node.normal',
  '1': 'node-manager.cloudregion.node.unknown',
  '2': 'node-manager.cloudregion.node.error',
  '3': 'node-manager.cloudregion.node.stopped',
  '4': 'node-manager.cloudregion.node.notStarted',
  '10': 'node-manager.cloudregion.node.installing',
  '11': 'node-manager.cloudregion.node.notStarted',
  '12': 'node-manager.cloudregion.node.failInstall',
};

export function nodeOnlineI18nKey(active: boolean | undefined | null): string | null {
  if (typeof active !== 'boolean') return null;
  return active
    ? 'node-manager.cloudregion.node.online'
    : 'node-manager.cloudregion.node.offline';
}

export function collectorStatusI18nKey(status: string | number | undefined | null): string {
  if (status == null || status === '') {
    return 'node-manager.cloudregion.node.unknown';
  }
  return COLLECTOR_STATUS_I18N[String(status)] || 'node-manager.cloudregion.node.unknown';
}

// 与主场 Sidecar 列同口径：在线绿、离线黄；active 非布尔时不着色，由调用方显示 --。
export function nodeOnlineTagColor(
  active: boolean | undefined | null
): NodeStatusTagColor | null {
  if (typeof active !== 'boolean') return null;
  return active ? 'success' : 'warning';
}

export function collectorStatusTagColor(
  status: string | number | undefined | null
): NodeStatusTagColor {
  if (status == null || status === '') return 'default';
  return COLLECTOR_STATUS_TAG_COLOR[String(status)] || 'default';
}

export interface CollectorStatusSummaryItem {
  status: string;
  i18nKey: string;
  tagColor: NodeStatusTagColor;
  count: number;
}

// 主场列表模式：同状态的采集器合并成「文案: 数量」，按首次出现顺序稳定输出。
export function summarizeCollectorStatuses(
  collectors: ReadonlyArray<{ status?: string | number | null }> | null | undefined
): CollectorStatusSummaryItem[] {
  const grouped = new Map<string, CollectorStatusSummaryItem>();
  for (const collector of collectors || []) {
    const raw = collector?.status;
    const status = raw == null || raw === '' ? '' : String(raw);
    const existing = grouped.get(status);
    if (existing) {
      existing.count += 1;
      continue;
    }
    grouped.set(status, {
      status,
      i18nKey: collectorStatusI18nKey(raw),
      tagColor: collectorStatusTagColor(raw),
      count: 1,
    });
  }
  return [...grouped.values()];
}

const STALE_HEALTHY_KEYWORDS =
  /\b(healthy|reporting|running|normal|ok|success)\b|正常|运行中/i;

// 解决离线与存量心跳说明打架问题：
// 在线（active === true）时展示 healthy / reporting 等最新摘要；
// 离线（active === false）时，过滤掉最后一次心跳遗留的 healthy 词汇，仅保留明确的离线/超时异常原因；若无可靠原因则返回 null（前端隐藏该说明块）。
export function resolveSidecarStatusMessage(
  active: boolean | undefined | null,
  rawMessage?: string | null
): string | null {
  const msg = rawMessage?.trim();
  if (!msg) return null;

  if (active === true) {
    return msg;
  }

  if (active === false) {
    if (STALE_HEALTHY_KEYWORDS.test(msg)) {
      return null;
    }
    return msg;
  }

  return msg;
}

export function extractCollectorMessage(rawMessage: unknown): string {
  if (!rawMessage) return '';
  if (typeof rawMessage === 'string') return rawMessage.trim();
  if (typeof rawMessage === 'object' && rawMessage !== null) {
    const msgObj = rawMessage as Record<string, unknown>;
    return String(msgObj.final_message || msgObj.message || '').trim();
  }
  return String(rawMessage).trim();
}

export interface ComponentVersionItem {
  version?: string;
  latest_version?: string;
  upgradeable?: boolean;
}

export interface ParsedComponentVersions {
  controller: ComponentVersionItem | null;
  collectors: Map<string, ComponentVersionItem>;
}

export function parseComponentVersions(
  versions: ReadonlyArray<Record<string, unknown>> | null | undefined
): ParsedComponentVersions {
  let controller: ComponentVersionItem | null = null;
  const collectors = new Map<string, ComponentVersionItem>();

  for (const item of versions || []) {
    const compType = String(item?.component_type || '').toLowerCase();
    const versionItem: ComponentVersionItem = {
      version: item?.version ? String(item.version) : undefined,
      latest_version: item?.latest_version ? String(item.latest_version) : undefined,
      upgradeable: Boolean(item?.upgradeable),
    };
    if (compType === 'controller') {
      if (!controller) {
        controller = versionItem;
      }
    } else if (compType === 'collector') {
      const compId = String(item?.component_id ?? '').trim();
      if (compId) {
        collectors.set(compId, versionItem);
      }
    }
  }

  return { controller, collectors };
}

