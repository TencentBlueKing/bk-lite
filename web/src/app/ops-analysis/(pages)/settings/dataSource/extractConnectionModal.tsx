"use client";

import React from "react";
import { Form, Input, Modal } from "antd";
import type { FormInstance } from "antd/es/form";
import { useTranslation } from "@/utils/i18n";

interface ExtractConnectionModalProps {
  open: boolean;
  loading: boolean;
  form: FormInstance;
  onCancel: () => void;
  onOk: () => void;
}

export const ExtractConnectionModal: React.FC<ExtractConnectionModalProps> = ({
  open,
  loading,
  form,
  onCancel,
  onOk,
}) => {
  const { t } = useTranslation();

  return (
    <Modal
      title={t("dataConnection.extractConnectionTitle")}
      open={open}
      centered
      confirmLoading={loading}
      okText={t("common.confirm")}
      cancelText={t("common.cancel")}
      onCancel={onCancel}
      onOk={onOk}
      destroyOnClose
    >
      <Form form={form} layout="vertical" className="pt-2">
        <Form.Item
          name="name"
          label={t("dataConnection.name")}
          rules={[{ required: true, message: t("common.inputMsg") }]}
        >
          <Input placeholder={t("common.inputMsg")} maxLength={128} />
        </Form.Item>
        <Form.Item name="description" label={t("dataConnection.describe")}>
          <Input.TextArea
            rows={3}
            placeholder={t("common.inputMsg")}
            maxLength={512}
          />
        </Form.Item>
      </Form>
    </Modal>
  );
};
