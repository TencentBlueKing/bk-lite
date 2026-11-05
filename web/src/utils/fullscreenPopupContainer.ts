/** 浏览器全屏时浮层必须挂进全屏节点，否则会被挡住。未全屏时仍挂到 body。 */
export const fullscreenPopupContainer = (): HTMLElement => {
  const element = document.fullscreenElement;
  return element instanceof HTMLElement ? element : document.body;
};
