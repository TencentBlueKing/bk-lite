import React, { useEffect, useMemo, useRef, useState } from 'react';
import { Button, Modal, Select } from 'antd';
import { PlusCircleOutlined } from '@ant-design/icons';
import useUnsavedConfirm from '@/hooks/useUnsavedConfirm';
import { ValueMappingsConfigSection } from '@/app/ops-analysis/components/valueMappingsConfigSection';
import { ThresholdColorConfigSection } from '@/app/ops-analysis/components/thresholdColorConfigSection';
import { DEFAULT_THRESHOLD_COLORS } from '@/app/ops-analysis/constants/threshold';
import type { TableColumnConfigItem } from '@/app/ops-analysis/types/dashBoard';
import type { ThresholdColorConfig } from '@/app/ops-analysis/utils/thresholdUtils';
import type { ValueMapping } from '@/app/ops-analysis/utils/valueMapping';
import type { DisplayColumnRow } from '../utils/columnProbing';

interface ColumnCellStyleDraft {
  cellType?: TableColumnConfigItem['cellType'];
  valueMappings?: ValueMapping[];
  cellThresholdColors?: ThresholdColorConfig[];
}

interface ColumnCellStyleModalProps {
  open: boolean;
  column?: DisplayColumnRow | null;
  t: (key: string) => string;
  onCancel: () => void;
  onConfirm: (nextStyle: ColumnCellStyleDraft) => void;
}

const snapshotStyle = (draft: ColumnCellStyleDraft) =>
  JSON.stringify({
    cellType: draft.cellType || 'text',
    valueMappings: draft.valueMappings || [],
    cellThresholdColors: draft.cellThresholdColors || [],
  });

const toDraft = (column?: DisplayColumnRow | null): ColumnCellStyleDraft => ({
  cellType: column?.cellType,
  valueMappings: column?.valueMappings ? [...column.valueMappings] : undefined,
  cellThresholdColors: column?.cellThresholdColors
    ? column.cellThresholdColors.map((item) => ({ ...item }))
    : undefined,
});

export const ColumnCellStyleModal: React.FC<ColumnCellStyleModalProps> = ({
  open,
  column,
  t,
  onCancel,
  onConfirm,
}) => {
  const [draft, setDraft] = useState<ColumnCellStyleDraft>({});
  const guardClose = useUnsavedConfirm();
  const initialSnapshotRef = useRef('');

  useEffect(() => {
    if (!open || !column) return;
    const next = toDraft(column);
    setDraft(next);
    initialSnapshotRef.current = snapshotStyle(next);
  }, [open, column]);

  const columnLabel = useMemo(
    () => column?.title || column?.key || '',
    [column],
  );

  const handleCancel = () =>
    guardClose(snapshotStyle(draft) !== initialSnapshotRef.current, onCancel);

  const handleConfirm = () => {
    onConfirm({
      cellType: draft.cellType === 'text' ? undefined : draft.cellType,
      valueMappings: draft.valueMappings?.length
        ? draft.valueMappings
        : undefined,
      cellThresholdColors: draft.cellThresholdColors?.length
        ? draft.cellThresholdColors
        : undefined,
    });
  };

  const handleCellThresholdChange = (
    index: number,
    field: 'value' | 'color',
    value: string | number,
  ) => {
    setDraft((prev) => {
      const current = [...(prev.cellThresholdColors || [])];
      if (!current[index]) return prev;
      current[index] = {
        ...current[index],
        [field]: String(value),
      };
      return { ...prev, cellThresholdColors: current };
    });
  };

  const handleCellThresholdBlur = (index: number, value: number | null) => {
    setDraft((prev) => {
      const current = [...(prev.cellThresholdColors || [])];
      if (!current[index] || index === current.length - 1) return prev;
      current[index] = {
        ...current[index],
        value: String(value ?? 0),
      };
      current.sort((a, b) => parseFloat(b.value) - parseFloat(a.value));
      return { ...prev, cellThresholdColors: current };
    });
  };

  const handleAddCellThreshold = (afterIndex?: number) => {
    setDraft((prev) => {
      const current = [...(prev.cellThresholdColors || [])];
      if (current.length === 0) {
        return {
          ...prev,
          cellThresholdColors: [...DEFAULT_THRESHOLD_COLORS],
        };
      }
      const insertAt =
        typeof afterIndex === 'number' ? afterIndex + 1 : current.length - 1;
      const template = current[Math.max(0, insertAt - 1)] || current[0];
      current.splice(insertAt, 0, {
        value: template.value,
        color: template.color,
      });
      return { ...prev, cellThresholdColors: current };
    });
  };

  const handleRemoveCellThreshold = (index: number) => {
    setDraft((prev) => {
      const current = [...(prev.cellThresholdColors || [])];
      if (current.length === 0) return prev;
      if (current.length === 1) {
        return { ...prev, cellThresholdColors: undefined };
      }
      if (index === current.length - 1) return prev;
      current.splice(index, 1);
      return { ...prev, cellThresholdColors: current };
    });
  };

  return (
    <Modal
      title={
        <span>
          {t('dashboard.columnCellStyleConfig')}
          {columnLabel ? (
            <span className="ml-2 text-sm font-normal text-(--color-text-3)">
              {columnLabel}
            </span>
          ) : null}
        </span>
      }
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
            {t('dashboard.columnCellType')}
          </div>
          <Select
            value={draft.cellType || 'text'}
            style={{ width: 220 }}
            options={[
              { value: 'text', label: t('dashboard.columnCellTypeText') },
              {
                value: 'colorBackground',
                label: t('dashboard.columnCellTypeColorBackground'),
              },
            ]}
            onChange={(value) =>
              setDraft((prev) => ({
                ...prev,
                cellType: value === 'text' ? undefined : value,
              }))
            }
          />
        </div>

        <div>
          <div className="mb-2 text-sm text-(--color-text-2)">
            {t('dashboard.columnValueMappings')}
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

        <div>
          {(draft.cellThresholdColors || []).length > 0 ? (
            <div>
              <div className="mb-2 flex items-center justify-between gap-2">
                <span className="text-sm text-(--color-text-2)">
                  {t('dashboard.columnCellThresholdColors')}
                </span>
                <Button
                  type="link"
                  size="small"
                  onClick={() =>
                    setDraft((prev) => ({
                      ...prev,
                      cellThresholdColors: undefined,
                    }))
                  }
                >
                  {t('dashboard.clearColumnCellThresholdColors')}
                </Button>
              </div>
              <ThresholdColorConfigSection
                t={t}
                thresholdColors={
                  draft.cellThresholdColors as ThresholdColorConfig[]
                }
                onThresholdChange={handleCellThresholdChange}
                onThresholdBlur={handleCellThresholdBlur}
                onAddThreshold={handleAddCellThreshold}
                onRemoveThreshold={handleRemoveCellThreshold}
              />
            </div>
          ) : (
            <>
              <div className="mb-2 text-sm text-(--color-text-2)">
                {t('dashboard.columnCellThresholdColors')}
              </div>
              <Button
                type="dashed"
                size="small"
                icon={<PlusCircleOutlined />}
                onClick={() => handleAddCellThreshold()}
              >
                {t('dashboard.addColumnCellThresholdColors')}
              </Button>
            </>
          )}
        </div>
      </div>
    </Modal>
  );
};
