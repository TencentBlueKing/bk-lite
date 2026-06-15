import { useCallback } from 'react';
import { Modal } from 'antd';
import { useTranslation } from '@/utils/i18n';

type Dirty = boolean | (() => boolean);

/**
 * 表单弹框「未保存二次确认」复用 hook。
 *
 * 返回一个 guard 函数：在执行真正的关闭动作前，先判断表单是否被改动过（dirty）。
 * - 未改动：直接关闭，零打扰。
 * - 已改动：弹 Modal.confirm 让用户确认是否放弃修改，确认后才关闭。
 *
 * 搭配弹框上的 `maskClosable={false}` 一起使用：
 * 点击遮罩外部不再直接关闭，X / 取消 / ESC 等主动关闭路径走本 guard。
 *
 * @example
 * const guardClose = useUnsavedConfirm();
 * <Drawer
 *   maskClosable={false}
 *   onClose={() => guardClose(form.isFieldsTouched(), onClose)}
 * />
 */
export const useUnsavedConfirm = () => {
  const { t } = useTranslation();

  return useCallback(
    (isDirty: Dirty, onConfirm: () => void) => {
      const dirty = typeof isDirty === 'function' ? isDirty() : isDirty;
      if (!dirty) {
        onConfirm();
        return;
      }
      Modal.confirm({
        title: t('common.unsavedTitle'),
        content: t('common.unsavedContent'),
        okText: t('common.discardChanges'),
        cancelText: t('common.continueEditing'),
        okButtonProps: { danger: true },
        centered: true,
        onOk: onConfirm,
      });
    },
    [t]
  );
};

export default useUnsavedConfirm;
