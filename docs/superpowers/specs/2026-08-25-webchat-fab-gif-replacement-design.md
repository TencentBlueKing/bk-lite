# WebChat 右下角悬浮 Logo GIF 替换设计

## 目标

将页面右下角 WebChat 悬浮入口当前使用的 `fab-dolphin.gif` 替换为已确认的第五版品牌动画，同时保持现有组件行为和静态降级资源不变。

## 修改范围

- 使用 `web/public/logo-site-animated-v5-brand.gif` 作为替换源。
- 将动画缩放为现有悬浮入口资产规格 128 × 128，保留透明背景、无限循环和帧时序。
- 同步覆盖以下两个同名 GIF，防止源码资产和已发布资产不一致：
  - `webchat/packages/webchat-ui/src/assets/fab-dolphin.gif`
  - `web/public/webchat/fab-dolphin.gif`
- 不修改 `fab-dolphin.png`、`PlatformChat.tsx`、按钮尺寸、位置、点击行为、焦点样式或聊天逻辑。

## 验收标准

- 两个目标 GIF 内容和校验值一致，均为 128 × 128、透明背景、无限循环动画。
- 页面正常动态模式下显示第五版品牌动画。
- 系统启用“减少动态效果”时继续使用原有 PNG，不受本次修改影响。
- WebChat 组件代码和页面布局无变化。
