/**
 * 格式化消息时间显示
 */
export const formatMessageTime = (timestamp: number): string => {
    const date = new Date(timestamp);
    const now = new Date();

    // 今天
    if (date.toDateString() === now.toDateString()) {
        return date.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' });
    }

    // 昨天
    const yesterday = new Date(now);
    yesterday.setDate(yesterday.getDate() - 1);
    if (date.toDateString() === yesterday.toDateString()) {
        return '昨天 ' + date.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' });
    }

    // 其他日期
    return date.toLocaleDateString('zh-CN', { month: '2-digit', day: '2-digit' }) + ' ' +
        date.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' });
};

/**
 * 判断是否需要显示时间（超过1分钟间隔）
 */
export const shouldShowTime = (currentTimestamp: number, previousTimestamp?: number): boolean => {
    if (!previousTimestamp) return true; // 第一条消息总是显示时间
    const diff = currentTimestamp - previousTimestamp;
    return diff > 1 * 60 * 1000; // 超过1分钟
};
