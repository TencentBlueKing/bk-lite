'use client';

import { createContext, useContext } from 'react';

export type ShareCanvasDetailLoader = () => Promise<unknown>;

const ShareCanvasDetailContext = createContext<ShareCanvasDetailLoader | null>(null);

export const ShareCanvasDetailProvider = ShareCanvasDetailContext.Provider;

export const useShareCanvasDetailOverride = () => useContext(ShareCanvasDetailContext);
