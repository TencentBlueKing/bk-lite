'use client';

import React from 'react';
import Image from 'next/image';
import { Empty, Tooltip } from 'antd';
import { useTranslation } from '@/utils/i18n';
import type { TaskStatusMap, TreeNode } from '@/app/cmdb/types/autoDiscovery';
import {
  cleanPluginName,
  countPluginTasks,
  filterCatalogCategories,
  getCollectionIconSrc,
  getTaskStatusStats,
} from '../pluginCatalog';

interface PluginCatalogViewProps {
  categories: TreeNode[];
  taskStatus: TaskStatusMap;
  keyword: string;
  onSelectPlugin: (pluginId: string) => void;
}

const PluginCatalogView: React.FC<PluginCatalogViewProps> = ({
  categories,
  taskStatus,
  keyword,
  onSelectPlugin,
}) => {
  const { t } = useTranslation();
  const groups = filterCatalogCategories(categories, keyword);

  if (!groups.length) {
    return (
      <div className="flex flex-1 items-center justify-center py-16">
        <Empty description={t('Collection.catalog.empty')} />
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-5 pb-6">
      {groups.map(({ category, plugins }) => {
        return (
          <section
            key={category.id}
            className="flex flex-col rounded-2xl border border-slate-200/70 bg-white p-4 sm:p-5 shadow-[0_1px_3px_rgba(0,0,0,0.02),0_8px_20px_rgba(0,0,0,0.02)] transition-shadow hover:shadow-[0_2px_8px_rgba(0,0,0,0.04),0_12px_28px_rgba(0,0,0,0.03)]"
          >
            {/* 分类行标题：纯文字排版，名字 + 数量药丸，不加logo */}
            <div className="flex items-center gap-2.5 pb-3.5">
              <h2 className="m-0 text-[15px] font-bold tracking-tight text-slate-800">
                {category.name}
              </h2>
              <span className="inline-flex items-center justify-center rounded-full bg-slate-100 px-2.5 py-0.5 text-xs font-semibold tabular-nums text-slate-500">
                {plugins.length}
              </span>
              <div className="h-px flex-1 bg-slate-100" />
            </div>

            {/* 插件自适应平铺网格：全量平铺，展示图标、名称、标签与任务状态 */}
            <div className="grid grid-cols-[repeat(auto-fill,minmax(230px,1fr))] gap-3.5">
              {plugins.map((plugin) => {
                const stats = getTaskStatusStats(taskStatus, plugin);
                const total = countPluginTasks(stats);
                const failed = stats?.failed || 0;
                const { cleanName, isBeta } = cleanPluginName(plugin.name);
                const iconSrc = getCollectionIconSrc(plugin);
                const displayTags = (plugin.tag || []).filter(
                  (t) => t.toLowerCase() !== 'beta',
                );

                const tooltipTitle = (
                  <div className="flex flex-col gap-1 text-xs">
                    <div className="font-semibold">{plugin.name}</div>
                    {plugin.desc && (
                      <div className="text-white/80">{plugin.desc}</div>
                    )}
                    <div className="mt-1 flex items-center gap-2 border-t border-white/20 pt-1">
                      <span>{t('Collection.statusLabel.running')}: {stats?.running || 0}</span>
                      <span>{t('Collection.statusLabel.syncSuccess')}: {stats?.success || 0}</span>
                      <span className={failed > 0 ? 'text-rose-300 font-semibold' : ''}>
                        {t('Collection.statusLabel.syncFailed')}: {failed}
                      </span>
                    </div>
                  </div>
                );

                return (
                  <Tooltip key={plugin.id} title={tooltipTitle} placement="top">
                    <button
                      type="button"
                      className="group relative flex min-w-0 cursor-pointer items-start gap-3 rounded-xl border border-slate-200/70 bg-slate-50/50 p-3 text-left transition-all duration-200 hover:-translate-y-0.5 hover:border-blue-300 hover:bg-white hover:shadow-[0_4px_16px_rgba(37,99,235,0.08),0_1px_3px_rgba(0,0,0,0.03)] active:scale-[0.98] focus:outline-none focus:ring-2 focus:ring-blue-100"
                      onClick={() => onSelectPlugin(plugin.id)}
                    >
                      {/* Apple 风格图标容器底座 */}
                      <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl border border-slate-100 bg-white p-1.5 shadow-[0_1px_2px_rgba(0,0,0,0.04)] transition-transform duration-200 group-hover:scale-105">
                        <Image
                          src={iconSrc}
                          alt=""
                          width={26}
                          height={26}
                          unoptimized
                          className="object-contain"
                        />
                      </div>

                      {/* 标题、标签与任务信息 */}
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center gap-1.5">
                          <span className="block truncate text-[13.5px] font-semibold text-slate-800 transition-colors group-hover:text-blue-600">
                            {cleanName}
                          </span>
                          {isBeta && (
                            <span className="shrink-0 rounded-full border border-amber-200 bg-amber-50 px-1.5 py-0.2 text-[9px] font-bold leading-none text-amber-700">
                              BETA
                            </span>
                          )}
                        </div>

                        {/* 插件标签（Tags） */}
                        {displayTags.length > 0 && (
                          <div className="mt-1.5 flex flex-wrap gap-1">
                            {displayTags.map((tag) => (
                              <span
                                key={tag}
                                className="inline-flex items-center rounded-md bg-slate-200/60 px-1.5 py-0.5 text-[10px] font-medium leading-none text-slate-600"
                              >
                                {tag}
                              </span>
                            ))}
                          </div>
                        )}

                        {/* 任务状态指示灯与数量 */}
                        <div className="mt-2 flex items-center gap-1.5">
                          <span
                            className={`h-1.5 w-1.5 shrink-0 rounded-full ${
                              failed > 0
                                ? 'bg-rose-500 shadow-[0_0_0_2px_rgba(244,63,94,0.18)]'
                                : total > 0
                                  ? 'bg-emerald-500 shadow-[0_0_0_2px_rgba(16,185,129,0.18)]'
                                  : 'bg-slate-300'
                            }`}
                          />
                          <span
                            className={`text-xs tabular-nums leading-none ${
                              failed > 0
                                ? 'font-semibold text-rose-600'
                                : total > 0
                                  ? 'font-medium text-slate-600'
                                  : 'text-slate-400'
                            }`}
                          >
                            {total > 0
                              ? t('Collection.catalog.taskCount', '', { n: total })
                              : t('Collection.catalog.noTask')}
                          </span>
                        </div>
                      </div>
                    </button>
                  </Tooltip>
                );
              })}
            </div>
          </section>
        );
      })}
    </div>
  );
};

export default PluginCatalogView;
