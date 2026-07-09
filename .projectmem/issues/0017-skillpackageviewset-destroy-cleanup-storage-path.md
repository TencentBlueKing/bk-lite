# #0017 SkillPackageViewSet.destroy 漏磁盘清理:删 DB 行后没 rmtree storage_path

- 2026-07-09T08:02:53Z `issue`: SkillPackageViewSet.destroy 走 DRF 默认实现只删 DB 行,留下磁盘上的 storage_path 孤儿 [server/apps/opspilot/viewsets/llm_view.py:729-731]
- 2026-07-09T08:02:53Z `fix`(事件流里挂在 #0013 上,内容是这个 issue 的): override destroy,DB 删完顺手调 _cleanup_storage_path 用 shutil.rmtree 清磁盘;带 safety check(路径必须在 DEFAULT_SKILL_PACKAGE_ROOT 之下),抽成 static method 方便单测 [server/apps/opspilot/viewsets/llm_view.py:692-727; tests/test_llm_viewset_views.py:377-403]
- 2026-07-09T08:20:39Z `fix`(事件流里挂在 #0013 上,内容是这个 issue 的): 把原 viewset 里那个只调 super().destroy() 的旧 destroy 删了,留下唯一的就是带 _cleanup_storage_path 的版本。之前 bug 是两个 destroy 同名,Python 取后一个,导致 _cleanup_storage_path 永远跑不到 [server/apps/opspilot/viewsets/llm_view.py:760-762 (removed)]
- 2026-07-09T08:30:xxZ `decision`: 同一 bug,fix 历史已落到上述 #0013-attached 两条 fix 事件里,把 #0017 重新作为这个问题的归属 issue

## Notes
- 修复前:**两个同名 `destroy` 共存于 SkillPackageViewSet**,Python 取最后一个定义,所以新加的 `_cleanup_storage_path` 永远跑不到。修法是删旧的留新的
- 修后:destroy 是唯一的,DB 行 + 磁盘目录都清;safety check 确保只在 `DEFAULT_SKILL_PACKAGE_ROOT` 之下删
- 3 个单元测试覆盖(`test_skill_package_cleanup_storage_path_*`):root 内删 / 拒绝 root 外 / 空字符串 noop
