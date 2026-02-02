'use client';

import React, { createContext, useContext, useState, useCallback, useEffect } from 'react';
import { useSearchParams } from 'next/navigation';
import { useSkillApi } from '@/app/opspilot/api/skill';

interface SkillInfo {
  name: string;
  introduction: string;
}

interface SkillContextType {
  skillInfo: SkillInfo;
  isLoading: boolean;
  refreshSkillInfo: () => Promise<void>;
}

const SkillContext = createContext<SkillContextType | null>(null);

export const SkillProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const searchParams = useSearchParams();
  const id = searchParams?.get('id') || '';
  const { fetchSkillDetail } = useSkillApi();

  const [skillInfo, setSkillInfo] = useState<SkillInfo>({
    name: searchParams?.get('name') || '',
    introduction: searchParams?.get('desc') || '',
  });
  const [isLoading, setIsLoading] = useState(true);

  const refreshSkillInfo = useCallback(async () => {
    if (!id) {
      setIsLoading(false);
      return;
    }

    try {
      setIsLoading(true);
      const data = await fetchSkillDetail(id);
      setSkillInfo({
        name: data.name,
        introduction: data.introduction || data.desc || '',
      });
    } catch (error) {
      console.error('Failed to fetch skill info:', error);
    } finally {
      setIsLoading(false);
    }
  }, [id, fetchSkillDetail]);

  useEffect(() => {
    refreshSkillInfo();
  }, [id]);

  return (
    <SkillContext.Provider value={{ skillInfo, isLoading, refreshSkillInfo }}>
      {children}
    </SkillContext.Provider>
  );
};

export const useSkill = () => {
  const context = useContext(SkillContext);
  if (!context) {
    throw new Error('useSkill must be used within a SkillProvider');
  }
  return context;
};
