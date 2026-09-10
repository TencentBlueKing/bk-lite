"use client";

import { useEffect, useState } from "react";
import { Alert, Modal } from "antd";
import { FolderOutlined } from "@ant-design/icons";
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
      width={480}
      okText={t("wiki.confirmMove")}
      cancelText={t("common.cancel")}
      okButtonProps={{ disabled: targetDirectoryId === undefined }}
      confirmLoading={loading}
      maskClosable={!loading}
      closable={!loading}
      onCancel={onCancel}
      onOk={handleConfirm}
      destroyOnClose
    >
      <div className="flex flex-col gap-4 pt-1 pb-2">
        <div className="flex items-center gap-2 rounded-md bg-[var(--color-fill-1)] px-3.5 py-2.5 text-xs text-[var(--color-text-2)]">
          <FolderOutlined className="text-[var(--color-primary)] text-sm" />
          <span>
            {t("wiki.movePagesSelected").replace("{count}", String(pageCount))}
          </span>
        </div>

        <div className="flex flex-col gap-2">
          <label className="text-xs font-medium text-[var(--color-text-2)]">
            <span className="text-red-500 mr-1">*</span>
            {t("wiki.selectTargetDirectory")}
          </label>
          <WikiDirectorySelect
            value={targetDirectoryId}
            directories={directories}
            placeholder={t("wiki.selectTargetDirectory")}
            onChange={setTargetDirectoryId}
            allowClear
          />
        </div>

        <div className="mt-1">
          <Alert
            type="info"
            showIcon
            message={
              <span className="text-xs leading-5">
                {t("wiki.manualDirectoryLockTip")}
              </span>
            }
          />
        </div>
      </div>
    </Modal>
  );
};

export default WikiPageMoveModal;
