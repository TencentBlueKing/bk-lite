"use client";

import {
  ArrowLeftOutlined,
  LoadingOutlined,
} from "@ant-design/icons";
import Icon from "@/components/icon";
import type { LoginAuthBindingItem } from "./types";

interface LoginAuthValidationPanelProps {
  bindings: LoginAuthBindingItem[];
  isLoadingBindings: boolean;
  activeBindingId: number | null;
  isSelectionLocked: boolean;
  onStartLoginAuth: (binding: LoginAuthBindingItem) => void;
}

export default function LoginAuthValidationPanel({
  bindings,
  isLoadingBindings,
  activeBindingId,
  isSelectionLocked,
  onStartLoginAuth,
}: LoginAuthValidationPanelProps) {
  const shouldShowLoadingState = isLoadingBindings && bindings.length === 0;

  return (
    <div className="space-y-3 pt-5">
      {shouldShowLoadingState && (
        <div className="flex min-h-[132px] items-center justify-center rounded-2xl border border-[#E9EDF5] bg-white/72 px-6 py-6 shadow-[0_10px_26px_rgba(15,23,42,0.04)]">
          <div className="flex h-11 w-11 items-center justify-center rounded-full bg-[#F4F7FB] text-[18px] text-(--color-text-3)">
            <LoadingOutlined />
          </div>
        </div>
      )}

      {bindings.length > 0 && (
        <div className="grid grid-cols-[repeat(auto-fit,minmax(88px,100px))] justify-center gap-4">
          {bindings.map((binding) => {
            const isActive = isSelectionLocked && binding.id === activeBindingId;
            const isDisabled = isSelectionLocked;
            return (
              <button
                key={binding.id}
                type="button"
                onClick={() => onStartLoginAuth(binding)}
                title={binding.name}
                disabled={isDisabled}
                aria-pressed={isActive}
                className={`flex h-[104px] w-full flex-col items-center rounded-2xl px-2 pt-4 pb-3 text-center shadow-[0_8px_20px_rgba(15,23,42,0.04)] transition-all ${
                  isActive
                    ? "border border-[#4F86FF] bg-white/90 shadow-[0_10px_22px_rgba(36,107,253,0.05)]"
                    : isDisabled
                      ? "cursor-not-allowed border border-[#DCE4F1] bg-white/72 opacity-70"
                      : "border border-[#E9EDF5] bg-white/90 hover:-translate-y-0.5 hover:border-[#D4E4FF] hover:shadow-[0_12px_28px_rgba(36,107,253,0.10)]"
                }`}
              >
                <span className="flex min-h-0 flex-1 items-center justify-center">
                  <span className={`flex h-14 w-14 shrink-0 items-center justify-center rounded-2xl ${isActive ? "bg-[#F4F8FF]" : "bg-[#F4F7FB]"}`}>
                    {binding.icon ? (
                      <Icon type={binding.icon} className={`h-6! w-6! ${isActive ? "text-[#246BFD]" : "text-(--color-text-1)"}`} />
                    ) : (
                      <ArrowLeftOutlined rotate={180} className={`text-base ${isActive ? "text-[#246BFD]" : "text-(--color-text-3)"}`} />
                    )}
                  </span>
                </span>
                <span className={`mt-2 block w-full shrink-0 truncate text-[12px] leading-4 font-medium ${isActive ? "text-[#246BFD]" : "text-(--color-text-2)"}`}>
                  {binding.name}
                </span>
              </button>
            );
          })}
        </div>
      )}

      {!isLoadingBindings && bindings.length === 0 && (
        <div className="rounded-2xl border border-dashed border-(--color-border-2) bg-(--color-fill-1) px-4 py-6 text-center text-sm text-(--color-text-3)">
          No external login methods are currently available.
        </div>
      )}
    </div>
  );
}
