"use client";

import React from "react";

interface ConfigBlockProps {
  title: React.ReactNode;
  extra?: React.ReactNode;
  children?: React.ReactNode;
  className?: string;
  bodyClassName?: string;
}

/** 数据配置内统一内容块：标题栏 + 内容区，便于区分标题与正文 */
const ConfigBlock: React.FC<ConfigBlockProps> = ({
  title,
  extra,
  children,
  className,
  bodyClassName,
}) => (
  <div
    className={`overflow-hidden rounded-md border border-[var(--color-border-1)] ${className || ""}`}
  >
    <div
      className={`flex min-h-9 items-center justify-between gap-3 bg-[var(--color-fill-2)] px-3 py-1.5 ${
        children != null ? "border-b border-[var(--color-border-1)]" : ""
      }`}
    >
      <div className="inline-flex min-w-0 items-center gap-1.5 text-[13px] font-medium leading-[22px] text-[var(--color-text-1)]">
        {title}
      </div>
      {extra ? <div className="shrink-0">{extra}</div> : null}
    </div>
    {children != null ? (
      <div className={`p-3 ${bodyClassName || ""}`}>{children}</div>
    ) : null}
  </div>
);

export default ConfigBlock;
