import { CopyOutlined, DeleteOutlined } from '@ant-design/icons';
import { Tooltip } from 'antd';
import { useTranslation } from '@/utils/i18n';

function ToolButton({ label, onClick, children }: { label: string; onClick: () => void; children: React.ReactNode }) {
  return (
    <Tooltip title={label}>
      <button
        type="button"
        aria-label={label}
        className="flex h-7 w-7 items-center justify-center text-sm text-white hover:bg-white/20"
        onClick={onClick}
      >
        {children}
      </button>
    </Tooltip>
  );
}

export function CanvasTools({ onCopy, onDelete }: { onCopy?: () => void; onDelete: () => void }) {
  const { t } = useTranslation();
  return (
    <div
      className="nodrag nopan flex overflow-hidden rounded-md bg-[var(--color-primary)] shadow-xs"
      onPointerDown={(event) => event.stopPropagation()}
      onClick={(event) => event.stopPropagation()}
    >
      {onCopy ? <ToolButton label={t('itsm.common.copy')} onClick={onCopy}><CopyOutlined /></ToolButton> : null}
      <ToolButton label={t('itsm.common.delete')} onClick={onDelete}><DeleteOutlined /></ToolButton>
    </div>
  );
}
