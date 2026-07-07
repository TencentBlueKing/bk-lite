"use client";

import type { ReactNode } from "react";

interface SigninContentShellProps {
  mode: "page" | "modal";
  mainContent: ReactNode;
  methodsContent?: ReactNode;
  methodsTitle?: ReactNode;
}

export default function SigninContentShell({
  mode,
  mainContent,
  methodsContent,
  methodsTitle,
}: SigninContentShellProps) {
  const isModalMode = mode === "modal";

  return (
    <div className={`w-full ${isModalMode ? "" : "max-w-md"}`} style={isModalMode ? { maxWidth: 388 } : undefined}>
      <div className={isModalMode ? "h-[228px]" : "h-[236px]"}>{mainContent}</div>
      {methodsContent ? (
        <div className={isModalMode ? "mt-5 border-t border-[#E7EDF4] pt-4" : "mt-6 border-t border-[#E7EDF4] pt-4"}>
          {methodsTitle ? (
            <div className={`mb-3 text-(--color-text-3) ${isModalMode ? "text-[12px] leading-5" : "text-[13px] leading-5"}`}>
              {methodsTitle}
            </div>
          ) : null}
          {methodsContent}
        </div>
      ) : null}
    </div>
  );
}
