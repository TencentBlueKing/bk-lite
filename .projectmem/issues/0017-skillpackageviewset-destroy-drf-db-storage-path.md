# #0017 SkillPackageViewSet.destroy 走 DRF 默认实现只删 DB 行,留下磁盘上的 storage_path 孤儿

- 2026-07-09T08:02:53Z `issue`: SkillPackageViewSet.destroy 走 DRF 默认实现只删 DB 行,留下磁盘上的 storage_path 孤儿 [server/apps/opspilot/viewsets/llm_view.py:729-731]
- 2026-07-09T09:08:10Z `attempt`: Expanded the user-profile family story with a nested verification workflow callout so UserInformation's email/password verification branches are part of the Storybook contract without creating shadow stories. [web/src/stories/system-manager-user-profile-family.stories.tsx] (worked)
- 2026-07-09T09:08:38Z `fix`: SystemManager user-profile family now documents UserInformation's nested verification workflow, and the updated family story linted cleanly with a clean diff check. [web/src/stories/system-manager-user-profile-family.stories.tsx]
