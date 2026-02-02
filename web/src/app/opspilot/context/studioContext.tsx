'use client';

import React, { createContext, useContext, useState, useCallback, useEffect } from 'react';
import { useSearchParams } from 'next/navigation';
import { useStudioApi } from '@/app/opspilot/api/studio';

interface BotInfo {
  name: string;
  introduction: string;
  botType: number | null;
}

interface StudioContextType {
  botInfo: BotInfo;
  isLoading: boolean;
  refreshBotInfo: () => Promise<void>;
}

const StudioContext = createContext<StudioContextType | null>(null);

export const StudioProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const searchParams = useSearchParams();
  const id = searchParams?.get('id') || '';
  const { fetchBotDetail } = useStudioApi();

  const [botInfo, setBotInfo] = useState<BotInfo>({
    name: searchParams?.get('name') || '',
    introduction: searchParams?.get('desc') || '',
    botType: null,
  });
  const [isLoading, setIsLoading] = useState(true);

  const refreshBotInfo = useCallback(async () => {
    if (!id) {
      setIsLoading(false);
      return;
    }

    try {
      setIsLoading(true);
      const data = await fetchBotDetail(id);
      setBotInfo({
        name: data.name,
        introduction: data.introduction,
        botType: data.bot_type,
      });
    } catch (error) {
      console.error('Failed to fetch bot info:', error);
    } finally {
      setIsLoading(false);
    }
  }, [id, fetchBotDetail]);

  useEffect(() => {
    refreshBotInfo();
  }, [id]);

  return (
    <StudioContext.Provider value={{ botInfo, isLoading, refreshBotInfo }}>
      {children}
    </StudioContext.Provider>
  );
};

export const useStudio = () => {
  const context = useContext(StudioContext);
  if (!context) {
    throw new Error('useStudio must be used within a StudioProvider');
  }
  return context;
};
