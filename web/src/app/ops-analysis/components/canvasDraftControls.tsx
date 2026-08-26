'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { Button, Dropdown, Empty, Input, Modal, Space, Spin, Tooltip } from 'antd';
import type { InputRef } from 'antd';
import { DownOutlined, LoadingOutlined } from '@ant-design/icons';
import dayjs from 'dayjs';
import { useTranslation } from '@/utils/i18n';
import CodeSnippet from '@/components/code-snippet';
import type { CanvasDraftHistoryItem } from '@/app/ops-analysis/api/canvasDraft';
import type { CanvasDraftController } from '@/app/ops-analysis/hooks/useCanvasDraft';

const CHECKPOINT_LABEL_MAX_LENGTH = 30;

interface CanvasDraftControlsProps {
  history: CanvasDraftHistoryItem[];
  savingFrame?: boolean;
  historyLoading?: boolean;
  onSaveFrame: () => Promise<void>;
  onRestore: (id: number) => Promise<void>;
  onUpdateLabel: (id: number, label: string) => Promise<void>;
}

const formatFrameTime = (createdAt: string) =>
  dayjs(createdAt).format('YYYY-MM-DD HH:mm');

const frameDisplayTitle = (item: CanvasDraftHistoryItem) => {
  const label = item.label?.trim();
  if (label) return label;
  return formatFrameTime(item.created_at);
};

interface HistoryLabelCellProps {
  item: CanvasDraftHistoryItem;
  editing: boolean;
  saving: boolean;
  draftLabel: string;
  onDraftLabelChange: (value: string) => void;
  onStartEdit: () => void;
  onCommit: () => void;
  onCancel: () => void;
}

const HistoryLabelCell = ({
  item,
  editing,
  saving,
  draftLabel,
  onDraftLabelChange,
  onStartEdit,
  onCommit,
  onCancel,
}: HistoryLabelCellProps) => {
  const { t } = useTranslation();
  const inputRef = useRef<InputRef>(null);
  const label = item.label?.trim();

  useEffect(() => {
    if (!editing) return;
    inputRef.current?.input?.focus();
  }, [editing]);

  if (editing) {
    return (
      <Input
        ref={inputRef}
        size="small"
        maxLength={CHECKPOINT_LABEL_MAX_LENGTH}
        placeholder={t('opsAnalysis.canvasDraft.namePlaceholder')}
        value={draftLabel}
        disabled={saving}
        suffix={saving ? <LoadingOutlined className="text-[12px]" /> : null}
        onChange={(event) => onDraftLabelChange(event.target.value)}
        onBlur={() => {
          void onCommit();
        }}
        onKeyDown={(event) => {
          if (event.key === 'Enter') {
            event.preventDefault();
            void onCommit();
          }
          if (event.key === 'Escape') {
            event.preventDefault();
            onCancel();
          }
        }}
      />
    );
  }

  const display = label || t('opsAnalysis.canvasDraft.namePlaceholder');

  return (
    <Tooltip title={label || t('opsAnalysis.canvasDraft.nameEditHint')}>
      <button
        type="button"
        className={`w-full truncate rounded px-1 py-0.5 text-left text-[13px] leading-5 transition-colors hover:bg-[var(--color-fill-2)] ${
          label
            ? 'text-[var(--color-text-1)]'
            : 'text-[var(--color-text-4)] italic'
        }`}
        onClick={onStartEdit}
      >
        {display}
      </button>
    </Tooltip>
  );
};

const CanvasDraftControls = ({
  history,
  savingFrame = false,
  historyLoading = false,
  onSaveFrame,
  onRestore,
  onUpdateLabel,
}: CanvasDraftControlsProps) => {
  const { t } = useTranslation();
  const [historyOpen, setHistoryOpen] = useState(false);
  const [viewing, setViewing] = useState<CanvasDraftHistoryItem | null>(null);
  const [restoringId, setRestoringId] = useState<number | null>(null);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [draftLabel, setDraftLabel] = useState('');
  const [savingLabelId, setSavingLabelId] = useState<number | null>(null);

  const restore = async (id: number) => {
    setRestoringId(id);
    try {
      await onRestore(id);
      setViewing(null);
      setHistoryOpen(false);
    } finally {
      setRestoringId(null);
    }
  };

  const openHistory = () => {
    setHistoryOpen(true);
  };

  const startEdit = useCallback((item: CanvasDraftHistoryItem) => {
    setEditingId(item.id);
    setDraftLabel(item.label || '');
  }, []);

  const cancelEdit = useCallback(() => {
    setEditingId(null);
    setDraftLabel('');
  }, []);

  const commitEdit = useCallback(
    async (item: CanvasDraftHistoryItem) => {
      const trimmed = draftLabel.trim();
      const current = item.label?.trim() || '';
      if (trimmed === current) {
        cancelEdit();
        return;
      }
      setSavingLabelId(item.id);
      try {
        await onUpdateLabel(item.id, trimmed);
        cancelEdit();
      } finally {
        setSavingLabelId(null);
      }
    },
    [cancelEdit, draftLabel, onUpdateLabel],
  );

  return (
    <>
      <Dropdown
        trigger={['hover']}
        mouseEnterDelay={0.05}
        mouseLeaveDelay={0.15}
        disabled={savingFrame}
        menu={{
          items: [
            {
              key: 'saveFrame',
              label: t('opsAnalysis.canvasDraft.saveFrame'),
              disabled: savingFrame,
              onClick: () => {
                void onSaveFrame();
              },
            },
            {
              key: 'history',
              disabled: savingFrame,
              label: (
                <span className="inline-flex items-center gap-1.5">
                  <span>
                    {t('opsAnalysis.canvasDraft.history')}
                    {!historyLoading ? ` (${history.length})` : ''}
                  </span>
                  {historyLoading ? (
                    <LoadingOutlined className="text-[12px] text-[var(--color-text-3)]" />
                  ) : null}
                </span>
              ),
              onClick: () => {
                openHistory();
              },
            },
          ],
        }}
      >
        <Button
          type="text"
          className="mr-1! px-0! text-[var(--color-text-1)]!"
          loading={savingFrame}
        >
          {t('opsAnalysis.canvasDraft.menu')}
          {!savingFrame ? (
            <DownOutlined className="ml-0! text-[10px]! text-[var(--color-text-3)]!" />
          ) : null}
        </Button>
      </Dropdown>

      <Modal
        title={t('opsAnalysis.canvasDraft.history')}
        open={historyOpen}
        centered
        width={630}
        onCancel={() => {
          cancelEdit();
          setHistoryOpen(false);
        }}
        footer={
          <Button
            onClick={() => {
              cancelEdit();
              setHistoryOpen(false);
            }}
          >
            {t('common.close')}
          </Button>
        }
        styles={{
          body: {
            maxHeight: 'min(480px, calc(100vh - 280px))',
            overflow: 'hidden',
            paddingTop: 4,
            display: 'flex',
            flexDirection: 'column',
          },
        }}
      >
        {historyLoading ? (
          <div className="flex justify-center py-10">
            <Spin />
          </div>
        ) : history.length === 0 ? (
          <Empty
            image={Empty.PRESENTED_IMAGE_SIMPLE}
            description={t('opsAnalysis.canvasDraft.historyEmpty')}
          />
        ) : (
          <div className="flex min-h-0 flex-1 flex-col">
            <div className="grid shrink-0 grid-cols-[44px_minmax(0,200px)_148px_96px] items-center gap-x-4 border-b border-[var(--color-border-2)] bg-[var(--color-bg-1)] px-2 pb-2 pt-2 text-[12px] leading-none text-[var(--color-text-3)]">
              <span>{t('opsAnalysis.canvasDraft.historyVersion')}</span>
              <span>{t('opsAnalysis.canvasDraft.historyName')}</span>
              <span>{t('opsAnalysis.canvasDraft.historyTime')}</span>
              <span>{t('opsAnalysis.canvasDraft.historyActions')}</span>
            </div>
            <div className="min-h-0 flex-1 overflow-y-auto">
              <ul className="m-0 list-none p-0">
                {history.map((item, index) => {
                  const versionNo = history.length - index;
                  const restoring = restoringId === item.id;
                  const editing = editingId === item.id;

                  return (
                    <li
                      key={item.id}
                      className="grid grid-cols-[44px_minmax(0,200px)_148px_96px] items-center gap-x-4 border-b border-[var(--color-border-2)] px-2 py-2.5 last:border-b-0"
                    >
                    <span className="text-[13px] font-medium leading-5 text-[var(--color-text-1)]">
                      #{versionNo}
                    </span>
                    <HistoryLabelCell
                      item={item}
                      editing={editing}
                      saving={savingLabelId === item.id}
                      draftLabel={draftLabel}
                      onDraftLabelChange={setDraftLabel}
                      onStartEdit={() => startEdit(item)}
                      onCommit={() => void commitEdit(item)}
                      onCancel={cancelEdit}
                    />
                    <time
                      dateTime={item.created_at}
                      className="whitespace-nowrap text-[13px] leading-5 tabular-nums text-[var(--color-text-3)]"
                    >
                      {formatFrameTime(item.created_at)}
                    </time>
                    <Space size={8} className="whitespace-nowrap">
                      <Button
                        type="link"
                        size="small"
                        className="h-auto! px-0! text-[13px]! leading-5!"
                        loading={restoring}
                        onClick={() => void restore(item.id)}
                      >
                        {t('opsAnalysis.canvasDraft.restore')}
                      </Button>
                      <Button
                        type="link"
                        size="small"
                        className="h-auto! px-0! text-[13px]! leading-5!"
                        onClick={() => setViewing(item)}
                      >
                        {t('opsAnalysis.canvasDraft.viewYaml')}
                      </Button>
                    </Space>
                  </li>
                );
              })}
              </ul>
            </div>
          </div>
        )}
      </Modal>

      <Modal
        title={
          viewing
            ? t('opsAnalysis.canvasDraft.frameYamlTitle', undefined, {
              name: frameDisplayTitle(viewing),
            })
            : undefined
        }
        open={!!viewing}
        centered
        width={640}
        onCancel={() => setViewing(null)}
        footer={
          <Space>
            <Button onClick={() => setViewing(null)}>{t('common.close')}</Button>
            <Button
              type="primary"
              loading={restoringId === viewing?.id}
              onClick={() => {
                if (viewing) void restore(viewing.id);
              }}
            >
              {t('opsAnalysis.canvasDraft.restoreFrame')}
            </Button>
          </Space>
        }
        styles={{
          body: { maxHeight: 'calc(100vh - 200px)', overflowY: 'auto' },
        }}
      >
        {viewing ? (
          <CodeSnippet
            value={viewing.yaml}
            copyable
            maxHeight="calc(100vh - 320px)"
          />
        ) : null}
      </Modal>
    </>
  );
};

export const bindCanvasDraftControls = (draft: CanvasDraftController) => (
  <CanvasDraftControls
    history={draft.history}
    savingFrame={draft.savingFrame}
    historyLoading={draft.historyLoading}
    onSaveFrame={draft.saveFrame}
    onRestore={draft.restoreFrame}
    onUpdateLabel={draft.updateFrameLabel}
  />
);

export default CanvasDraftControls;
