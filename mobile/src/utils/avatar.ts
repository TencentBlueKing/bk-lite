import { withBasePath } from './basePath';

/**
 * 头像工具函数
 */

// 头像列表
const avatarList = [
    withBasePath('/avatars/01.png'),
    withBasePath('/avatars/02.png'),
    withBasePath('/avatars/03.png'),
    withBasePath('/avatars/04.png'),
];

/**
 * 根据 id 获取固定的头像
 * @param id - 用于确定头像的 ID（数字或字符串）
 * @returns 头像路径
 */
export const getAvatar = (id: number | string): string => {
    const numId = typeof id === 'string' ? parseInt(id, 10) || 0 : id;
    return avatarList[Math.abs(numId) % avatarList.length];
};

/**
 * 获取头像列表
 * @returns 所有头像路径数组
 */
export const getAvatarList = (): string[] => {
    return [...avatarList];
};
