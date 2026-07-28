/**
 * 安全存储工具类
 * Tauri 环境下优先使用系统凭据存储保存认证 Token，普通缓存继续使用 Tauri Store。
 * 
 * 特点：
 * - iOS Token 存储在 Keychain 后端
 * - Android Token 由 Android Keystore-backed 原生安全存储保护
 * - 非敏感数据存储在应用私有目录，应用重启后数据依然保留
 * - 适合移动端长期登录场景
 */

import type { LoginUserInfo } from '@/types/user';
import type { Store } from '@tauri-apps/plugin-store';

// 存储键名常量
export const STORAGE_KEYS = {
    TOKEN: 'auth_token',
    USER_INFO: 'user_info',
    REFRESH_TOKEN: 'refresh_token',
} as const;

// 存储文件名
const STORE_FILE = 'secure_auth.json';

type CredentialKey = typeof STORAGE_KEYS.TOKEN | typeof STORAGE_KEYS.REFRESH_TOKEN;
type CredentialCommand =
    | 'secure_credential_set'
    | 'secure_credential_get'
    | 'secure_credential_remove';

const CREDENTIAL_KEYS: readonly CredentialKey[] = [
    STORAGE_KEYS.TOKEN,
    STORAGE_KEYS.REFRESH_TOKEN,
];

// 内存缓存，用于同步访问
const memoryCache = new Map<string, unknown>();
let storeInstance: Store | null = null;
let isInitialized = false;

/**
 * 检查是否在 Tauri 环境中运行
 */
export function isTauriEnvironment(): boolean {
    return typeof window !== 'undefined' && '__TAURI_INTERNALS__' in window;
}

function isCredentialKey(key: string): key is CredentialKey {
    return CREDENTIAL_KEYS.some((credentialKey) => credentialKey === key);
}

function shouldUseNativeCredentialStore(key: string): key is CredentialKey {
    return isTauriEnvironment() && isCredentialKey(key);
}

async function invokeSecureCredential<T>(
    command: CredentialCommand,
    args: Record<string, unknown>,
): Promise<T> {
    const { invoke } = await import('@tauri-apps/api/core');
    return await invoke<T>(command, args);
}

async function credentialSet(key: CredentialKey, value: string): Promise<void> {
    await invokeSecureCredential<void>('secure_credential_set', { key, value });
}

async function credentialGet(key: CredentialKey): Promise<string | null> {
    return await invokeSecureCredential<string | null>('secure_credential_get', { key });
}

async function credentialRemove(key: CredentialKey): Promise<void> {
    await invokeSecureCredential<void>('secure_credential_remove', { key });
}

/**
 * 清理旧版本在 Tauri Store 不可用时写入 localStorage 的认证数据。
 * H5/开发环境仍保留显式的 localStorage 存储行为。
 */
function clearLegacyAuthStorage(): void {
    if (typeof window === 'undefined') {
        return;
    }

    for (const key of Object.values(STORAGE_KEYS)) {
        window.localStorage.removeItem(key);
    }
}

/**
 * 获取 Store 实例
 */
async function getStore() {
    if (!isTauriEnvironment()) {
        return null;
    }

    clearLegacyAuthStorage();

    if (storeInstance) {
        return storeInstance;
    }

    try {
        const { load } = await import('@tauri-apps/plugin-store');
        storeInstance = await load(STORE_FILE, { autoSave: true, defaults: {} });
        return storeInstance;
    } catch (error) {
        console.error('Failed to load Tauri store:', error);
        throw error;
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
            const persistedValues = new Map<string, unknown>();
            if (shouldUseNativeCredentialStore(STORAGE_KEYS.TOKEN)) {
                const token = await credentialGet(STORAGE_KEYS.TOKEN);
                if (token) {
                    persistedValues.set(STORAGE_KEYS.TOKEN, token);
                }
                const refreshToken = await credentialGet(STORAGE_KEYS.REFRESH_TOKEN);
                if (refreshToken) {
                    persistedValues.set(STORAGE_KEYS.REFRESH_TOKEN, refreshToken);
                }
            } else {
                for (const key of CREDENTIAL_KEYS) {
                    const value = await store.get(key);
                    if (value !== null && value !== undefined) {
                        persistedValues.set(key, value);
                    }
                }
            }
            const userInfo = await store.get(STORAGE_KEYS.USER_INFO);
            if (userInfo !== null && userInfo !== undefined) {
                persistedValues.set(STORAGE_KEYS.USER_INFO, userInfo);
            }
            persistedValues.forEach((value, key) => memoryCache.set(key, value));
            isInitialized = true;
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
        }
    } catch (error) {
        console.error('Failed to initialize secure storage:', error);
        throw error;
    }
}

/**
 * 安全存储数据
 */
export async function secureSet<T>(key: string, value: T): Promise<void> {
    try {
        if (shouldUseNativeCredentialStore(key)) {
            if (typeof value !== 'string') {
                throw new Error(`Credential ${key} must be a string`);
            }
            await credentialSet(key, value);
        } else {
            const store = await getStore();
            if (store) {
                await store.set(key, value);
                await store.save();
            } else {
                // 非 Tauri 环境回退到 localStorage（仅用于开发）
                if (typeof window !== 'undefined') {
                    localStorage.setItem(key, JSON.stringify(value));
                }
            }
        }
        // 只有持久化成功后才更新内存，避免产生虚假的已保存状态。
        memoryCache.set(key, value);
    } catch (error) {
        console.error(`Failed to save ${key} to secure storage:`, error);
        throw error;
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
        if (shouldUseNativeCredentialStore(key)) {
            const value = await credentialGet(key);
            if (value !== null && value !== undefined) {
                memoryCache.set(key, value);
                return value as T;
            }
        } else {
            const store = await getStore();
            if (store) {
                const value = await store.get<T>(key);
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
    try {
        if (shouldUseNativeCredentialStore(key)) {
            await credentialRemove(key);
        } else {
            const store = await getStore();
            if (store) {
                await store.delete(key);
                await store.save();
            } else {
                // 非 Tauri 环境回退到 localStorage
                if (typeof window !== 'undefined') {
                    localStorage.removeItem(key);
                }
            }
        }
    } catch (error) {
        console.error(`Failed to remove ${key} from secure storage:`, error);
        throw error;
    } finally {
        // 无论持久化层是否可用，当前进程都不得继续复用旧凭据。
        memoryCache.delete(key);
    }
}

/**
 * 清除所有安全存储数据
 */
export async function secureClear(): Promise<void> {
    try {
        if (isTauriEnvironment()) {
            await Promise.all(
                Array.from(CREDENTIAL_KEYS).map((key) => credentialRemove(key)),
            );
        }

        const store = await getStore();
        if (store) {
            await store.clear();
            await store.save();
        } else {
            // 非 Tauri 环境回退到 localStorage
            if (typeof window !== 'undefined') {
                for (const key of Object.values(STORAGE_KEYS)) {
                    localStorage.removeItem(key);
                }
            }
        }
    } catch (error) {
        console.error('Failed to clear secure storage:', error);
        throw error;
    } finally {
        memoryCache.clear();
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
export function sanitizeUserInfoForStorage(userInfo: LoginUserInfo): LoginUserInfo {
    return { ...userInfo, token: '' };
}

export async function saveUserInfo(userInfo: LoginUserInfo): Promise<void> {
    const value = sanitizeUserInfoForStorage(userInfo);
    await secureSet(STORAGE_KEYS.USER_INFO, value);
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
    const failures: unknown[] = [];
    for (const key of Object.values(STORAGE_KEYS)) {
        try {
            // Tauri Store 是单实例，顺序删除避免并发 save 互相覆盖。
            await secureRemove(key);
        } catch (error) {
            failures.push(error);
        }
    }
    if (failures.length > 0) {
        throw new AggregateError(failures, 'Failed to clear authentication storage');
    }
}

/**
 * 检查是否已登录（同步方法）
 */
export function isLoggedIn(): boolean {
    return !!secureGetSync<string>(STORAGE_KEYS.TOKEN);
}
