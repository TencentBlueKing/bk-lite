"use client";

import {
  ArrowLeftOutlined,
} from "@ant-design/icons";
import { Tooltip } from "antd";
import Icon from "@/components/icon";
import type { LoginAuthBindingItem } from "./types";

interface LoginAuthValidationPanelProps {
  mode: "page" | "modal";
  bindings: LoginAuthBindingItem[];
  selectedBindingId: number | null;
  isSelectionLocked: boolean;
  onSelectBinding: (bindingId: number) => void;
}

export default function LoginAuthValidationPanel({
  mode,
  bindings,
  selectedBindingId,
  isSelectionLocked,
  onSelectBinding,
}: LoginAuthValidationPanelProps) {
  const isModalMode = mode === "modal";
  const containerClassName = isModalMode
    ? "inline-flex flex-wrap items-start justify-center gap-x-8"
    : "inline-flex flex-wrap items-start justify-center gap-x-6";

  return (
    <div className="space-y-3">
      {bindings.length > 0 && (
        <div className={containerClassName}>
          {bindings.map((binding) => {
            const isActive = binding.id === selectedBindingId;
            const isDisabled = isSelectionLocked;
            const pageItemClassName = `flex h-9 w-9 shrink-0 items-center justify-center rounded-lg transition-colors duration-150 ${
              isActive
                ? "border border-[#b6d1ff] bg-[#e7f0ff]"
                : "bg-transparent hover:bg-[#eef3fb]"
            }`;
            const modalItemClassName = `flex h-[42px] w-[42px] shrink-0 items-center justify-center rounded-[12px] border bg-[#F4F7FB] transition-colors ${
              isActive
                ? "border-[#D7E6FF]"
                : "border-[#E6EDF5] hover:border-[#D7E3FF]"
            }`;
            const itemClassName = isModalMode ? modalItemClassName : pageItemClassName;
            const iconClassName = isActive ? "text-[#246BFD]" : "text-[#34507F]";
            const fallbackIconClassName = isActive ? "text-[#246BFD]" : "text-[#6C81A3]";
            const itemStyle = isModalMode && isActive ? { boxShadow: "inset 0 0 0 1px #6EA8FF" } : undefined;
            const iconSizeClassName = isModalMode ? "h-[18px]! w-[18px]!" : "h-5! w-5!";
            const fallbackIconSizeClassName = isModalMode ? "text-[15px]" : "text-[17px]";
            return (
              <Tooltip
                key={binding.id}
                title={binding.name}
                placement="top"
                zIndex={1100}
                getPopupContainer={(trigger) => trigger?.parentElement || document.body}
              >
                <button
                  type="button"
                  onClick={() => onSelectBinding(binding.id)}
                  disabled={isDisabled}
                  aria-pressed={isActive}
                  aria-label={binding.name}
                  className={`flex min-h-10 min-w-10 shrink-0 items-center justify-center rounded-md transition-colors ${
                    isActive
                      ? ""
                      : isDisabled
                        ? "cursor-not-allowed opacity-70"
                        : ""
                  }`}
                >
                  <span className={itemClassName} style={itemStyle}>
                    {binding.icon ? (
                      <Icon type={binding.icon} className={`${iconSizeClassName} ${iconClassName}`} />
                    ) : (
                      <ArrowLeftOutlined rotate={180} className={`${fallbackIconSizeClassName} ${fallbackIconClassName}`} />
                    )}
                  </span>
                </button>
              </Tooltip>
            );
          })}
        </div>
      )}
    </div>
  );
}
