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
  const pageMethodsClassName =
    mode === "page"
      ? "mt-8 border-white/30 pt-7 text-center"
      : "mt-5 text-center";

  return (
    <div className="w-full" style={isModalMode ? { maxWidth: 388 } : undefined}>
      <div className={isModalMode ? "h-[228px]" : "min-h-[236px]"}>{mainContent}</div>
      {methodsContent ? (
        <div className={isModalMode ? "mt-5 text-center" : pageMethodsClassName}>
          {methodsTitle ? (
            <div
              className={`mb-3 ${isModalMode ? "text-(--color-text-3) text-[12px] leading-5" : "text-[13px] leading-5 text-[#7386a7]"}`}
            >
              {methodsTitle}
            </div>
          ) : null}
          {methodsContent}
        </div>
      ) : null}
    </div>
  );
}
