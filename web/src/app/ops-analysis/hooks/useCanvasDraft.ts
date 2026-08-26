'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { message } from 'antd';
import { useTranslation } from '@/utils/i18n';
import type { CanvasType } from '@/app/ops-analysis/constants/canvasTypes';
import {
  useCanvasDraftApi,
  type CanvasDraftHistoryItem,
  type CanvasDraftPayload,
} from '@/app/ops-analysis/api/canvasDraft';
import { HandledRequestError } from '@/utils/request';

const formatDraftValidationError = (error: unknown) => {
  if (!(error instanceof HandledRequestError)) return null;
  const payload = error.payload as
    | { data?: { errors?: Array<{ message?: string; field?: string }> } }
    | undefined;
  const errors = payload?.data?.errors;
  if (!Array.isArray(errors) || errors.length === 0) return null;
  return errors
    .slice(0, 3)
    .map((item) => {
      const messageText =
        typeof item?.message === 'string' ? item.message.trim() : '';
      if (!messageText) return '';
      return typeof item?.field === 'string' && item.field
        ? `${item.field}: ${messageText}`
        : messageText;
    })
    .filter(Boolean)
    .join('；');
};

const formatDraftRequestError = (error: unknown) => {
  const validation = formatDraftValidationError(error);
  if (validation) return validation;
  if (!(error instanceof HandledRequestError)) {
    return error instanceof Error ? error.message : null;
  }
  const payload = error.payload as { detail?: string } | undefined;
  if (typeof payload?.detail === 'string' && payload.detail.trim()) {
    return payload.detail.trim();
  }
  return null;
};

interface UseCanvasDraftOptions {
  resourceType: CanvasType;
  resourceId?: number;
  enabled: boolean;
  getPayload: () => CanvasDraftPayload;
  applyPayload: (payload: CanvasDraftPayload) => void;
}

export const useCanvasDraft = ({
  resourceType,
  resourceId,
  enabled,
  getPayload,
  applyPayload,
}: UseCanvasDraftOptions) => {
  const { t } = useTranslation();
  const api = useCanvasDraftApi();
  const apiRef = useRef(api);
  apiRef.current = api;
  const [history, setHistory] = useState<CanvasDraftHistoryItem[]>([]);
  const [savingFrame, setSavingFrame] = useState(false);
  const [historyLoading, setHistoryLoading] = useState(false);
  const getPayloadRef = useRef(getPayload);
  const applyPayloadRef = useRef(applyPayload);
  getPayloadRef.current = getPayload;
  applyPayloadRef.current = applyPayload;

  const refreshHistory = useCallback(async () => {
    if (!resourceId) return;
    const items = await apiRef.current.listHistory(resourceType, resourceId);
    setHistory(items);
  }, [resourceId, resourceType]);

  const loadHistory = useCallback(async () => {
    if (!resourceId) return;
    setHistoryLoading(true);
    try {
      await refreshHistory();
    } finally {
      setHistoryLoading(false);
    }
  }, [refreshHistory, resourceId]);

  useEffect(() => {
    if (!enabled || !resourceId) {
      setHistory([]);
      setHistoryLoading(false);
      return;
    }
    void loadHistory();
  }, [enabled, loadHistory, resourceId]);

  const saveFrame = useCallback(async () => {
    if (!resourceId || savingFrame) return;
    const payload = getPayloadRef.current();
    setSavingFrame(true);
    try {
      await apiRef.current.saveCheckpoint(resourceType, resourceId, payload);
      await refreshHistory();
      message.success(t('opsAnalysis.canvasDraft.saveFrameSuccess'));
    } catch (error) {
      const detail = formatDraftRequestError(error);
      message.error(
        detail
          ? `${t('opsAnalysis.canvasDraft.validationFailed')}: ${detail}`
          : t('opsAnalysis.canvasDraft.validationFailed'),
      );
    } finally {
      setSavingFrame(false);
    }
  }, [refreshHistory, resourceId, resourceType, savingFrame, t]);

  const restoreFrame = useCallback(
    async (checkpointId: number) => {
      if (!resourceId) return;
      try {
        const current = await apiRef.current.restoreCheckpoint(
          resourceType,
          resourceId,
          checkpointId,
        );
        applyPayloadRef.current(current.payload);
        message.success(t('opsAnalysis.canvasDraft.restoreSuccess'));
      } catch (error) {
        const detail = formatDraftRequestError(error);
        message.error(
          detail
            ? `${t('opsAnalysis.canvasDraft.restoreFailed')}: ${detail}`
            : t('opsAnalysis.canvasDraft.restoreFailed'),
        );
      }
    },
    [resourceId, resourceType, t],
  );

  const updateFrameLabel = useCallback(
    async (checkpointId: number, label: string) => {
      if (!resourceId) return;
      try {
        const updated = await apiRef.current.updateCheckpointLabel(
          resourceType,
          resourceId,
          checkpointId,
          label,
        );
        setHistory((items) =>
          items.map((item) =>
            item.id === checkpointId ? { ...item, label: updated.label } : item,
          ),
        );
      } catch (error) {
        const detail = formatDraftRequestError(error);
        message.error(
          detail ?? t('opsAnalysis.canvasDraft.updateLabelFailed'),
        );
        throw error;
      }
    },
    [resourceId, resourceType, t],
  );

  return {
    history,
    savingFrame,
    historyLoading,
    saveFrame,
    restoreFrame,
    updateFrameLabel,
  };
};

export type CanvasDraftController = ReturnType<typeof useCanvasDraft>;
