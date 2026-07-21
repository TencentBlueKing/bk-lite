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
  const pageMethodsClassName = "mt-6 text-center";

  return (
    <div className="w-full" style={isModalMode ? { maxWidth: 388 } : undefined}>
      <div className="min-h-0">{mainContent}</div>
      {methodsContent ? (
        <div className={isModalMode ? "mt-5 text-center" : pageMethodsClassName}>
          {methodsTitle ? (
            <div className="mb-3 flex items-center gap-3 text-[12px] leading-5 text-(--color-text-3)">
              <span className="h-px flex-1 bg-(--color-border)" />
              <span>{methodsTitle}</span>
              <span className="h-px flex-1 bg-(--color-border)" />
            </div>
          ) : null}
          {methodsContent}
        </div>
      ) : null}
    </div>
  );
}
