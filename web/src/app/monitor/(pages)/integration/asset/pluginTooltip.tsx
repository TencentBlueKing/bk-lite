import React from 'react';

export interface CollectorNode {
  id: string;
  name: string;
}

interface PluginTooltipContentProps {
  statusText: string;
  lastReportTimeLabel: string;
  timeText: string;
  collectionNodeLabel: string;
  notAssociatedText: string;
  collectMode?: string;
  collectorNodes?: CollectorNode[];
}

export const formatCollectorNodes = (
  collectMode?: string,
  collectorNodes?: CollectorNode[]
): string[] => {
  if (collectMode !== 'auto' || !Array.isArray(collectorNodes)) return [];

  const seen = new Set<string>();
  return collectorNodes.flatMap((node) => {
    const id = String(node?.id || '').trim();
    if (!id || seen.has(id)) return [];
    seen.add(id);
    const name = String(node?.name || id).trim() || id;
    return [name === id ? id : `${name} (${id})`];
  });
};

const PluginTooltipContent = ({
  statusText,
  lastReportTimeLabel,
  timeText,
  collectionNodeLabel,
  notAssociatedText,
  collectMode,
  collectorNodes
}: PluginTooltipContentProps) => {
  const formattedNodes = formatCollectorNodes(collectMode, collectorNodes);

  return (
    <div className="text-xs leading-5">
      <div>{statusText}</div>
      <div>{`${lastReportTimeLabel}：${timeText}`}</div>
      <div>
        <span>{`${collectionNodeLabel}：`}</span>
        {formattedNodes.length ? (
          <div className="pl-3">
            {formattedNodes.map((node) => (
              <div key={node}>{node}</div>
            ))}
          </div>
        ) : (
          <span>{notAssociatedText}</span>
        )}
      </div>
    </div>
  );
};

export default PluginTooltipContent;
