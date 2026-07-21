'use client';

import { createContext, useContext } from 'react';

interface PluginGuideContextValue {
  openGuide: () => void;
  hasGuide: boolean;
}

const defaultValue: PluginGuideContextValue = {
  openGuide: () => {},
  hasGuide: false
};

export const PluginGuideContext = createContext<PluginGuideContextValue>(defaultValue);

export const usePluginGuide = (): PluginGuideContextValue => useContext(PluginGuideContext);
