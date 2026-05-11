## 1. 后端：新增 by_vendor action

- [ ] 1.1 在 `LLMModelViewSet` 中新增 `by_vendor` action
- [ ] 1.2 在 `EmbedProviderViewSet` 中新增 `by_vendor` action
- [ ] 1.3 在 `RerankProviderViewSet` 中新增 `by_vendor` action
- [ ] 1.4 在 `OCRProviderViewSet` 中新增 `by_vendor` action

## 2. 前端：调用新接口

- [ ] 2.1 在 `provider.ts` 中新增 `fetchModelsByVendor` 方法
- [ ] 2.2 修改 `modelManagement.tsx` 使用新接口获取模型列表

## 3. 验证

- [ ] 3.1 后端 lint 检查通过
- [ ] 3.2 前端 type-check 通过
- [ ] 3.3 手动测试：供应商详情页能展示所有模型（不受模型 team 过滤）
- [ ] 3.4 手动测试：无权限的供应商返回空列表
