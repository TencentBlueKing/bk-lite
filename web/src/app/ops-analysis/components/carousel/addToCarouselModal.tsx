'use client';

import React, { useEffect, useState } from 'react';
import { Modal, Select, message } from 'antd';
import { useTranslation } from '@/utils/i18n';
import { useCarouselApi } from '@/app/ops-analysis/api/carousel';
import type { CanvasType } from '@/app/ops-analysis/constants/canvasTypes';
import type { CarouselSummary } from '@/app/ops-analysis/types/carousel';
import { CAROUSEL_MAX_ITEMS } from '@/app/ops-analysis/utils/carouselPlayer';
import { canvasIdentityKey } from '@/app/ops-analysis/utils/carouselDraft';

interface AddToCarouselModalProps {
  open: boolean;
  resourceType: CanvasType | null;
  canvasId: number | null;
  onClose: () => void;
}

const AddToCarouselModal: React.FC<AddToCarouselModalProps> = ({
  open,
  resourceType,
  canvasId,
  onClose,
}) => {
  const { t } = useTranslation();
  const { listCarousels, appendCarouselItem } = useCarouselApi();
  const [rows, setRows] = useState<CarouselSummary[]>([]);
  const [selected, setSelected] = useState<number | null>(null);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (!open) return;
    setSelected(null);
    void listCarousels().then(setRows).catch(() => setRows([]));
  }, [listCarousels, open]);

  return (
    <Modal
      title={t('opsCarousel.addToCarousel')}
      open={open}
      centered
      okText={t('common.confirm')}
      cancelText={t('common.cancel')}
      confirmLoading={submitting}
      okButtonProps={{ disabled: selected == null }}
      onCancel={onClose}
      onOk={() => {
        if (selected == null || !resourceType || canvasId == null) return;
        const target = rows.find((row) => row.id === selected);
        if (target && target.item_count >= CAROUSEL_MAX_ITEMS) {
          message.warning(t('opsCarousel.itemLimit'));
          return;
        }
        setSubmitting(true);
        void appendCarouselItem(selected, {
          resource_type: resourceType,
          canvas_id: canvasId,
        }).then(() => {
          message.success(t('opsCarousel.added'));
          onClose();
        }).catch((error) => {
          console.error('Failed to append carousel item:', error);
        }).finally(() => setSubmitting(false));
      }}
    >
      <Select
        className="w-full"
        showSearch
        optionFilterProp="label"
        placeholder={t('opsCarousel.pickList')}
        value={selected ?? undefined}
        options={rows.map((row) => {
          const included = resourceType != null && canvasId != null
            && (row.canvas_keys || []).includes(canvasIdentityKey(resourceType, canvasId));
          const full = row.item_count >= CAROUSEL_MAX_ITEMS;
          return {
            value: row.id,
            disabled: included || full,
            label: included
              ? `${row.name}（${t('opsCarousel.alreadyContains')}）`
              : `${row.name} (${row.item_count})`,
          };
        })}
        onChange={(value) => setSelected(value)}
      />
    </Modal>
  );
};

export default AddToCarouselModal;
