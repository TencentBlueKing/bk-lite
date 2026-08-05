"use client";

import React, { useEffect, useRef, useState } from "react";
import {
  Alert,
  AutoComplete,
  Button,
  Drawer,
  Form,
  Input,
  List,
  Select,
  Space,
  Tag,
  message,
} from "antd";
import { useWikiApi } from "@/app/opspilot/api/wiki";
import type { KnowledgePage, PageVersion } from "@/app/opspilot/types/wiki";
import { useTranslation } from "@/utils/i18n";

interface WikiPageEditorDrawerProps {
  kbId: number;
  open: boolean;
  page: KnowledgePage | null;
  typeOptions: Array<{ value: string }>;
  onClose: () => void;
  onPageChanged: (pageId?: number) => Promise<KnowledgePage | null>;
}

const isArchivedPage = (page: KnowledgePage) => page.status === "archived";

const diffColor = (line: string) =>
  line.startsWith("+")
    ? "#237804"
    : line.startsWith("-")
      ? "#a8071a"
      : "inherit";

const WikiPageEditorDrawer: React.FC<WikiPageEditorDrawerProps> = ({
  kbId,
  open,
  page,
  typeOptions,
  onClose,
  onPageChanged,
}) => {
  const { t } = useTranslation();
  const {
    createPage,
    updatePage,
    fetchPageVersions,
    restorePageVersion,
    fetchPageDiff,
  } = useWikiApi();
  const fetchPageVersionsRef = useRef(fetchPageVersions);
  fetchPageVersionsRef.current = fetchPageVersions;
  const [form] = Form.useForm();
  const [saving, setSaving] = useState(false);
  const [versions, setVersions] = useState<PageVersion[]>([]);
  const [diffLines, setDiffLines] = useState<string[]>([]);
  const [diffVersionId, setDiffVersionId] = useState<number | null>(null);
  const readOnly = !!page && isArchivedPage(page);
  const watchedTitle = Form.useWatch("title", form);
  const titleChanged =
    !!page &&
    !readOnly &&
    String(watchedTitle ?? "").trim() !== page.title.trim();

  useEffect(() => {
    if (!open) return;

    let active = true;
    setDiffLines([]);
    setDiffVersionId(null);
    if (!page) {
      form.resetFields();
      setVersions([]);
      return () => {
        active = false;
      };
    }

    form.setFieldsValue({
      page_type: page.page_type,
      title: page.title,
      tags: page.tags || [],
      body: page.body || "",
    });
    void fetchPageVersionsRef.current(page.id).then((result) => {
      if (active) setVersions(result);
    });
    return () => {
      active = false;
    };
  }, [form, open, page]);

  const save = async () => {
    if (readOnly) return;
    const values = await form.validateFields();
    setSaving(true);
    try {
      if (page) {
        await updatePage(page.id, {
          title: values.title,
          tags: values.tags || [],
          body: values.body || "",
        });
      } else {
        await createPage({
          knowledge_base: kbId,
          page_type: values.page_type,
          title: values.title,
          tags: values.tags || [],
          body: values.body || "",
        });
      }
      message.success(t("wiki.saveSuccess"));
      await onPageChanged(page?.id);
      onClose();
    } finally {
      setSaving(false);
    }
  };

  const showDiff = async (versionId: number) => {
    if (!page?.current_version) return;
    const result = await fetchPageDiff(
      page.id,
      versionId,
      page.current_version,
    );
    setDiffLines(result.diff);
    setDiffVersionId(versionId);
  };

  const restore = async (versionId: number) => {
    if (!page || readOnly) return;
    await restorePageVersion(page.id, versionId);
    message.success(t("wiki.saveSuccess"));
    const updated = await onPageChanged(page.id);
    if (updated) form.setFieldsValue({ body: updated.body || "" });
    setVersions(await fetchPageVersions(page.id));
    setDiffLines([]);
    setDiffVersionId(null);
  };
  const versionActions = (version: PageVersion): React.ReactNode[] => {
    if (version.is_current) {
      return [
        <Tag color="green" key="cur">
          {t("wiki.current")}
        </Tag>,
      ];
    }

    const actions: React.ReactNode[] = [
      <Button
        type="link"
        size="small"
        key="diff"
        onClick={() => showDiff(version.id)}
      >
        {t("wiki.diff")}
      </Button>,
    ];
    if (!readOnly) {
      actions.push(
        <Button
          type="link"
          size="small"
          key="restore"
          onClick={() => restore(version.id)}
        >
          {t("wiki.restore")}
        </Button>,
      );
    }
    return actions;
  };
  return (
    <Drawer
      title={
        readOnly
          ? t("wiki.viewPage")
          : page
            ? t("wiki.editPage")
            : t("wiki.newPage")
      }
      open={open}
      width={680}
      onClose={onClose}
      extra={
        readOnly ? null : (
          <Space>
            <Button onClick={onClose}>{t("common.cancel")}</Button>
            <Button type="primary" loading={saving} onClick={save}>
              {t("common.save")}
            </Button>
          </Space>
        )
      }
    >
      {readOnly && (
        <div className="mb-3 text-xs text-[var(--color-text-3)]">
          {t("wiki.archivedReadOnlyTip")}
        </div>
      )}
      <Form form={form} layout="vertical" disabled={readOnly}>
        <Form.Item
          label={t("wiki.type")}
          name="page_type"
          rules={[{ required: true, message: t("wiki.typeRequired") }]}
          tooltip={page ? t("wiki.typeLockedTip") : undefined}
        >
          <AutoComplete
            options={typeOptions}
            disabled={!!page || readOnly}
            placeholder={t("wiki.type")}
            filterOption={(input, option) =>
              String(option?.value ?? "")
                .toLowerCase()
                .includes(input.toLowerCase())
            }
          />
        </Form.Item>
        <Form.Item
          label={t("wiki.name")}
          name="title"
          rules={[{ required: true, message: t("wiki.titleRequired") }]}
        >
          <Input disabled={readOnly} />
        </Form.Item>
        {titleChanged && (
          <Alert
            showIcon
            type="warning"
            className="mb-4"
            message={t("wiki.renamePageWarningTitle")}
            description={t("wiki.renamePageWarningDesc")}
          />
        )}
        <Form.Item label={t("wiki.tags")} name="tags">
          <Select
            mode="tags"
            open={false}
            placeholder={t("wiki.tagsPlaceholder")}
            disabled={readOnly}
          />
        </Form.Item>
        <Form.Item label={t("wiki.body")} name="body">
          <Input.TextArea
            rows={12}
            placeholder={t("wiki.bodyPlaceholder")}
            disabled={readOnly}
          />
        </Form.Item>
      </Form>

      {page && (
        <div className="mt-2">
          <List
            header={t("wiki.versionHistory")}
            size="small"
            dataSource={versions}
            renderItem={(version) => (
              <List.Item actions={versionActions(version)}>
                {`v${version.no} · ${version.change_type}`}
              </List.Item>
            )}
          />
          {!!diffLines.length && (
            <div className="mt-3">
              <div className="mb-1 text-xs text-gray-500">
                {`v${versions.find((version) => version.id === diffVersionId)?.no ?? "?"} → current`}
              </div>
              <pre className="whitespace-pre-wrap text-xs">
                {diffLines.map((line, index) => (
                  <div key={index} style={{ color: diffColor(line) }}>
                    {line}
                  </div>
                ))}
              </pre>
            </div>
          )}
        </div>
      )}
    </Drawer>
  );
};

export default WikiPageEditorDrawer;
