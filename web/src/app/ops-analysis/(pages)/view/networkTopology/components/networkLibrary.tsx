import React, { useEffect, useMemo, useRef, useState } from "react";
import { Empty, Input, Spin, Button, Tooltip, Tag } from "antd";
import {
  ReloadOutlined,
  PlusOutlined,
  LeftOutlined,
  RightOutlined,
} from "@ant-design/icons";
import type {
  NetworkNodeLibraryItem,
  NetworkNodeModel,
} from "@/app/ops-analysis/types/networkTopology";
import { useTranslation } from "@/utils/i18n";
import { buildNetworkNodeClientId } from "../utils/networkTopologyUtils";

const MODEL_TAG_COLORS: Record<string, string> = {
  bk_switch: "cyan",
  bk_router: "blue",
  bk_firewall: "volcano",
  bk_loadbalance: "purple",
  bk_load_balancer: "purple",
};

export const getModelTagColor = (bkObjId: string) =>
  MODEL_TAG_COLORS[bkObjId] ?? "geekblue";

export interface NetworkLibraryProps {
  models: NetworkNodeModel[];
  nodes: NetworkNodeLibraryItem[];
  loading: boolean;
  error: string | null;
  modelFilter: string | undefined;
  keyword: string;
  onModelFilterChange: (bkObjId: string | undefined) => void;
  onKeywordChange: (value: string) => void;
  onReload: () => void;
  /** 拖拽开始时调用。父级不需要参数也能正常接入(dataTransfer 由本组件内部写入)。 */
  onDragStart?: () => void;
  onAddClick: (item: NetworkNodeLibraryItem) => void;
  disabled?: boolean;
  testId?: string;
  className?: string;
  /** 侧栏收起状态,父级用 useCollapsedState 管理。 */
  collapsed?: boolean;
  /** 父级传入的切换回调。 */
  onCollapsedChange?: (collapsed: boolean) => void;
}

/**
 * 左侧设备库(design.md §7.3):
 * - 模型下拉(可选)
 * - 关键字搜索(可选)
 * - 单源设备直接添加,多源添加时由父级弹 MonitorSourcePickerModal
 * - 侧栏支持收起/展开(参考 topology/components/nodeSidebar.tsx)
 */
const NetworkLibrary: React.FC<NetworkLibraryProps> = ({
  models,
  nodes,
  loading,
  error,
  modelFilter,
  keyword,
  onModelFilterChange,
  onKeywordChange,
  onReload,
  onDragStart,
  onAddClick,
  disabled = false,
  testId,
  className,
  collapsed = false,
  onCollapsedChange,
}) => {
  const { t } = useTranslation();
  const [keywordDraft, setKeywordDraft] = useState(keyword);
  const nodeCount = nodes?.length ?? 0;
  const modelNameById = useMemo(() => {
    const map = new Map<string, string>();
    models.forEach((model) => map.set(model.bk_obj_id, model.display_name));
    return map;
  }, [models]);
  const handleToggleCollapsed = () => onCollapsedChange?.(!collapsed);

  // 编辑/只读切换时自动同步侧栏状态(参考 topology/components/nodeSidebar):
  // - 切到只读(disabled=true): 收起
  // - 切到编辑(disabled=false): 展开
  // 只在 disabled 真变的时候才同步 —— 如果把 collapsed 也放进依赖,
  // 用户点按钮收起后 effect 会立刻跑,又把它强制展开(死循环)。
  const prevDisabledRef = useRef(disabled);
  useEffect(() => {
    if (prevDisabledRef.current !== disabled) {
      prevDisabledRef.current = disabled;
      onCollapsedChange?.(disabled);
    }
  }, [disabled, onCollapsedChange]);

  return (
    <>
      <section
        className={`relative shrink-0 transition-[width] duration-300 ${
          collapsed ? "w-0" : "w-72"
        } ${className ?? ""}`}
        data-testid={testId ?? "network-library"}
        aria-hidden={collapsed}
      >
        <Button
          type="text"
          icon={collapsed ? <RightOutlined /> : <LeftOutlined />}
          onClick={handleToggleCollapsed}
          className="absolute top-5 z-10 rounded-full border border-[var(--color-border-1)] bg-[var(--color-bg-1)] shadow-sm hover:bg-[var(--color-fill-2)] hover:shadow-md"
          style={{
            width: 24,
            height: 24,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            padding: 0,
            right: collapsed ? "-12px" : "-12px",
            borderRadius: collapsed ? "0 50% 50% 0" : "50%",
          }}
          data-testid="network-library-collapse-toggle"
          aria-label={collapsed ? "expand" : "collapse"}
        />
        {!collapsed && (
          <div className="h-full w-72 overflow-hidden border-r border-[var(--color-border-1)]">
            <div className="flex h-full flex-col gap-2 overflow-auto p-3">
              <div className="flex items-center gap-2">
                <strong className="flex-1 text-[13px] font-semibold text-[var(--color-text-1)]">
                  {t("opsAnalysis.networkTopology.library.title")}
                </strong>
                <Tooltip
                  title={t(
                    "opsAnalysis.networkTopology.library.refreshTooltip",
                  )}
                >
                  <Button
                    size="small"
                    icon={<ReloadOutlined />}
                    onClick={onReload}
                    data-testid="network-library-refresh"
                  />
                </Tooltip>
              </div>
              <Input.Search
                size="small"
                allowClear
                placeholder={t(
                  "opsAnalysis.networkTopology.library.keywordPlaceholder",
                )}
                value={keywordDraft}
                onChange={(e) => {
                  setKeywordDraft(e.target.value);
                  onKeywordChange(e.target.value);
                }}
                onSearch={(v) => onKeywordChange(v)}
                data-testid="network-library-keyword"
              />
              {/* 设备类型筛选 chip(参考 spec HTML .filter-chips)。
                用 inline style + CSS 变量保证选中态视觉明显:
                - 选中:实色蓝底白字
                - 未选中:浅灰底深字 + hover 加深
                不用 Tailwind 任意值类,避免 JIT 漏掉 hex 色。 */}
              <div
                className="mt-1 flex flex-wrap gap-1.5"
                data-testid="network-library-model-filter"
              >
                <span
                  role="button"
                  tabIndex={0}
                  onClick={() => onModelFilterChange(undefined)}
                  className="cursor-pointer rounded-full border px-2.5 py-0.5 text-[11px] transition-colors"
                  style={
                    !modelFilter
                      ? {
                        backgroundColor: "#1d4ed8",
                        borderColor: "#1d4ed8",
                        color: "#ffffff",
                      }
                      : {
                        backgroundColor: "#f1f5f9",
                        borderColor: "transparent",
                        color: "#475569",
                      }
                  }
                >
                  {t("opsAnalysis.networkTopology.library.allModels")}
                </span>
                {models.map((m) => {
                  const active = modelFilter === m.bk_obj_id;
                  return (
                    <span
                      key={m.bk_obj_id}
                      role="button"
                      tabIndex={0}
                      onClick={() =>
                        onModelFilterChange(active ? undefined : m.bk_obj_id)
                      }
                      className="cursor-pointer rounded-full border px-2.5 py-0.5 text-[11px] transition-colors"
                      style={
                        active
                          ? {
                            backgroundColor: "#1d4ed8",
                            borderColor: "#1d4ed8",
                            color: "#ffffff",
                          }
                          : {
                            backgroundColor: "#f1f5f9",
                            borderColor: "transparent",
                            color: "#475569",
                          }
                      }
                    >
                      {m.display_name}
                    </span>
                  );
                })}
              </div>
              {loading ? (
                <div className="flex justify-center p-6">
                  <Spin />
                </div>
              ) : error ? (
                <Empty
                  image={Empty.PRESENTED_IMAGE_SIMPLE}
                  description={error}
                  data-testid="network-library-error"
                />
              ) : nodeCount === 0 ? (
                <Empty
                  image={Empty.PRESENTED_IMAGE_SIMPLE}
                  description={t("opsAnalysis.networkTopology.library.empty")}
                  data-testid="network-library-empty"
                />
              ) : (
                <div className="flex flex-col gap-2">
                  {(nodes ?? []).map((item) => (
                    <div
                      key={buildNetworkNodeClientId(item)}
                      draggable={!disabled}
                      onDragStart={(event) => {
                        if (disabled) return;
                        event.dataTransfer.setData(
                          "application/json",
                          JSON.stringify(item),
                        );
                        event.dataTransfer.effectAllowed = "copy";
                        onDragStart?.();
                      }}
                      className={`rounded border border-[var(--color-border-1)] bg-white px-3 py-2.5 transition-colors ${
                        disabled
                          ? "cursor-not-allowed opacity-60"
                          : "cursor-grab hover:border-[var(--color-border-2)] hover:bg-[var(--color-fill-2)] active:cursor-grabbing"
                      }`}
                      data-testid="network-library-item"
                    >
                      <div className="flex items-start gap-2">
                        <div className="min-w-0 flex-1">
                          <div className="flex min-w-0 items-center">
                            <span className="min-w-0 flex-1 truncate text-[12px] font-semibold text-[var(--color-text-1)]">
                              {item.bk_inst_name}
                            </span>
                          </div>
                          <div className="mt-1 flex min-w-0 items-center gap-1.5">
                            <span className="min-w-0 truncate text-[11px] text-[var(--color-text-3)]">
                              {item.ip_addr || item.bk_obj_id}
                            </span>
                            <Tag
                              bordered={false}
                              color={getModelTagColor(item.bk_obj_id)}
                              style={{
                                marginInlineEnd: 0,
                                maxWidth: 64,
                                height: 18,
                                lineHeight: "18px",
                                paddingInline: 6,
                                fontSize: 11,
                              }}
                              className="shrink-0 truncate"
                            >
                              {modelNameById.get(item.bk_obj_id) ??
                                item.bk_obj_id}
                            </Tag>
                          </div>
                        </div>
                        <Button
                          size="small"
                          type="text"
                          icon={<PlusOutlined />}
                          disabled={disabled}
                          onClick={(event) => {
                            event.stopPropagation();
                            onAddClick(item);
                          }}
                          data-testid="network-library-add"
                        >
                          {t("opsAnalysis.networkTopology.library.add")}
                        </Button>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        )}
      </section>
    </>
  );
};

export default NetworkLibrary;
