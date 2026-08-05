"use client";

import { useEffect, useState } from "react";
import { Alert, Modal } from "antd";
import { useTranslation } from "@/utils/i18n";
import type { WikiDirectoryNode } from "@/app/opspilot/types/wiki";
import WikiDirectorySelect from "./WikiDirectorySelect";

interface WikiPageMoveModalProps {
  open: boolean;
  loading: boolean;
  pageCount: number;
  directories: WikiDirectoryNode[];
  onCancel: () => void;
  onConfirm: (directoryId: number) => void | Promise<void>;
}

const WikiPageMoveModal = ({
  open,
  loading,
  pageCount,
  directories,
  onCancel,
  onConfirm,
}: WikiPageMoveModalProps) => {
  const { t } = useTranslation();
  const [targetDirectoryId, setTargetDirectoryId] = useState<number>();

  useEffect(() => {
    if (!open) setTargetDirectoryId(undefined);
  }, [open]);

  const handleConfirm = async () => {
    if (targetDirectoryId === undefined) return;
    await onConfirm(targetDirectoryId);
  };

  return (
    <Modal
      title={t("wiki.movePages")}
      open={open}
      okText={t("wiki.confirmMove")}
      cancelText={t("common.cancel")}
      okButtonProps={{ disabled: targetDirectoryId === undefined }}
      confirmLoading={loading}
      maskClosable={!loading}
      closable={!loading}
      onCancel={onCancel}
      onOk={handleConfirm}
    >
      <div className="space-y-4 py-2">
        <div className="text-sm text-[var(--color-text-2)]">
          {t("wiki.movePagesSelected").replace("{count}", String(pageCount))}
        </div>
        <WikiDirectorySelect
          value={targetDirectoryId}
          directories={directories}
          placeholder={t("wiki.selectTargetDirectory")}
          onChange={setTargetDirectoryId}
        />
        <Alert
          type="info"
          showIcon
          message={t("wiki.manualDirectoryLockTip")}
        />
      </div>
    </Modal>
  );
};

export default WikiPageMoveModal;
