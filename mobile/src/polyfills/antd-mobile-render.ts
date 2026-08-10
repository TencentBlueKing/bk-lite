/**
 * antd-mobile 命令式 API（Dialog / Toast / ActionSheet 等）依赖 renderToBody。
 * 1) 用 unstableSetRender 注入 createRoot，避免挂出空容器；
 * 2) 同步写入 rc-util 的 root 标记，避免关闭弹层时仍走
 *    legacyUnmount → unmountComponentAtNode is not a function。
 */
import { unstableSetRender } from 'antd-mobile';
import { createRoot, type Root } from 'react-dom/client';

type Host = Element & { __rc_react_root__?: Root };

const MARK = '__rc_react_root__' as const;

unstableSetRender((node, container) => {
  const host = container as Host;
  const root = host[MARK] ?? createRoot(host);
  host[MARK] = root;
  root.render(node);
  return async () => {
    root.unmount();
    delete host[MARK];
  };
});
