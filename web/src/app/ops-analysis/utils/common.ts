// 架构图相关工具函数
import type { IconWithSize } from '@/app/ops-analysis/types';

export const svgToBase64 = async (svgPath: string): Promise<string> => {
  try {
    const response = await fetch(`/app/assets/assetModelIcon/${svgPath}.svg`);
    const svgText = await response.text();
    const base64 = btoa(unescape(encodeURIComponent(svgText)));
    return `data:image/svg+xml;base64,${base64}`;
  } catch {
    const fallbackSvg =
      '<svg width="24" height="24" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg"><rect width="24" height="24" fill="#e0e0e0"/><text x="12" y="12" text-anchor="middle" dominant-baseline="middle" font-size="8" fill="#666">?</text></svg>';
    const fallbackBase64 = btoa(unescape(encodeURIComponent(fallbackSvg)));
    return `data:image/svg+xml;base64,${fallbackBase64}`;
  }
};

export const patchIconSize = (icon: IconWithSize) => ({
  ...icon,
  width: icon.width || icon.size || 48,
  height: icon.height || icon.size || 48,
});
