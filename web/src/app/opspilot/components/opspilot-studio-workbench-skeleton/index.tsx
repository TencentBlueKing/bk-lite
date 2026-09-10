'use client';

import React from 'react';
import { Skeleton } from 'antd';

const Bone: React.FC<{ className?: string }> = ({ className = '' }) => (
  <Skeleton.Input active size="small" className={`!min-w-0 ${className}`} />
);

const FormRow: React.FC = () => (
  <div className="mb-3.5 flex items-center gap-3">
    <Bone className="!h-4 !w-16" />
    <Bone className="!h-8 !flex-1 !w-auto" />
  </div>
);

const SettingRow: React.FC = () => (
  <div className="flex items-center justify-between py-2.5">
    <Bone className="!h-4 !w-28" />
    <Bone className="!h-5 !w-9 !rounded-full" />
  </div>
);

/** 设置双栏加载骨架 — 与智能体设置页最终布局同构，禁止用居中 Spin 代替 */
export default function OpsPilotStudioWorkbenchSkeleton() {
  return (
    <div
      className="flex h-full min-h-0 gap-3.5"
      aria-busy="true"
      aria-label="loading"
    >
      <div className="flex h-full min-h-0 w-1/2 flex-col overflow-hidden rounded-lg border border-[var(--color-border-1)] bg-[var(--color-bg)]">
        <div className="flex h-11 shrink-0 items-center justify-between border-b border-[var(--color-border-1)] bg-[var(--color-fill-1)]/60 px-4">
          <div className="flex items-center gap-2">
            <Skeleton.Avatar active size={20} shape="square" className="!rounded" />
            <Bone className="!h-4 !w-16" />
          </div>
          <Bone className="!h-5 !w-16" />
        </div>

        <div className="min-h-0 flex-1 overflow-hidden px-5 py-4">
          <div className="mb-3.5 flex items-center gap-2">
            <span className="h-3.5 w-1 rounded-full bg-[var(--color-fill-3)]" />
            <Bone className="!h-4 !w-20" />
          </div>
          <FormRow />
          <FormRow />
          <FormRow />
          <FormRow />

          <div className="mb-3.5 mt-6 flex items-center gap-2 border-t border-[var(--color-border-1)] pt-5">
            <span className="h-3.5 w-1 rounded-full bg-[var(--color-fill-3)]" />
            <Bone className="!h-4 !w-24" />
          </div>
          <FormRow />
          <FormRow />

          <div className="divide-y divide-[var(--color-fill-2)]/60 pt-1">
            <SettingRow />
            <SettingRow />
            <SettingRow />
          </div>

          <div className="mt-6 border-t border-[var(--color-border-1)] pt-5">
            <div className="mb-2.5 flex items-center justify-between">
              <Bone className="!h-4 !w-14" />
              <Bone className="!h-4 !w-20" />
            </div>
            <div className="grid grid-cols-2 gap-2">
              <div className="rounded-lg bg-[var(--color-fill-1)]/70 p-2.5">
                <div className="flex items-center gap-1.5">
                  <Skeleton.Avatar active size={20} shape="square" className="!rounded" />
                  <Bone className="!h-4 !w-24" />
                </div>
              </div>
              <div className="rounded-lg bg-[var(--color-fill-1)]/70 p-2.5">
                <div className="flex items-center gap-1.5">
                  <Skeleton.Avatar active size={20} shape="square" className="!rounded" />
                  <Bone className="!h-4 !w-20" />
                </div>
              </div>
            </div>
          </div>
        </div>

        <div className="flex h-12 shrink-0 items-center justify-between border-t border-[var(--color-border-1)] px-5">
          <Bone className="!h-3 !w-32" />
          <Bone className="!h-8 !w-16 !rounded-md" />
        </div>
      </div>

      <div className="flex h-full min-h-0 w-1/2 flex-col overflow-hidden rounded-lg border border-[var(--color-border-1)] bg-[var(--color-bg)]">
        <div className="flex h-11 shrink-0 items-center justify-between border-b border-[var(--color-border-1)] bg-[var(--color-fill-1)]/60 px-4">
          <div className="flex items-center gap-2">
            <Skeleton.Avatar active size={20} shape="square" className="!rounded" />
            <Bone className="!h-4 !w-12" />
            <Bone className="!h-5 !w-28 !rounded-full" />
          </div>
          <Bone className="!h-5 !w-20" />
        </div>

        <div className="flex min-h-0 flex-1 flex-col px-4 py-4">
          <div className="mb-4 space-y-2">
            <Bone className="!h-4 !w-[88%]" />
            <Bone className="!h-4 !w-[62%]" />
          </div>
          <div className="mb-4 flex flex-wrap gap-2">
            <Bone className="!h-7 !w-16 !rounded-md" />
            <Bone className="!h-7 !w-14 !rounded-md" />
          </div>
          <div className="mt-auto rounded-xl border border-[var(--color-border-1)] bg-[var(--color-bg)] px-3 py-2.5">
            <Bone className="!mb-3 !h-4 !w-[42%]" />
            <div className="flex items-center justify-between">
              <div className="flex gap-1.5">
                <Skeleton.Avatar active size={20} shape="square" className="!rounded" />
                <Skeleton.Avatar active size={20} shape="square" className="!rounded" />
              </div>
              <Skeleton.Avatar active size={28} shape="circle" />
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
