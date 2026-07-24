import { useCallback, useState } from 'react';
import { ActionSheet, Dialog, Toast } from 'antd-mobile';
import { deleteSessionHistory } from '@/api/bot';
import { useConversationManager, useRunningSessionIds } from '@/context/conversation';
import type { SessionItem } from '@/types/conversation';
import { useTranslation } from '@/utils/i18n';

interface UseSessionDeletionOptions {
  fallbackNodeId?: string;
  onDeleted: (session: SessionItem) => void | Promise<void>;
}

export function useSessionDeletion({ fallbackNodeId, onDeleted }: UseSessionDeletionOptions) {
  const { t } = useTranslation();
  const { manager: conversationManager } = useConversationManager();
  const runningSessionIds = useRunningSessionIds();
  const [deletingSessionId, setDeletingSessionId] = useState<string | null>(null);

  const isSessionRunning = useCallback(
    (sessionId: string) => runningSessionIds.includes(sessionId),
    [runningSessionIds],
  );

  const confirmDeleteSession = useCallback((session: SessionItem) => {
    const nodeId = session.node_id || fallbackNodeId;
    if (!nodeId || deletingSessionId) return;
    if (isSessionRunning(session.session_id)) {
      Toast.show({ content: t('chat.deleteRunningConversation'), icon: 'fail' });
      return;
    }

    Dialog.confirm({
      title: t('chat.deleteConversation'),
      content: t('chat.deleteConversationConfirm'),
      confirmText: t('common.delete'),
      cancelText: t('common.cancel'),
      onConfirm: async () => {
        setDeletingSessionId(session.session_id);
        try {
          const response = await deleteSessionHistory(nodeId, session.session_id);
          if (!response.result) {
            throw new Error(response.message || 'Failed to delete session');
          }

          await onDeleted(session);
          conversationManager.clearSession(session.session_id);
          Toast.show({ content: t('chat.deleteConversationSuccess'), icon: 'success' });
        } catch (error) {
          console.error('deleteSessionHistory error:', error);
          Toast.show({ content: t('chat.deleteConversationFailed'), icon: 'fail' });
        } finally {
          setDeletingSessionId(null);
        }
      },
    });
  }, [conversationManager, deletingSessionId, fallbackNodeId, isSessionRunning, onDeleted, t]);

  const openSessionActions = useCallback((session: SessionItem) => {
    ActionSheet.show({
      actions: [{
        key: 'delete',
        text: t('chat.deleteConversation'),
        danger: true,
        onClick: () => confirmDeleteSession(session),
      }],
      cancelText: t('common.cancel'),
      closeOnAction: true,
      safeArea: true,
    });
  }, [confirmDeleteSession, t]);

  return {
    confirmDeleteSession,
    deletingSessionId,
    isSessionRunning,
    openSessionActions,
  };
}
