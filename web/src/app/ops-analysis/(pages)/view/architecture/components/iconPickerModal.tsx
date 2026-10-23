import React from 'react';
import OperateModal from '@/components/operate-modal';
import type { IconPickerRequest } from '@bk-lite/isoflow';

interface IconPickerModalProps {
  request: IconPickerRequest | null;
  onClose: () => void;
}

const IconPickerModal: React.FC<IconPickerModalProps> = ({ request, onClose }) => {
  return (
    <OperateModal
      open={Boolean(request)}
      width={562}
      centered
      destroyOnHidden
      title={request?.title}
      footer={null}
      onCancel={onClose}
    >
      <div className="grid grid-cols-6 gap-[2px]">
        {request?.icons.map((icon) => (
          <div
            key={icon.id}
            role="button"
            tabIndex={0}
            className="flex h-[88px] min-w-0 cursor-pointer flex-col items-center justify-center gap-1 border-0 bg-transparent p-1 text-[var(--color-text-2)] shadow-none outline-none hover:bg-[var(--color-fill-2)]"
            style={{ border: 'none', boxShadow: 'none' }}
            onClick={() => {
              request.onSelect(icon.id);
              onClose();
            }}
            onKeyDown={(event) => {
              if (event.key !== 'Enter' && event.key !== ' ') return;
              event.preventDefault();
              request.onSelect(icon.id);
              onClose();
            }}
          >
            <img src={icon.url} alt={icon.name} width={52} height={52} className="block h-[52px] w-[52px]" />
            <span className="w-full truncate text-center text-[10px] leading-3">{icon.name}</span>
          </div>
        ))}
      </div>
    </OperateModal>
  );
};

export default IconPickerModal;
