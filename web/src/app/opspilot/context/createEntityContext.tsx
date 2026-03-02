'use client';

import React, { createContext, useContext, useState, useCallback, useEffect } from 'react';
import { useSearchParams } from 'next/navigation';

/**
 * 实体信息的基础接口
 */
export interface BaseEntityInfo {
  name: string;
  introduction: string;
}

/**
 * 实体 Context 的值类型（标准化）
 */
export interface EntityContextValue<T extends BaseEntityInfo> {
  entityInfo: T;
  isLoading: boolean;
  refreshEntityInfo: () => Promise<void>;
}

/**
 * 创建实体 Context 的配置选项
 */
export interface CreateEntityContextOptions<T extends BaseEntityInfo, R> {
  /** Context 名称，用于错误提示 */
  contextName: string;
  /** 获取详情的 API hook */
  useApi: () => { fetchDetail: (id: string) => Promise<R> };
  /** 将 API 响应转换为实体信息 */
  transformResponse: (data: R) => T;
  /** 默认的实体信息（当没有 id 时使用） */
  getDefaultInfo: (searchParams: URLSearchParams | null) => T;
}

/**
 * 创建实体 Context 的工厂函数
 * 用于减少 knowledge、skill、studio 等 Context 的重复代码
 *
 * @example
 * ```tsx
 * const { Provider: KnowledgeProvider, useEntity: useKnowledge } = createEntityContext({
 *   contextName: 'Knowledge',
 *   useApi: () => {
 *     const { fetchKnowledgeBaseDetails } = useKnowledgeApi();
 *     return { fetchDetail: (id) => fetchKnowledgeBaseDetails(Number(id)) };
 *   },
 *   transformResponse: (data) => ({
 *     name: data.name,
 *     introduction: data.introduction,
 *   }),
 *   getDefaultInfo: (searchParams) => ({
 *     name: searchParams?.get('name') || '',
 *     introduction: searchParams?.get('desc') || '',
 *   }),
 * });
 * ```
 */
export function createEntityContext<T extends BaseEntityInfo, R>(
  options: Omit<CreateEntityContextOptions<T, R>, 'entityInfoKey' | 'refreshKey'>
) {
  const {
    contextName,
    useApi,
    transformResponse,
    getDefaultInfo,
  } = options;

  const EntityContext = createContext<EntityContextValue<T> | null>(null);
  EntityContext.displayName = `${contextName}Context`;

  const Provider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
    const searchParams = useSearchParams();
    const id = searchParams?.get('id') || '';
    const { fetchDetail } = useApi();

    const [entityInfo, setEntityInfo] = useState<T>(() => getDefaultInfo(searchParams));
    const [isLoading, setIsLoading] = useState(true);

    const refreshEntityInfo = useCallback(async () => {
      if (!id) {
        setIsLoading(false);
        return;
      }

      try {
        setIsLoading(true);
        const data = await fetchDetail(id);
        setEntityInfo(transformResponse(data));
      } catch (error) {
        console.error(`Failed to fetch ${contextName.toLowerCase()} info:`, error);
      } finally {
        setIsLoading(false);
      }
    }, [id, fetchDetail]);

    useEffect(() => {
      refreshEntityInfo();
    }, [id]);

    return (
      <EntityContext.Provider value={{ entityInfo, isLoading, refreshEntityInfo }}>
        {children}
      </EntityContext.Provider>
    );
  };

  Provider.displayName = `${contextName}Provider`;

  const useEntity = (): EntityContextValue<T> => {
    const context = useContext(EntityContext);
    if (!context) {
      throw new Error(`use${contextName} must be used within a ${contextName}Provider`);
    }
    return context;
  };

  return {
    Provider,
    useEntity,
    Context: EntityContext,
  };
}

export default createEntityContext;
