# CMDB 应用连接数据库与中间件

Status: implemented

## Problem Statement

应用拓扑只能沿「应用 → 主机 → 库/中间件」两跳推断依赖。共享库、独立 DB 主机和云 RDS 不会作为应用的消费对象出现，也无法反查「这套库连着哪些应用」。运维需要一条与组织树、进程落点分开的应用依赖关系。

## Solution

在应用模型上预置 `connect`（关联）到数据库、缓存、消息队列、注册中心、对象存储及云上同类，基数 n:n。不新增「访问」类型。服务树、主机挂载和扫描建边保持不变。实例关联页和应用拓扑沿用现有能力。

## User Stories

1. As an 运维人员, I want 在应用实例上把已有的 MySQL / Redis / 云 RDS 等依赖关联上去, so that 不必把库主机挂到应用上才能表达消费关系
2. As an 运维人员, I want 一套库可以同时关联多个应用, so that 共享依赖不必复制实例
3. As an 运维人员, I want 打开应用拓扑时从应用一跳看到这些依赖, so that 共享库和云库能进应用服务带
4. As an 运维人员, I want Tomcat / Nginx 以及 PDB、租户、节点等子对象不出现在应用可关联的依赖列表里, so that 运行载体和集群零件不会被当成被访问的服务

## Implementation Decisions

- 使用已有关联类型 `connect`，不新增 asst_id。种子写在应用模型的关联表，生成 `application_connect_<model_id>`，mapping 为 n:n。
- 接到运维认的服务身份模型，不接到集群内部子对象。纳入：数据库主模型、缓存、消息队列、注册中心、对象存储、云上同类实例。不纳入：Web 容器与负载均衡、Oracle 实例/PDB、OceanBase Zone/节点/租户、Nacos 节点/命名空间/服务、IBM MQ 通道/监听器/队列、HDFS/YARN/Storm/Ambari/Spark。
- 官方模型初始化按 `model_asst_id` 补缺边；已有 `application_run_host` 不变。第一期不写自动关联规则，扫描不生成消费边。
- 应用实例「添加关联」下拉按运行于优先、关联按名称排序，并支持搜索，避免 64 条 connect 无法选择。
- 服务树仍只到应用和主机。库/中间件不上组织树，也不改 `contains`。
- 应用拓扑仍按关联跳数展开；新边出现后即可从应用一跳落到应用服务带，不改展开器。

## Testing Decisions

- 好测试只验证：种子里应用对纳入模型是 `connect` + `n:n`；排除名单不出现；`application_run_host` 仍在；每个目标模型在 models 表存在；应用拓扑 depth=1 的 `application_connect_*` 不经过主机；添加关联下拉运行于优先。
- 约定接缝：应用模型关联种子、应用拓扑 hop 展开、添加关联下拉排序。
- Prior art：`test_service_tree_model_config.py` 的关联种子断言、`test_application_resource_overview_service.py` 的拓扑展开。

## Out of Scope

- 从扫描或同主机推断消费边
- 新关联类型「访问」
- 把库/中间件挂进服务树
- 给 Web 容器、负载均衡或集群子对象加 `connect`
- 专用依赖管理页面或反查报表

## Further Notes

- 工作名「应用依赖」；存储名是 `connect`，不要写成 contains 或 run。
- 存量环境需再跑一次官方模型初始化才会出现新模型关联。

## Completion Evidence

已实现并通过约定接缝测试。

- 种子：`asso-application` 保留 `application_run_host` n:n，并对纳入的数据库/中间件/云上同类补 `connect` n:n；排除 Web 容器、负载均衡和集群子对象。
- 拓扑：`application_connect_mysql` 在 depth=1 即可落到应用服务带，不经过主机。
- Web：应用实例添加关联支持搜索；运行于主机排在 connect 依赖之前。
- 验证：`test_application_connect_dependency_model_config.py`、`test_application_resource_overview_service.py`、`associationPicker.test.ts` 通过。
