/**
 * 安全存储工具类
 * 使用 Tauri Store 插件实现安全的数据存储
 * 
 * 特点：
 * - 数据存储在应用的私有目录中，其他应用无法访问
 * - 支持持久化存储，应用重启后数据依然保留
 * - 适合移动端长期登录场景
 */

import type { LoginUserInfo } from '@/types/user';

// 存储键名常量
export const STORAGE_KEYS = {
    TOKEN: 'auth_token',
    USER_INFO: 'user_info',
    REFRESH_TOKEN: 'refresh_token',
} as const;

// 存储文件名
const STORE_FILE = 'secure_auth.json';

// 内存缓存，用于同步访问
const memoryCache: Map<string, any> = new Map();
let storeInstance: any = null;
let isInitialized = false;

/**
 * 检查是否在 Tauri 环境中运行
 */
export function isTauriEnvironment(): boolean {
    return typeof window !== 'undefined' && '__TAURI_INTERNALS__' in window;
}

/**
 * 获取 Store 实例
 */
async function getStore() {
    if (storeInstance) {
        return storeInstance;
    }

    if (!isTauriEnvironment()) {
        return null;
    }

    try {
        const { load } = await import('@tauri-apps/plugin-store');
        storeInstance = await load(STORE_FILE, { autoSave: true, defaults: {} });
        return storeInstance;
    } catch (error) {
        console.error('Failed to load Tauri store:', error);
        return null;
    }
}

/**
 * 初始化安全存储
 * 从持久化存储加载数据到内存缓存
 */
export async function initSecureStorage(): Promise<void> {
    if (isInitialized) {
        return;
    }

    try {
        const store = await getStore();
        if (store) {
            // 从 Tauri Store 加载所有已保存的数据到内存缓存
            for (const key of Object.values(STORAGE_KEYS)) {
                const value = await store.get(key);
                if (value !== null && value !== undefined) {
                    memoryCache.set(key, value);
                }
            }
            isInitialized = true;
            console.log('Secure storage initialized from Tauri Store');
        } else {
            // 非 Tauri 环境，从 localStorage 加载（开发环境回退）
            if (typeof window !== 'undefined') {
                for (const key of Object.values(STORAGE_KEYS)) {
                    const value = localStorage.getItem(key);
                    if (value) {
                        try {
                            memoryCache.set(key, JSON.parse(value));
                        } catch {
                            memoryCache.set(key, value);
                        }
                    }
                }
            }
            isInitialized = true;
            console.log('Secure storage initialized from localStorage (fallback)');
        }
    } catch (error) {
        console.error('Failed to initialize secure storage:', error);
        isInitialized = true; // 标记为已初始化，避免重复尝试
    }
}

/**
 * 安全存储数据
 */
export async function secureSet<T>(key: string, value: T): Promise<void> {
    // 更新内存缓存
    memoryCache.set(key, value);

    try {
        const store = await getStore();
        if (store) {
            await store.set(key, value);
            await store.save();
            console.log(`Secure storage: saved ${key} to Tauri Store`);
        } else {
            // 非 Tauri 环境回退到 localStorage（仅用于开发）
            if (typeof window !== 'undefined') {
                localStorage.setItem(key, JSON.stringify(value));
                console.log(`Secure storage: saved ${key} to localStorage (fallback)`);
            }
        }
    } catch (error) {
        console.error(`Failed to save ${key} to secure storage:`, error);
    }
}

/**
 * 安全获取数据
 */
export async function secureGet<T>(key: string): Promise<T | null> {
    // 首先检查内存缓存
    if (memoryCache.has(key)) {
        return memoryCache.get(key) as T;
    }

    try {
        const store = await getStore();
        if (store) {
            const value = await store.get(key);
            if (value !== null && value !== undefined) {
                memoryCache.set(key, value);
                return value as T;
            }
        } else {
            // 非 Tauri 环境回退到 localStorage
            if (typeof window !== 'undefined') {
                const value = localStorage.getItem(key);
                if (value) {
                    try {
                        const parsed = JSON.parse(value);
                        memoryCache.set(key, parsed);
                        return parsed as T;
                    } catch {
                        memoryCache.set(key, value);
                        return value as unknown as T;
                    }
                }
            }
        }
    } catch (error) {
        console.error(`Failed to get ${key} from secure storage:`, error);
    }

    return null;
}

/**
 * 同步获取数据（仅从内存缓存）
 * 用于需要同步访问的场景
 */
export function secureGetSync<T>(key: string): T | null {
    return memoryCache.get(key) as T | null ?? null;
}

/**
 * 安全删除数据
 */
export async function secureRemove(key: string): Promise<void> {
    // 从内存缓存删除
    memoryCache.delete(key);

    try {
        const store = await getStore();
        if (store) {
            await store.delete(key);
            await store.save();
            console.log(`Secure storage: removed ${key} from Tauri Store`);
        } else {
            // 非 Tauri 环境回退到 localStorage
            if (typeof window !== 'undefined') {
                localStorage.removeItem(key);
                console.log(`Secure storage: removed ${key} from localStorage (fallback)`);
            }
        }
    } catch (error) {
        console.error(`Failed to remove ${key} from secure storage:`, error);
    }
}

/**
 * 清除所有安全存储数据
 */
export async function secureClear(): Promise<void> {
    // 清空内存缓存
    memoryCache.clear();

    try {
        const store = await getStore();
        if (store) {
            await store.clear();
            await store.save();
            console.log('Secure storage: cleared all data from Tauri Store');
        } else {
            // 非 Tauri 环境回退到 localStorage
            if (typeof window !== 'undefined') {
                for (const key of Object.values(STORAGE_KEYS)) {
                    localStorage.removeItem(key);
                }
                console.log('Secure storage: cleared all data from localStorage (fallback)');
            }
        }
    } catch (error) {
        console.error('Failed to clear secure storage:', error);
    }
}

// ==================== 便捷方法 ====================

/**
 * 保存认证 Token
 */
export async function saveToken(token: string): Promise<void> {
    await secureSet(STORAGE_KEYS.TOKEN, token);
}

/**
 * 获取认证 Token
 */
export async function getToken(): Promise<string | null> {
    return await secureGet<string>(STORAGE_KEYS.TOKEN);
}

/**
 * 同步获取 Token（从内存缓存）
 */
export function getTokenSync(): string | null {
    return secureGetSync<string>(STORAGE_KEYS.TOKEN);
}

/**
 * 保存用户信息
 */
export async function saveUserInfo(userInfo: LoginUserInfo): Promise<void> {
    await secureSet(STORAGE_KEYS.USER_INFO, userInfo);
}

/**
 * 获取用户信息
 */
export async function getUserInfoFromStorage(): Promise<LoginUserInfo | null> {
    return await secureGet<LoginUserInfo>(STORAGE_KEYS.USER_INFO);
}

/**
 * 同步获取用户信息（从内存缓存）
 */
export function getUserInfoSync(): LoginUserInfo | null {
    return secureGetSync<LoginUserInfo>(STORAGE_KEYS.USER_INFO);
}

/**
 * 清除认证数据（登出时调用）
 */
export async function clearAuthData(): Promise<void> {
    await secureRemove(STORAGE_KEYS.TOKEN);
    await secureRemove(STORAGE_KEYS.USER_INFO);
    await secureRemove(STORAGE_KEYS.REFRESH_TOKEN);
}

/**
 * 检查是否已登录（同步方法）
 */
export function isLoggedIn(): boolean {
    return !!secureGetSync<string>(STORAGE_KEYS.TOKEN);
}
