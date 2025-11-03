/**
 * 安全的存储工具类，兼容 SSR 环境
 * 在服务端渲染时不会崩溃，客户端正常工作
 */

export class SafeStorage {
  private static isClient(): boolean {
    return typeof window !== 'undefined';
  }

  /**
   * 获取 sessionStorage 中的值
   * @param key 存储键
   * @param defaultValue 默认值
   * @returns 存储的值或默认值
   */
  static getSessionItem<T = string>(
    key: string,
    defaultValue: T | null = null
  ): T | null {
    if (!this.isClient()) {
      return defaultValue;
    }

    try {
      const item = sessionStorage.getItem(key);
      if (item === null) {
        return defaultValue;
      }

      // 尝试解析 JSON，如果失败则返回原始字符串
      try {
        return JSON.parse(item) as T;
      } catch {
        return item as unknown as T;
      }
    } catch (error) {
      console.warn(
        `SafeStorage: Failed to get sessionStorage item "${key}":`,
        error
      );
      return defaultValue;
    }
  }

  /**
   * 设置 sessionStorage 中的值
   * @param key 存储键
   * @param value 要存储的值
   * @returns 是否成功设置
   */
  static setSessionItem(key: string, value: any): boolean {
    if (!this.isClient()) {
      return false;
    }

    try {
      const serializedValue =
        typeof value === 'string' ? value : JSON.stringify(value);
      sessionStorage.setItem(key, serializedValue);
      return true;
    } catch (error) {
      console.warn(
        `SafeStorage: Failed to set sessionStorage item "${key}":`,
        error
      );
      return false;
    }
  }

  /**
   * 移除 sessionStorage 中的值
   * @param key 存储键
   * @returns 是否成功移除
   */
  static removeSessionItem(key: string): boolean {
    if (!this.isClient()) {
      return false;
    }

    try {
      sessionStorage.removeItem(key);
      return true;
    } catch (error) {
      console.warn(
        `SafeStorage: Failed to remove sessionStorage item "${key}":`,
        error
      );
      return false;
    }
  }

  /**
   * 获取 localStorage 中的值
   * @param key 存储键
   * @param defaultValue 默认值
   * @returns 存储的值或默认值
   */
  static getLocalItem<T = string>(
    key: string,
    defaultValue: T | null = null
  ): T | null {
    if (!this.isClient()) {
      return defaultValue;
    }

    try {
      const item = localStorage.getItem(key);
      if (item === null) {
        return defaultValue;
      }

      // 尝试解析 JSON，如果失败则返回原始字符串
      try {
        return JSON.parse(item) as T;
      } catch {
        return item as unknown as T;
      }
    } catch (error) {
      console.warn(
        `SafeStorage: Failed to get localStorage item "${key}":`,
        error
      );
      return defaultValue;
    }
  }

  /**
   * 设置 localStorage 中的值
   * @param key 存储键
   * @param value 要存储的值
   * @returns 是否成功设置
   */
  static setLocalItem(key: string, value: any): boolean {
    if (!this.isClient()) {
      return false;
    }

    try {
      const serializedValue =
        typeof value === 'string' ? value : JSON.stringify(value);
      localStorage.setItem(key, serializedValue);
      return true;
    } catch (error) {
      console.warn(
        `SafeStorage: Failed to set localStorage item "${key}":`,
        error
      );
      return false;
    }
  }

  /**
   * 移除 localStorage 中的值
   * @param key 存储键
   * @returns 是否成功移除
   */
  static removeLocalItem(key: string): boolean {
    if (!this.isClient()) {
      return false;
    }

    try {
      localStorage.removeItem(key);
      return true;
    } catch (error) {
      console.warn(
        `SafeStorage: Failed to remove localStorage item "${key}":`,
        error
      );
      return false;
    }
  }
}
