"use client";

import CompactEmptyState from "@/components/compact-empty-state";
import MarkdownRenderer from "@/components/markdown";
import { useWikiApi } from "@/app/opspilot/api/wiki";
import { pickWikiMaterialSourceBody } from "@/app/opspilot/utils/wikiMaterialDisplay";
import { useTranslation } from "@/utils/i18n";
import { Spin, Typography } from "antd";
import React, { useEffect, useState } from "react";

interface WikiMaterialSourcePaneProps {
  materialId: number | null;
}

const WikiMaterialSourcePane: React.FC<WikiMaterialSourcePaneProps> = ({
  materialId,
}) => {
  const { t } = useTranslation();
  const { fetchMaterialInfo } = useWikiApi();
  const [loading, setLoading] = useState(false);
  const [title, setTitle] = useState("");
  const [body, setBody] = useState("");

  useEffect(() => {
    if (!materialId) {
      setTitle("");
      setBody("");
      return;
    }

    let active = true;
    setLoading(true);
    void fetchMaterialInfo(materialId)
      .then((info) => {
        if (!active) return;
        setTitle(info.material.name);
        setBody(
          pickWikiMaterialSourceBody(
            info.parsed_markdown,
            info.original,
            info.material.text_content,
          ),
        );
      })
      .catch(() => {
        if (!active) return;
        setTitle("");
        setBody("");
      })
      .finally(() => {
        if (active) setLoading(false);
      });

    return () => {
      active = false;
    };
  }, [materialId]);

  if (!materialId) {
    return (
      <div className="flex h-full min-h-0 flex-1 items-center justify-center">
        <CompactEmptyState description={t("wiki.materialSourceBodyEmpty")} />
      </div>
    );
  }

  if (loading && !title && !body) {
    return (
      <div className="flex h-full min-h-0 flex-1 items-center justify-center">
        <Spin />
      </div>
    );
  }

  return (
    <div className="relative flex h-full min-h-0 flex-1 flex-col overflow-hidden">
      <Spin
        spinning={loading}
        wrapperClassName="flex h-full min-h-0 flex-col [&_.ant-spin-container]:flex [&_.ant-spin-container]:h-full [&_.ant-spin-container]:min-h-0 [&_.ant-spin-container]:flex-col"
      >
        <div className="min-h-0 flex-1 overflow-y-auto p-4">
          <Typography.Title level={4} className="!mb-4 !text-base">
            {title || "--"}
          </Typography.Title>
          {body ? (
            <div className="min-w-0 max-w-full overflow-x-auto text-sm">
              <MarkdownRenderer content={body} />
            </div>
          ) : (
            <CompactEmptyState description={t("wiki.materialSourceBodyEmpty")} />
          )}
        </div>
      </Spin>
    </div>
  );
};

export default WikiMaterialSourcePane;
