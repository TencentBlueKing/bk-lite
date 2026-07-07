"use client";

import {
  ArrowLeftOutlined,
} from "@ant-design/icons";
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
        <div className="flex flex-wrap items-start gap-x-4 gap-y-1.5">
          {bindings.map((binding) => {
            const isActive = binding.id === selectedBindingId;
            const isDisabled = isSelectionLocked;
            return (
              <button
                key={binding.id}
                type="button"
                onClick={() => onSelectBinding(binding.id)}
                title={binding.name}
                disabled={isDisabled}
                aria-pressed={isActive}
                className={`flex w-[42px] shrink-0 flex-col items-center px-0.5 pt-0.5 pb-0 text-center transition-colors ${
                  isActive
                    ? ""
                    : isDisabled
                      ? "cursor-not-allowed opacity-70"
                      : ""
                }`}
              >
                <span className="flex items-center justify-center">
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
                </span>
                <span
                  className={`mt-1.5 block break-words text-[11px] leading-[1.25] font-medium ${isActive ? "text-[#246BFD]" : "text-(--color-text-2)"}`}
                  style={{
                    width: 42,
                    maxWidth: 42,
                    display: "-webkit-box",
                    WebkitLineClamp: 2,
                    WebkitBoxOrient: "vertical",
                    overflow: "hidden",
                  }}
                >
                  {binding.name}
                </span>
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}
