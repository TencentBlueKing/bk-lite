import React from 'react';

export const actionItems = [
    {
        key: 'copy',
        icon: React.createElement('span', {
            className: 'iconfont icon-fuzhi text-sm font-bold',
        }),
    },
    {
        key: 'regenerate',
        icon: React.createElement('span', {
            className: 'iconfont icon-shuaxin text-sm font-bold',
        }),
    },
];

// 推荐内容池
export const recommendationPool = [
    ['CPU利用率持续95%以上，可能的原因是什么？', '写一个Shell脚本，实现每晚自动备份2点自动备份/log目录到/bak，并上传至远程ftp', '如何设置自动清理30天前的文件？'],
    ['如何优化MySQL数据库查询性能？', '编写一个Python脚本监控服务器状态', '如何配置Nginx反向代理？'],
    ['Docker容器占用空间过大如何清理？', '如何实现Redis主从同步？', 'Linux系统如何设置定时任务？'],
    ['如何排查Java应用内存泄漏？', '编写一个自动化部署脚本', 'Git多分支开发的最佳实践是什么？'],
    ['如何监控服务器磁盘IO性能？', '实现一个简单的API接口限流', 'Kubernetes如何进行资源配额管理？'],
];

// 获取随机推荐内容
export const getRandomRecommendations = () => {
    return recommendationPool[Math.floor(Math.random() * recommendationPool.length)];
};

// LocalStorage key
export const LAST_VISIT_KEY = 'conversation_last_visit_time';
