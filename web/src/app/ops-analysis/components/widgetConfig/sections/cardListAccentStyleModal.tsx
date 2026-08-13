import React, { useEffect, useRef, useState } from 'react';
import { Modal, Select } from 'antd';
import useUnsavedConfirm from '@/hooks/useUnsavedConfirm';
import { ValueMappingsConfigSection } from '@/app/ops-analysis/components/valueMappingsConfigSection';
import {
  normalizeCardListAccentStyle,
  type CardListAccentDisplayType,
  type CardListAccentStyle,
} from '@/app/ops-analysis/utils/cardList';
import type { ValueMapping } from '@/app/ops-analysis/utils/valueMapping';

interface CardListAccentStyleDraft {
  displayType?: CardListAccentDisplayType;
  valueMappings?: ValueMapping[];
}

interface CardListAccentStyleModalProps {
  open: boolean;
  title: string;
  value?: CardListAccentStyle;
  t: (key: string) => string;
  onCancel: () => void;
  onConfirm: (nextStyle?: CardListAccentStyle) => void;
}

const snapshotStyle = (draft: CardListAccentStyleDraft) =>
  JSON.stringify({
    displayType: draft.displayType || 'text',
    valueMappings: draft.valueMappings || [],
  });

const toDraft = (value?: CardListAccentStyle): CardListAccentStyleDraft => ({
  displayType: value?.displayType,
  valueMappings: value?.valueMappings ? [...value.valueMappings] : undefined,
});

export const CardListAccentStyleModal: React.FC<
  CardListAccentStyleModalProps
> = ({ open, title, value, t, onCancel, onConfirm }) => {
  const [draft, setDraft] = useState<CardListAccentStyleDraft>({});
  const guardClose = useUnsavedConfirm();
  const initialSnapshotRef = useRef('');

  useEffect(() => {
    if (!open) return;
    const next = toDraft(value);
    setDraft(next);
    initialSnapshotRef.current = snapshotStyle(next);
  }, [open, value]);

  const handleCancel = () =>
    guardClose(snapshotStyle(draft) !== initialSnapshotRef.current, onCancel);

  const handleConfirm = () => {
    onConfirm(normalizeCardListAccentStyle(draft));
  };

  return (
    <Modal
      title={title}
      width={720}
      open={open}
      centered
      maskClosable={false}
      onCancel={handleCancel}
      onOk={handleConfirm}
      destroyOnHidden
      styles={{
        body: {
          maxHeight: 'calc(100vh - 320px)',
          overflowY: 'auto',
          paddingRight: 8,
        },
      }}
    >
      <div className="space-y-5">
        <div>
          <div className="mb-2 text-sm text-(--color-text-2)">
            {t('dashboard.cardListAccentDisplayType')}
          </div>
          <Select
            value={draft.displayType || 'text'}
            style={{ width: 220 }}
            options={[
              {
                value: 'text',
                label: t('dashboard.cardListAccentDisplayTypeText'),
              },
              {
                value: 'textWithBackground',
                label: t('dashboard.cardListAccentDisplayTypeTextWithBackground'),
              },
              {
                value: 'colorBackground',
                label: t('dashboard.cardListAccentDisplayTypeColorDot'),
              },
            ]}
            onChange={(next) =>
              setDraft((prev) => ({
                ...prev,
                displayType: next === 'text' ? undefined : next,
              }))
            }
          />
        </div>

        <div>
          <div className="mb-2 text-sm text-(--color-text-2)">
            {t('dashboard.cardListAccentValueMappings')}
          </div>
          <ValueMappingsConfigSection
            t={t}
            value={draft.valueMappings || []}
            onChange={(next: ValueMapping[]) =>
              setDraft((prev) => ({
                ...prev,
                valueMappings: next.length ? next : undefined,
              }))
            }
          />
        </div>
      </div>
    </Modal>
  );
};
