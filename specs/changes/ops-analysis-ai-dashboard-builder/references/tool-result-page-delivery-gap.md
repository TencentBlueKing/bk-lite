# 工具结果到仪表盘页面的传递缺口

## 当前状态

运营分析工具在校验成功后返回以下结构。对话引擎的规划器、执行节点和总结器没有运营分析特判，也不会在模型未调用工具时补调检索或校验。

```json
{
  "success": true,
  "data": {
    "ok": true,
    "proposal": {},
    "pageAction": {
      "name": "dashboard_config_apply",
      "value": {
        "dashboardId": "current",
        "proposal": {}
      }
    }
  }
}
```

页面已经具备方案转换、编辑态和撤销。编辑页订阅 `prepare_dashboard_proposal` 的原始结果，`readDashboardApplyAction` 确认动作名是 `dashboard_config_apply` 且目标是当前仪表盘后，写入编辑态。保存仍由页面上的「保存」完成。WebChat 只转交已完成的工具名、调用 ID 和原始结果，不解释业务字段。

## 交接边界

- 检索和校验只走运营分析的两个 NATS 接口。
- 工具只执行调用方传入的参数。
- 把已完成的工具结果交给编辑页，需要另作交付，不能改规划器或执行节点，也不能为这一个工具改 WebChat 协议。
- 模型没有调用 `prepare_dashboard_proposal` 时，页面不改画布。
