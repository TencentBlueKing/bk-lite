// 架构图相关工具函数：传入完整资源路径，例如 /assets/icons-realistic/cc-host_主机.svg
export const svgToBase64 = async (svgUrl: string): Promise<string> => {
  try {
    const response = await fetch(svgUrl);
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
