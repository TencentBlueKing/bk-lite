import { formatAccountMessageTime } from '@/platform/preferences/dateTime';

/**
 * 格式化消息时间显示
 */
export const formatMessageTime = (
    timestamp: number,
    locale: string,
    timezone: string,
    yesterdayText: string,
): string => formatAccountMessageTime(
    timestamp,
    { locale, timezone },
    yesterdayText,
);

/**
 * 判断是否需要显示时间（超过10分钟间隔）
 */
export const shouldShowTime = (currentTimestamp: number, previousTimestamp?: number): boolean => {
    if (!previousTimestamp) return true; // 第一条消息总是显示时间
    const diff = currentTimestamp - previousTimestamp;
    return diff > 10 * 60 * 1000; // 超过10分钟
};
