import React from 'react';
import { Tag, Tooltip } from 'antd';

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

interface PluginTooltipTriggerProps {
  ariaLabel: string;
  color: string;
  onActivate: () => void;
  title: React.ReactNode;
  children: React.ReactNode;
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

export const PluginTooltipTrigger = ({
  ariaLabel,
  color,
  onActivate,
  title,
  children
}: PluginTooltipTriggerProps) => {
  const handleKeyDown = (event: React.KeyboardEvent<HTMLElement>) => {
    if (event.key !== 'Enter' && event.key !== ' ') return;
    event.preventDefault();
    onActivate();
  };

  return (
    <Tooltip
      title={title}
      classNames={{ root: 'asset-tooltip' }}
      mouseEnterDelay={0}
    >
      <Tag
        role="button"
        tabIndex={0}
        aria-label={ariaLabel}
        color={color}
        className="cursor-pointer"
        onClick={onActivate}
        onKeyDown={handleKeyDown}
      >
        {children}
      </Tag>
    </Tooltip>
  );
};

export default PluginTooltipContent;
