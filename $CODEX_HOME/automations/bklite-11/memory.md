2026-05-13: 完成 bk-lite alerts Alert/Incident 权限全量审查。节假日门禁通过，已在 /Volumes/Disk/codespaces/bk-lite 执行 git pull 并确认 HEAD=d6ba0e3dfbdd073d30370582c6988fbd20301ac5。去重后确认 2832/2833 覆盖的是旧版未收口问题；当前 HEAD 新增独立根因是 operator 被权限 helper 视为授权来源，但 Alert 分派/转派与 Incident 创建/更新允许跨组织写入任意用户名，导致主动扩权查看与处置。已创建 issue #2929 并确认 assignee=zhaojinmeng，已发送 BKLite 小助手通知。未再发现第二个同等级独立权限根因。
运行时间: 约 24 分钟
