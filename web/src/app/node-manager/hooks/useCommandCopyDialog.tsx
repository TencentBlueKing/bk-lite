'use client';

import { useCallback, useReducer } from 'react';
import { Alert, Button, Modal } from 'antd';
import {
  CheckCircleFilled,
  CloseCircleFilled,
} from '@ant-design/icons';
import { useTranslation } from '@/utils/i18n';
import {
  ClipboardCopyError,
  copyText,
  type ClipboardCopyFailureReason,
} from '@/app/node-manager/utils/clipboard';

export interface CommandCopyState {
  open: boolean;
  copying: boolean;
  content: string;
  status: 'success' | 'error' | null;
  reason: ClipboardCopyFailureReason | null;
}

type CommandCopyAction =
  | { type: 'copying'; content: string }
  | { type: 'success' }
  | {
      type: 'failure';
      reason: ClipboardCopyFailureReason;
      content?: string;
    }
  | { type: 'close' };

export const commandCopyInitialState: CommandCopyState = {
  open: false,
  copying: false,
  content: '',
  status: null,
  reason: null,
};

export const commandCopyReducer = (
  state: CommandCopyState,
  action: CommandCopyAction
): CommandCopyState => {
  switch (action.type) {
    case 'copying':
      return {
        ...state,
        copying: true,
        content: action.content,
        reason: null,
      };
    case 'success':
      return {
        ...state,
        open: true,
        copying: false,
        status: 'success',
        reason: null,
      };
    case 'failure':
      return {
        ...state,
        open: true,
        copying: false,
        content: action.content ?? state.content,
        status: 'error',
        reason: action.reason,
      };
    case 'close':
      return commandCopyInitialState;
    default:
      return state;
  }
};

const useCommandCopyDialog = () => {
  const { t } = useTranslation();
  const [state, dispatch] = useReducer(
    commandCopyReducer,
    commandCopyInitialState
  );

  const copyCommand = useCallback(async (value: string): Promise<boolean> => {
    dispatch({ type: 'copying', content: value });
    if (!value.trim()) {
      dispatch({ type: 'failure', reason: 'empty', content: value });
      return false;
    }

    try {
      await copyText(value);
      dispatch({ type: 'success' });
      return true;
    } catch (error) {
      dispatch({
        type: 'failure',
        reason:
          error instanceof ClipboardCopyError ? error.reason : 'failed',
      });
      return false;
    }
  }, []);

  const close = useCallback(() => {
    dispatch({ type: 'close' });
  }, []);

  const isSuccess = state.status === 'success';
  const isEmpty = state.reason === 'empty';
  const title = isSuccess
    ? t('node-manager.cloudregion.node.commandCopySuccessTitle')
    : t('node-manager.cloudregion.node.commandCopyFailedTitle');
  const description = isSuccess
    ? t('node-manager.cloudregion.node.commandCopySuccessDesc')
    : t(
        `node-manager.cloudregion.node.${
          isEmpty ? 'commandCopyEmptyDesc' : 'commandCopyFailedDesc'
        }`
    );

  const commandCopyDialog = (
    <Modal
      open={state.open}
      width={680}
      title={
        <div className="flex items-center gap-[8px]">
          {isSuccess ? (
            <CheckCircleFilled className="text-[var(--color-success)]" />
          ) : (
            <CloseCircleFilled className="text-[var(--color-fail)]" />
          )}
          <span>{title}</span>
        </div>
      }
      focusTriggerAfterClose
      onCancel={close}
      footer={[
        !isEmpty && (
          <Button
            key="copy"
            loading={state.copying}
            onClick={() => void copyCommand(state.content)}
          >
            {t(
              `node-manager.cloudregion.node.${
                isSuccess ? 'copyAgain' : 'retryCopy'
              }`
            )}
          </Button>
        ),
        <Button key="close" type="primary" onClick={close}>
          {t('node-manager.cloudregion.node.gotIt')}
        </Button>,
      ]}
    >
      <Alert
        type={isSuccess ? 'success' : 'error'}
        description={description}
        showIcon
      />
      {!isEmpty && (
        <>
          <div className="mt-[16px] text-[12px] text-[var(--color-text-3)]">
            {t('node-manager.cloudregion.node.copiedOriginal')}
          </div>
          <pre className="mt-[8px] max-h-[240px] overflow-auto whitespace-pre rounded-[6px] bg-[var(--color-fill-1)] p-[12px] font-mono text-[12px] text-[var(--color-text-1)]">
            {state.content}
          </pre>
        </>
      )}
    </Modal>
  );

  return {
    copyCommand,
    commandCopyDialog,
    copying: state.copying,
  };
};

export default useCommandCopyDialog;
