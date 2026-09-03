import React, { useState } from 'react';
import { BookOutlined, DownOutlined, ToolOutlined } from '@ant-design/icons';
import { SkillViewItem } from '@/app/opspilot/types/global';

interface SkillViewProps {
  items?: SkillViewItem[];
}

const SkillView: React.FC<SkillViewProps> = ({ items }) => {
  const [expanded, setExpanded] = useState(false);
  const visibleItems = (items || []).filter(item => item?.name);
  const missingToolCount = visibleItems.reduce((count, item) => (
    count + (Array.isArray(item.missing_tools) ? item.missing_tools.length : 0)
  ), 0);

  if (visibleItems.length === 0) return null;

  return (
    <div className="my-2">
      <button
        type="button"
        className="inline-flex items-center gap-1.5 py-0.5 px-1 -ml-1 text-xs text-[var(--color-text-3)] hover:text-[var(--color-text-2)] hover:bg-[var(--color-fill-1)] rounded transition-colors cursor-pointer select-none group border-0 bg-transparent"
        onClick={() => setExpanded(prev => !prev)}
      >
        <span className="flex items-center gap-1.5">
          <BookOutlined className="text-[11px] text-[var(--color-primary)]" />
          <span className="font-normal text-[var(--color-text-2)]">技能包命中 ({visibleItems.length})</span>
          {missingToolCount > 0 && (
            <span className="rounded bg-[var(--color-warning-light-1)] px-1 text-[10px] text-[var(--color-warning)]">
              缺 {missingToolCount} 工具
            </span>
          )}
        </span>
        <DownOutlined className={`text-[8px] text-[var(--color-text-4)] group-hover:text-[var(--color-text-3)] transition-transform ${expanded ? 'rotate-180' : ''}`} />
      </button>
      {expanded && (
        <div className="mt-1.5 ml-1 space-y-2 border-l-2 border-[var(--color-fill-3)] pl-3">
          {visibleItems.map((item) => (
            <div key={item.id || item.name} className="py-1">
              <div className="flex min-w-0 items-center gap-1.5">
                <span className="text-xs font-medium text-[var(--color-text-1)]">{item.name}</span>
                {item.package_id && (
                  <span className="shrink-0 rounded bg-[var(--color-fill-1)] px-1.5 py-0.5 text-[10px] text-[var(--color-text-3)]">
                    {item.package_id}
                  </span>
                )}
              </div>
              {item.description && (
                <p className="m-0 mt-0.5 text-xs leading-relaxed text-[var(--color-text-3)]">
                  {item.description}
                </p>
              )}
              {Array.isArray(item.missing_tools) && item.missing_tools.length > 0 && (
                <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
                  <span className="inline-flex items-center gap-1 text-[11px] text-[var(--color-warning)]">
                    <ToolOutlined className="text-[10px]" />
                    待绑定:
                  </span>
                  {item.missing_tools.map(tool => (
                    <span key={tool} className="rounded bg-[var(--color-warning-light-1)] px-1.5 py-0.2 text-[11px] text-[var(--color-warning)]">
                      {tool}
                    </span>
                  ))}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

export default SkillView;
