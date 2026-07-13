"use client";

import {
  ArrowLeftOutlined,
} from "@ant-design/icons";
import { Tooltip } from "antd";
import Icon from "@/components/icon";
import type { LoginAuthBindingItem } from "./types";

interface LoginAuthValidationPanelProps {
  bindings: LoginAuthBindingItem[];
  selectedBindingId: number | null;
  isSelectionLocked: boolean;
  onSelectBinding: (bindingId: number) => void;
}

export default function LoginAuthValidationPanel({
  bindings,
  selectedBindingId,
  isSelectionLocked,
  onSelectBinding,
}: LoginAuthValidationPanelProps) {
  return (
    <div className="space-y-3">
      {bindings.length > 0 && (
        <div className="inline-flex flex-wrap items-start justify-between gap-x-8">
          {bindings.map((binding) => {
            const isActive = binding.id === selectedBindingId;
            const isDisabled = isSelectionLocked;
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
                  className={`flex shrink-0 items-center justify-center transition-colors ${
                    isActive
                      ? ""
                      : isDisabled
                        ? "cursor-not-allowed opacity-70"
                        : ""
                  }`}
                >
                  <span
                    className={`flex h-[42px] w-[42px] shrink-0 items-center justify-center rounded-[12px] border bg-[#F4F7FB] transition-colors ${
                      isActive ? "border-[#D7E6FF]" : "border-[#E6EDF5]"
                    }`}
                    style={isActive ? { boxShadow: "inset 0 0 0 1px #6EA8FF" } : undefined}
                  >
                    {binding.icon ? (
                      <Icon type={binding.icon} className={`h-[18px]! w-[18px]! ${isActive ? "text-[#246BFD]" : "text-(--color-text-1)"}`} />
                    ) : (
                      <ArrowLeftOutlined rotate={180} className={`text-[15px] ${isActive ? "text-[#246BFD]" : "text-(--color-text-3)"}`} />
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
