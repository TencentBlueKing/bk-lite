import { Tooltip } from 'antd';
import { StatusToneBadge } from '@/app/monitor/utils/statusTone';
import type { CollectorNode } from './pluginTooltip';

export type CollectorNodeDisplayState = 'online' | 'offline' | 'removed';

export interface SummarizedCollectorNode {
  id: string;
  name: string;
  state: CollectorNodeDisplayState;
}

interface PluginWithCollectorNodes {
  collector_nodes?: CollectorNode[] | null;
}

export interface CollectorNodeStatusLabels {
  offline: string;
  removed: string;
}

const nodeState = (node: CollectorNode): CollectorNodeDisplayState => {
  if (node?.removed) return 'removed';
  if (node?.active === false) return 'offline';
  return 'online';
};

const preferNode = (current: CollectorNode, next: CollectorNode): CollectorNode => {
  if (Boolean(current?.removed) !== Boolean(next?.removed)) {
    return current?.removed ? next : current;
  }
  if (next?.removed) return current;
  if (next?.active === true) return current?.active === true ? current : next;
  if (current?.active === true) return current;
  if (next?.active === false) return current?.active === false ? current : next;
  return current;
};

const compareNodes = (
  left: SummarizedCollectorNode,
  right: SummarizedCollectorNode
) => {
  const byFoldedName = left.name
    .toLocaleLowerCase()
    .localeCompare(right.name.toLocaleLowerCase());
  if (byFoldedName !== 0) return byFoldedName;
  const byName = left.name.localeCompare(right.name);
  if (byName !== 0) return byName;
  return left.id.localeCompare(right.id);
};

export const summarizeInstanceCollectorNodes = (
  plugins?: readonly PluginWithCollectorNodes[] | null
): SummarizedCollectorNode[] => {
  const chosen = new Map<string, CollectorNode>();
  for (const plugin of plugins ?? []) {
    const nodes = plugin?.collector_nodes;
    if (!Array.isArray(nodes)) continue;
    for (const node of nodes) {
      const id = String(node?.id ?? '').trim();
      if (!id) continue;
      const current = chosen.get(id);
      chosen.set(id, current ? preferNode(current, node) : node);
    }
  }
  return Array.from(chosen.entries())
    .map(([id, node]) => ({
      id,
      name: String(node?.name ?? '').trim() || id,
      state: nodeState(node),
    }))
    .sort(compareNodes);
};

export const collectorNodeDetailText = (
  node: SummarizedCollectorNode,
  labels: CollectorNodeStatusLabels
): string => {
  const identity = node.name === node.id ? node.id : `${node.name} (${node.id})`;
  if (node.state === 'offline' && labels.offline) {
    return `${identity} · ${labels.offline}`;
  }
  if (node.state === 'removed' && labels.removed) {
    return `${identity} · ${labels.removed}`;
  }
  return identity;
};

interface CollectorNodeColumnProps {
  plugins?: readonly PluginWithCollectorNodes[] | null;
  notAssociatedText: string;
  offlineText: string;
  removedText: string;
}

export const CollectorNodeColumn = ({
  plugins,
  notAssociatedText,
  offlineText,
  removedText,
}: CollectorNodeColumnProps) => {
  const nodes = summarizeInstanceCollectorNodes(plugins);
  if (!nodes.length) {
    return (
      <span className="text-[var(--color-text-3)]">{notAssociatedText}</span>
    );
  }

  const labels = { offline: offlineText, removed: removedText };
  return (
    <div className="flex max-w-full flex-wrap items-center gap-1">
      {nodes.map((node) => (
        <Tooltip
          key={node.id}
          title={collectorNodeDetailText(node, labels)}
          classNames={{ root: 'asset-tooltip' }}
          mouseEnterDelay={0}
        >
          <span className="inline-flex min-w-0 max-w-full items-center gap-1">
            <span className="min-w-0 truncate">{node.name}</span>
            {node.state === 'offline' ? (
              <StatusToneBadge
                className="m-0 shrink-0"
                tone="warning"
                label={offlineText}
              />
            ) : null}
            {node.state === 'removed' ? (
              <StatusToneBadge
                className="m-0 shrink-0"
                tone="fail"
                label={removedText}
              />
            ) : null}
          </span>
        </Tooltip>
      ))}
    </div>
  );
};
