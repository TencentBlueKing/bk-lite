import React from 'react';
import { Modal } from 'antd';
import { useTranslation } from '@/utils/i18n';

export interface ConfirmDeleteModalProps {
  open: boolean;
  title?: string;
  /** 自定义确认按钮文案。 */
  okText?: string;
  cancelText?: string;
  /** 删除对象的可视化描述,例如「节点 core-sw-A」「连线 core-sw-A → agg-sw-B」。 */
  target?: string;
  /** 自定义内容,当 target 不够直观时使用。 */
  content?: React.ReactNode;
  loading?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
  zIndex?: number;
  testId?: string;
}

/**
 * 通用删除二次确认(design.md §3.2):
 * 节点和连线共用,文案简短:「确定要删除该节点吗?」「确定要删除该连线吗?」
 * 不展示级联内容,避免界面信息过载。
 */
const ConfirmDeleteModal: React.FC<ConfirmDeleteModalProps> = ({
  open,
  title,
  okText,
  cancelText,
  target,
  content,
  loading = false,
  onConfirm,
  onCancel,
  zIndex,
  testId,
}) => {
  const { t } = useTranslation();
  const resolvedTitle = title ?? t('opsAnalysis.networkTopology.deleteModal.title');
  const resolvedOkText = okText ?? t('opsAnalysis.networkTopology.actions.delete');
  const resolvedCancelText = cancelText ?? t('opsAnalysis.networkTopology.actions.cancel');

  return (
    <Modal
      title={resolvedTitle}
      open={open}
      onOk={onConfirm}
      onCancel={onCancel}
      okText={resolvedOkText}
      cancelText={resolvedCancelText}
      okButtonProps={{ danger: true, loading }}
      centered
      destroyOnClose
      maskClosable={false}
      zIndex={zIndex}
      data-testid={testId}
    >
      {content ?? (
        <span>
          {target ? (
            <strong>
              {t('opsAnalysis.networkTopology.deleteModal.confirmPrompt', undefined, {
                target: `「${target}」`,
              })}
            </strong>
          ) : (
            t('opsAnalysis.networkTopology.deleteModal.confirmPrompt', undefined, {
              target: t('opsAnalysis.networkTopology.deleteModal.defaultTarget'),
            })
          )}
        </span>
      )}
    </Modal>
  );
};

export default ConfirmDeleteModal;
