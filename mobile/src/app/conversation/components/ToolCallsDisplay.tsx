import React, { useState } from 'react';
import { Ellipsis, SpinLoading } from 'antd-mobile';
import { DownOutline, UpOutline, CheckOutline } from 'antd-mobile-icons';
import { ToolCall } from '../hooks/useMessages';

interface ToolCallsDisplayProps {
    toolCalls: ToolCall[];
    isRunFinished?: boolean; // AI 是否已运行完成
}

export const ToolCallsDisplay: React.FC<ToolCallsDisplayProps> = ({ toolCalls, isRunFinished = false }) => {
    const [showAll, setShowAll] = useState(false);

    if (!toolCalls || toolCalls.length === 0) {
        return null;
    }

    // 显示逻辑：
    // - 如果 AI 还在运行（isRunFinished 为 false），全部展开
    // - 如果 AI 运行结束且工具数量 > 3，默认收起，用户可手动展开
    const shouldCollapse = isRunFinished && toolCalls.length > 3;
    const shouldShowAll = !shouldCollapse || showAll;
    // 只有在 AI 运行结束、工具数量 >= 10 且用户展开全部时才启用滚动
    const hasScrolling = isRunFinished && toolCalls.length >= 10 && shouldShowAll;
    const displayTools = shouldShowAll ? toolCalls : toolCalls.slice(0, 3);


    return (
        <div className="mx-2 mt-3 mb-2">
            <div
                className={`flex flex-col gap-2 ${hasScrolling && shouldShowAll ? 'max-h-[400px] overflow-y-auto' : ''}`}
            >
                {displayTools.map((tool) => {
                    const hasResult = tool.status === 'completed' && tool.result;

                    return (
                        <div
                            key={tool.id}
                            className="bg-[var(--color-bg)] rounded-3xl p-3 border-2 border-[var(--color-border)]"
                        >
                            {/* 工具名称和状态 */}
                            <div className="flex items-center justify-between">
                                <div className="flex items-center gap-2">
                                    <span className="iconfont icon-gongju text-blue-500 text-base"></span>
                                    <span className="text-sm text-[var(--color-text-1)] font-bold">
                                        {tool.name}
                                    </span>
                                </div>
                                {tool.status === 'executing' && (
                                    <div className="flex items-center gap-1 text-xs text-[var(--color-text-3)]">
                                        <span>执行中</span>
                                        <SpinLoading style={{ '--size': '14px' }} />
                                    </div>
                                )}
                                {tool.status === 'completed' && (
                                    <div className="flex items-center gap-1 text-xs text-green-500">
                                        <span>执行完成</span>
                                        <CheckOutline />
                                    </div>
                                )}
                            </div>

                            {/* 工具执行结果 */}
                            {hasResult && (
                                <div
                                    className="text-xs text-[var(--color-text-2)]"
                                >
                                    <Ellipsis
                                        direction="end"
                                        rows={1}
                                        content={tool.result}
                                        expandText={
                                            <span className="m-1 inline-flex items-center">
                                                <DownOutline />
                                            </span>
                                        }
                                        collapseText={
                                            <span className="m-1 inline-flex items-center">
                                                <UpOutline />
                                            </span>
                                        }
                                    />
                                </div>
                            )}
                        </div>
                    );
                })}
            </div>

            {/* 展开/收起按钮 */}
            {shouldCollapse && (
                <div className="mt-3 flex justify-center">
                    <button
                        onClick={() => setShowAll(!showAll)}
                        className="flex items-center gap-1 text-sm text-blue-500 py-1 px-3 rounded-full border border-blue-500 hover:bg-blue-50 transition-colors"
                    >
                        {showAll ? (
                            <>
                                <UpOutline />
                                <span>收起</span>
                            </>
                        ) : (
                            <>
                                <DownOutline />
                                <span>展开全部 (+{toolCalls.length - 3})</span>
                            </>
                        )}
                    </button>
                </div>
            )}
        </div>
    );
};
