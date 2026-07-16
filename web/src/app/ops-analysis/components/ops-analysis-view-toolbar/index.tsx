import React from 'react';
import PageHeaderShell from '@/components/page-header-shell';
import SourceOriginBadge from '@/components/source-origin-badge';

interface ViewToolbarProps {
  title?: React.ReactNode;
  description?: React.ReactNode;
  isBuiltIn?: boolean;
  actions?: React.ReactNode;
  style?: React.CSSProperties;
  className?: string;
  leftClassName?: string;
  titleClassName?: string;
  descriptionClassName?: string;
  actionsClassName?: string;
}

const ViewToolbar: React.FC<ViewToolbarProps> = ({
  title,
  description,
  isBuiltIn = false,
  actions,
  style,
  className = '',
  leftClassName = '',
  titleClassName = '',
  descriptionClassName = '',
  actionsClassName = '',
}) => {
  return (
    <PageHeaderShell
      title={(
        <>
          {title}
          {isBuiltIn && (
            <SourceOriginBadge kind="builtin" className="ml-2 align-middle" />
          )}
        </>
      )}
      subtitle={description}
      className={
        `w-full mb-2.5 rounded-xl border border-(--color-border-2) bg-(--color-bg-1) px-3.5 py-2.5 ${className}`.trim()
      }
      style={{ boxShadow: '0 8px 22px rgba(31, 63, 104, 0.05)', ...style }}
      headerRowClassName="flex items-center justify-between gap-4"
      contentClassName={`min-w-0 flex-1 mr-6 ${leftClassName}`.trim()}
      titleRowClassName="flex items-center"
      titleClassName={`m-0 text-xl leading-7 font-semibold text-(--color-text-1) ${titleClassName}`.trim()}
      subtitleRowClassName="mt-1"
      subtitleClassName={`m-0 text-sm leading-5 text-(--color-text-2) ${descriptionClassName}`.trim()}
      actions={actions}
      actionsClassName={`flex shrink-0 items-center gap-1.5 ${actionsClassName}`.trim()}
    />
  );
};

export default ViewToolbar;
