"use client";

import React, { useEffect, useState } from "react";
import { Form, Input, Modal, Select } from "antd";
import { useTranslation } from "@/utils/i18n";
import GroupTreeSelect from "@/components/group-tree-select";
import { useWikiApi } from "@/app/opspilot/api/wiki";
import { WikiKnowledgeBase } from "@/app/opspilot/types/wiki";
import { LlmModel } from "@/app/opspilot/types/skill";
import { Model } from "@/app/opspilot/types/provider";
import {
  getModelOptionText,
  renderModelOptionLabel,
} from "@/app/opspilot/utils/modelOption";

interface WikiModifyModalProps {
  visible: boolean;
  onCancel: () => void;
  onConfirm: (values: Record<string, unknown>) => void;
  initialValues?: WikiKnowledgeBase | null;
}

const WikiModifyModal: React.FC<WikiModifyModalProps> = ({
  visible,
  onCancel,
  onConfirm,
  initialValues,
}) => {
  const { t } = useTranslation();
  const [form] = Form.useForm();
  const { fetchKnowledgeBase, fetchLlmModels, fetchEmbedProviders } =
    useWikiApi();
  const [llmModels, setLlmModels] = useState<LlmModel[]>([]);
  const [embedProviders, setEmbedProviders] = useState<Model[]>([]);
  const [confirmLoading, setConfirmLoading] = useState(false);

  useEffect(() => {
    if (!visible) return;
    fetchLlmModels()
      .then((models) => setLlmModels(models || []))
      .catch(() => undefined);
    fetchEmbedProviders()
      .then((models) => setEmbedProviders(models || []))
      .catch(() => undefined);
    if (initialValues?.id) {
      form.resetFields();
      fetchKnowledgeBase(initialValues.id)
        .then((full) => {
          form.setFieldsValue({
            name: full.name,
            introduction: full.introduction,
            team: full.team,
            llm_model: full.llm_model,
            embed_provider: full.embed_provider,
            vision_model: full.vision_model,
          });
        })
        .catch(() => undefined);
    } else {
      form.resetFields();
    }
  }, [visible, initialValues]);

  const handleOk = async () => {
    const values = await form.validateFields();
    const submitValues = {
      ...values,
      embed_provider: values.embed_provider ?? null,
    };
    setConfirmLoading(true);
    try {
      await onConfirm(submitValues);
    } finally {
      setConfirmLoading(false);
    }
  };

  return (
    <Modal
      title={initialValues ? t("wiki.edit") : t("wiki.create")}
      open={visible}
      onOk={handleOk}
      confirmLoading={confirmLoading}
      onCancel={onCancel}
      maskClosable={false}
      width={640}
      destroyOnHidden
      styles={{
        body: {
          maxHeight: "calc(100vh - 240px)",
          overflowY: "auto",
          overflowX: "hidden",
        },
      }}
    >
      <Form form={form} layout="vertical">
        <Form.Item
          label={t("wiki.name")}
          name="name"
          rules={[{ required: true }]}
        >
          <Input />
        </Form.Item>
        <Form.Item
          label={t("common.organization")}
          name="team"
          rules={[
            {
              required: true,
              message: `${t("common.selectMsg")}${t("common.organization")}`,
            },
          ]}
        >
          <GroupTreeSelect
            placeholder={`${t("common.selectMsg")}${t("common.organization")}`}
          />
        </Form.Item>
        <Form.Item
          label={t("wiki.llmModel")}
          name="llm_model"
          rules={[
            {
              required: true,
              message: `${t("common.selectMsg")}${t("wiki.llmModel")}`,
            },
          ]}
          tooltip={t("wiki.llmModelTip")}
        >
          <Select
            placeholder={t("wiki.llmModelPlaceholder")}
            optionFilterProp="title"
            options={llmModels.map((m) => ({
              value: m.id,
              label: renderModelOptionLabel(m),
              title: getModelOptionText(m),
              disabled: !m.enabled,
            }))}
          />
        </Form.Item>
        <Form.Item
          label={t("wiki.embedProvider")}
          name="embed_provider"
          tooltip={t("wiki.embedProviderTip")}
        >
          <Select
            allowClear
            placeholder={t("wiki.embedProviderPlaceholder")}
            optionFilterProp="title"
            options={embedProviders.map((m) => ({
              value: m.id,
              label: renderModelOptionLabel(m),
              title: getModelOptionText(m),
              disabled: !m.enabled,
            }))}
          />
        </Form.Item>
        <Form.Item
          label={t("wiki.visionModel")}
          name="vision_model"
          tooltip={t("wiki.visionModelTip")}
        >
          <Select
            allowClear
            placeholder={t("wiki.visionModelPlaceholder")}
            optionFilterProp="title"
            options={llmModels.map((m) => ({
              value: m.id,
              label: renderModelOptionLabel(m),
              title: getModelOptionText(m),
              disabled: !m.enabled,
            }))}
          />
        </Form.Item>
        <Form.Item
          label={t("wiki.introduction")}
          name="introduction"
          rules={[
            {
              required: true,
              whitespace: true,
              message: t("wiki.introductionRequired"),
            },
          ]}
        >
          <Input.TextArea rows={4} />
        </Form.Item>
      </Form>
    </Modal>
  );
};

export default WikiModifyModal;
