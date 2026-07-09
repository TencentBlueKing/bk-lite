# #0012 deep_wrapper_node 是 async 节点,但 _post_process_tool_results 走的是同步 dispatch_custom_event,导致 report 事件因缺 parent run id 静默失败

- 2026-07-09T04:03:21Z `issue`: deep_wrapper_node 是 async 节点,但 _post_process_tool_results 走的是同步 dispatch_custom_event,导致 report 事件因缺 parent run id 静默失败 [server/apps/opspilot/metis/llm/chain/node.py:856-862,2660-2723]
- 2026-07-09T04:03:21Z `attempt`: 让 _post_process_tool_results/_emit_report_event 接受可选的 event_dispatcher 回调,deep_wrapper_node 传入带 config 的 adispatch_custom_event 协程,这样 report 事件能正确 emit [server/apps/opspilot/metis/llm/chain/node.py:825-862,945-948,950-1006,2680-2723] (worked)
- 2026-07-09T04:03:21Z `fix`: async 包装节点里改用 adispatch_custom_event(..., config=config) emit 事件;同步路径仍走 dispatch_custom_event,行为兼容 [server/apps/opspilot/metis/llm/chain/node.py:825-862,945-948,950-1006,2680-2723]
- 2026-07-09T06:05:33Z `attempt`: report_file_download 也改成走 event_dispatcher,async 上下文里事件不再被吞,ReportDownloadCard 应能正常渲染 [server/apps/opspilot/metis/llm/chain/node.py:1020-1040] (worked)
