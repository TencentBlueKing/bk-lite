Feature: API Secret 管理
  作为一个已认证用户
  我需要管理我的 API 密钥
  以便通过 API 访问系统

  Scenario: 用户创建 API Secret
    Given 一个已认证的用户属于团队 1
    When 用户请求创建 API Secret
    Then 返回 201 状态码
    And 响应包含有效的 api_secret

  Scenario: 用户不能重复创建 API Secret
    Given 一个已认证的用户属于团队 1
    And 该用户已有一个 API Secret
    When 用户请求创建 API Secret
    Then 返回失败响应

  Scenario: 用户只能查看自己的 API Secret
    Given 一个已认证的用户属于团队 1
    And 该用户有一个 API Secret
    And 另一个用户也有一个 API Secret
    When 用户请求列出 API Secrets
    Then 只返回该用户的 API Secret

  Scenario: 完整生命周期
    Given 一个已认证的用户属于团队 1
    When 用户请求创建 API Secret
    Then 返回 201 状态码
    When 用户请求列出 API Secrets
    Then 列表包含 1 条记录
    When 用户请求删除该 API Secret
    Then 返回 204 状态码
    When 用户请求列出 API Secrets
    Then 列表为空

  Scenario: 多团队隔离
    Given 一个已认证的用户属于团队 1
    And 该用户在团队 1 有一个 API Secret
    And 该用户在团队 2 也有一个 API Secret
    When 用户以团队 1 请求列出 API Secrets
    Then 只返回团队 1 的 API Secret
    When 用户以团队 2 请求列出 API Secrets
    Then 只返回团队 2 的 API Secret
