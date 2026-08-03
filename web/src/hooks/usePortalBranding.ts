'use client';

import { useEffect, useMemo, useState } from 'react';
import {
  PORTAL_BRANDING_CACHE_KEY,
  readJsonCache,
  writeJsonCache,
} from '@/utils/portalTabTitle';

const DEFAULT_PORTAL_NAME = 'BlueKing Lite';
const DEFAULT_PORTAL_LOGO_URL = '/logo-site.png';
const DEFAULT_PORTAL_FAVICON_URL = '/logo-site.png';
const DEFAULT_WATERMARK_TEXT = 'BlueKing Lite · ${username} · ${date}';
const PORTAL_BRANDING_EVENT = 'portal-branding-updated';

export interface PortalBrandingState {
  portalName: string;
  logoUrl: string;
  faviconUrl: string;
  watermarkEnabled: boolean;
  watermarkText: string;
}

const DEFAULT_STATE: PortalBrandingState = {
  portalName: DEFAULT_PORTAL_NAME,
  logoUrl: DEFAULT_PORTAL_LOGO_URL,
  faviconUrl: DEFAULT_PORTAL_FAVICON_URL,
  watermarkEnabled: false,
  watermarkText: DEFAULT_WATERMARK_TEXT,
};

const resolveUrl = (value?: string, fallback = DEFAULT_PORTAL_LOGO_URL) => {
  const normalizedValue = value?.trim();
  return normalizedValue || fallback;
};

const normalizeBranding = (settings?: {
  portal_name?: string;
  portal_logo_url?: string;
  portal_favicon_url?: string;
  watermark_enabled?: string;
  watermark_text?: string;
}): PortalBrandingState => ({
  portalName: settings?.portal_name?.trim() || DEFAULT_PORTAL_NAME,
  logoUrl: resolveUrl(settings?.portal_logo_url, DEFAULT_PORTAL_LOGO_URL),
  faviconUrl: resolveUrl(settings?.portal_favicon_url, DEFAULT_PORTAL_FAVICON_URL),
  watermarkEnabled: settings?.watermark_enabled === '1',
  watermarkText: settings?.watermark_text?.trim() || DEFAULT_WATERMARK_TEXT,
});

const readCachedBranding = (): PortalBrandingState | null => {
  const cached = readJsonCache<Partial<PortalBrandingState>>(PORTAL_BRANDING_CACHE_KEY);
  if (!cached?.portalName) {
    return null;
  }
  return {
    ...DEFAULT_STATE,
    ...cached,
  };
};

const persistBranding = (branding: PortalBrandingState) => {
  writeJsonCache(PORTAL_BRANDING_CACHE_KEY, branding);
};

export const emitPortalBrandingUpdated = (branding: Partial<PortalBrandingState>) => {
  if (typeof window === 'undefined') {
    return;
  }

  window.dispatchEvent(new CustomEvent<Partial<PortalBrandingState>>(PORTAL_BRANDING_EVENT, {
    detail: branding,
  }));
};

export const usePortalBranding = () => {
  const [branding, setBranding] = useState<PortalBrandingState>(DEFAULT_STATE);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    let cancelled = false;

    const cachedBranding = readCachedBranding();
    if (cachedBranding) {
      setBranding(cachedBranding);
      setReady(true);
    }

    const fetchBranding = async () => {
      try {
        const response = await fetch('/api/proxy/core/api/get_bk_settings/', {
          cache: 'no-store',
        });

        if (!response.ok) {
          if (!cancelled) {
            setBranding(DEFAULT_STATE);
            persistBranding(DEFAULT_STATE);
            setReady(true);
          }
          return;
        }

        const payload = await response.json();
        const settings = payload?.data || {};

        if (!payload?.result || cancelled) {
          if (!cancelled) {
            setReady(true);
          }
          return;
        }

        const nextBranding = normalizeBranding(settings);
        setBranding(nextBranding);
        persistBranding(nextBranding);
        setReady(true);
      } catch {
        if (!cancelled) {
          setBranding(DEFAULT_STATE);
          persistBranding(DEFAULT_STATE);
          setReady(true);
        }
      }
    };

    fetchBranding();

    const handleBrandingUpdated = (event: Event) => {
      const nextBranding = (event as CustomEvent<Partial<PortalBrandingState>>).detail;
      if (!nextBranding || cancelled) {
        return;
      }

      setBranding((previousBranding) => {
        const merged = {
          ...previousBranding,
          ...nextBranding,
        };
        persistBranding(merged);
        return merged;
      });
      setReady(true);
    };

    window.addEventListener(PORTAL_BRANDING_EVENT, handleBrandingUpdated as EventListener);

    return () => {
      cancelled = true;
      window.removeEventListener(PORTAL_BRANDING_EVENT, handleBrandingUpdated as EventListener);
    };
  }, []);

  return useMemo(() => ({ ...branding, ready }), [branding, ready]);
};

export const portalBrandingDefaults = {
  portalName: DEFAULT_PORTAL_NAME,
  logoUrl: DEFAULT_PORTAL_LOGO_URL,
  faviconUrl: DEFAULT_PORTAL_FAVICON_URL,
  watermarkEnabled: false,
  watermarkText: DEFAULT_WATERMARK_TEXT,
};
