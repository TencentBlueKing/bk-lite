import React from 'react';
import { Ellipsis, SpinLoading } from 'antd-mobile';
import { DownOutline, UpOutline, CheckOutline, CloseOutline } from 'antd-mobile-icons';
import { ToolCall } from '@/types/conversation';
import { useTranslation } from '@/utils/i18n';

interface ToolCallItemProps {
    toolCall: ToolCall;
}

/**
 * 单个工具调用显示组件 - 用于在消息气泡内显示
 */
export const ToolCallItem: React.FC<ToolCallItemProps> = ({ toolCall }) => {
    const { t } = useTranslation();
    const hasResult = toolCall.status === 'completed' && toolCall.result;

    return (
        <div className="bg-[var(--color-fill-2)] rounded-2xl p-3 border border-[var(--color-border)]">
            {/* 工具名称和状态 */}
            <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                    <span className="iconfont icon-gongju text-blue-500 text-base"></span>
                    <span className="text-sm text-[var(--color-text-1)] font-bold">
                        {toolCall.name}
                    </span>
                </div>
                {toolCall.status === 'executing' && (
                    <div className="flex items-center gap-1 text-xs text-[var(--color-text-3)]">
                        <span>{t('chat.executing')}</span>
                        <SpinLoading style={{ '--size': '14px' }} />
                    </div>
                )}
                {toolCall.status === 'completed' && (
                    <div className="flex items-center gap-1 text-xs text-green-500">
                        <span>{t('chat.executionSuccess')}</span>
                        <CheckOutline />
                    </div>
                )}
                {toolCall.status === 'fail' && (
                    <div className="flex items-center gap-1 text-xs text-red-500">
                        <span>{t('chat.executionFailed')}</span>
                        <CloseOutline />
                    </div>
                )}
            </div>

            {/* 工具执行结果 */}
            {hasResult && (
                <div className="mt-2 text-xs text-[var(--color-text-2)]">
                    <Ellipsis
                        direction="end"
                        rows={1}
                        content={typeof toolCall.result === 'string' ? toolCall.result : JSON.stringify(toolCall.result)}
                        expandText={
                            <span className="m-1 inline-flex items-center text-blue-500">
                                <DownOutline />
                            </span>
                        }
                        collapseText={
                            <span className="m-1 inline-flex items-center text-blue-500">
                                <UpOutline />
                            </span>
                        }
                    />
                </div>
            )}
        </div>
    );
};
