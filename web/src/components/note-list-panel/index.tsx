import React from 'react';

export interface NoteListPanelProps {
  items: React.ReactNode[];
  className?: string;
  itemClassName?: string;
  textClassName?: string;
  bulletClassName?: string;
  gapClassName?: string;
}

const defaultItemClassName =
  'flex items-start gap-2 text-[13px] leading-6 text-[var(--color-text-2)]';

const NoteListPanel: React.FC<NoteListPanelProps> = ({
  items,
  className = '',
  itemClassName = '',
  textClassName = '',
  bulletClassName = 'mt-2 h-1.5 w-1.5 shrink-0 rounded-full bg-[var(--color-primary)]',
  gapClassName = 'space-y-2',
}) => {
  return (
    <div className={[gapClassName, className].filter(Boolean).join(' ')}>
      {items.map((item, index) => (
        <div
          key={index}
          className={[defaultItemClassName, itemClassName].filter(Boolean).join(' ')}
        >
          <span className={bulletClassName} />
          <span className={textClassName}>{item}</span>
        </div>
      ))}
    </div>
  );
};

export default NoteListPanel;
