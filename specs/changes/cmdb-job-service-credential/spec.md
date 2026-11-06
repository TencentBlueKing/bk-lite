# 脚本采集的服务凭据与容器分支

Status: implemented

日期：2026-11-05。已按本文实施。未提交。

## Completion evidence

- 凭据下发：`server/apps/cmdb/tests/test_job_service_credential.py` 2 项通过。服务口令在节点参数里是 `${PASSWORD_service_password_...}`，明文只在环境配置；SSH 密码不被覆盖。`encrypted_fields` 含 `service_password`。编辑掩码保留原口令的用例在 `test_credential_delivery_pipeline.py` 中通过。同一文件里带数据库的纵向用例在本机 sqlite 迁移时失败，错误是 `NewSessionEventRelation has no field named 'event'`，既有用例同样失败，不是这次改动引入的。
- 执行请求：`agents/stargazer/tests/test_job_credential_route.py` 通过。本机和 SSH 都把 `service_password` 映射为 `REDISCLI_AUTH`，SSH 密码和 SSH 账号不会变成 Redis 凭据。MongoDB 半套凭据不注入。调试日志不含口令。
- SSH 远程注入：`agents/nats-executor/ssh/executor_test.go` 的 `TestRemoteCommandWithServiceEnvKeepsSecretOutOfTheCommand` 通过。包装命令不含口令，口令只在 stdin 的 base64 里。
- Redis 脚本：`tests/test_redis_discover_output.py` 通过。宿主机 `redis-server` 不进容器；`docker-proxy` 且宿主机登录失败时进容器并采到连接数、内存和角色，docker 参数不含口令；没有 docker 时保留宿主机结果且退出成功。
- MongoDB 脚本：`tests/test_mongodb_discover_output.py` 通过。容器路径读到版本、连接数、fork、日志路径、数据路径；无口令时角色为空，成对口令时角色有值；docker 参数和 eval 文本不含口令。
- 页面：Redis / MongoDB 的说明与登录提示测试通过。主机 JOB 原有提示文案断言 `已接入可用 Agent` 与当前文案不一致，改动前就是这样，这次没有改那句文案。
- 10.10.41.149（`ssh lite`，主机名 `weops-lite`）：脚本只放到 `/tmp` 后跑完即删，没有改容器或配置。6379 的监听是 `docker-proxy`，无口令 `PING` 为 `NOAUTH`，脚本退出 0，只采到版本 7.4.10，连接数、内存和角色为空。6389 的 `verify-redis` 无口令即可登录，容器分支采到版本 7.4.10、安装路径 `/data/redis-server`、最大连接 10000、内存 0、角色 master。这台机器没有 MongoDB 容器；修正「没有 sh 的容器被当成 MongoDB」后，脚本退出 0 且没有输出。

## Problem Statement

Redis、MongoDB 这类脚本采集，页面只收一套 SSH 登录凭据。Redis 开了访问口令、MongoDB 开了认证时，脚本登录不了服务，版本或角色采不全。插件说明把「密码」写成 Redis 口令，对象目录和表单却把它当成 SSH 密码、端口写成 22，两个意思叠在同一个字段上。

同一批脚本只扫描宿主机进程和本机文件。服务装在本机 Docker 容器里时，宿主机上看不到服务进程，端口上通常是 `docker-proxy`，配置和客户端都在容器里。Redis 现有容器逻辑只在登录失败后补版本，连接数、内存上限和角色仍然空着。

## Solution

SSH 账号、密码和端口继续只负责登录目标机。Redis 和 MongoDB 在同一条凭据上另加服务凭据。服务口令不写进脚本正文，也不做脚本文本占位符替换。采集配置里仍用现有的环境变量占位把明文送到 Stargazer，Stargazer 再把字段映射成脚本进程的环境变量。

容器和本机共用同一份脚本、同一套输出字段。先走现有宿主机查找。宿主机上没有真正的服务进程，或监听进程是 `docker-proxy` 时，再进入对应容器执行同一组只读命令。用户不选择安装方式。

## User Stories

1. As a 采集配置人员, I want Redis 任务在 SSH 凭据之外单独填写 Redis 口令和可选 ACL 用户名, so that 开了访问控制的实例能采到连接数、内存上限和角色。
2. As a 采集配置人员, I want 不填 Redis 服务口令时任务仍能采集无口令实例, so that 没有访问控制的实例不用多填一项。
3. As a 采集配置人员, I want MongoDB 的用户名和口令成对填写、认证库可以省略, so that 开了认证的副本集能采到角色，没开认证的实例仍按现在的方式读配置。
4. As a 采集配置人员, I want 已经保存的 SSH 密码保持为登录密码, so that 拆字段后旧任务的登录不被改写成服务口令。
5. As a 运维人员, I want 装了控制器的本机执行和未装控制器的 SSH 远程都能把服务口令交给脚本, so that 两种执行方式采到的服务字段一致。
6. As a 运维人员, I want Redis 或 MongoDB 装在本机容器里时仍得到和宿主机安装相同的字段, so that 安装位置不影响入库结果。
7. As a 运维人员, I want 目标机没有 docker 命令或当前用户不能执行 docker 时保留宿主机采集结果, so that 容器探测失败不会把整机采集判失败。
8. As a 安全审计人员, I want 服务口令只出现在加密存储、下发环境变量和执行进程环境中, so that 脚本文件、命令参数、采集日志和指标标签里没有口令。

## Implementation Decisions

- 第一批只改 Redis 和 MongoDB。RabbitMQ、DB2、达梦、IBM MQ 的脚本不读取账号口令，本期不加服务口令字段。
- 服务凭据和 SSH 凭据放在同一条凭据对象里，沿用「SSH 密码之外另有一个加密字段」的现有做法。新增口令进入该对象的加密字段。SSH 的 `password` 继续只表示登录口令。
- Redis 增加可选服务口令和可选 ACL 用户名。MongoDB 增加可选用户名、可选口令、可选认证库。认证库不填时按 `admin`。MongoDB 用户名和口令必须成对；只填其中一个视为未提供服务凭据。
- 不加服务端口。端口仍由脚本发现。Redis 继续扫描现有默认端口列表。
- 下发链路不改形状。采集配置正文里，服务口令是 `${PASSWORD_...}` 这种环境变量占位，明文只在节点环境配置中。Telegraf 展开后再交给 Stargazer。Stargazer 得到的是内存中的服务口令字段。
- 脚本文件不做占位符替换。自定义脚本的 `{{credential.*}}` 不用于这两个内置插件。
- Stargazer 在执行请求上做字段映射，不改脚本内容：
  - Redis 服务口令映射为 `REDISCLI_AUTH`。ACL 用户名只有非空时映射为 `REDIS_USER`。SSH 账号不得映射为 `REDIS_USER`。
  - MongoDB 用户名、口令和认证库映射为脚本读取的一组环境变量，只用于现有的角色查询。
- 空值、纯空白，以及仍是 `${...}` 的未展开占位，都不注入。
- 本机执行沿用执行请求里已有的环境变量字段，由本机执行器放进子进程环境。脚本和 `redis-cli` 继承该环境。`redis-cli` 读取 `REDISCLI_AUTH`，命令参数中不出现口令。
- SSH 远程执行请求补上与本机执行相同形状的环境变量字段。执行器把变量放进远程进程环境。调试日志和流式日志里的命令文本只有脚本正文。目标 sshd 默认不接受会话级环境变量，因此不得改客户机 sshd 配置来完成注入，也不得把带口令的 `export` 写进会被记录的命令字符串。口令可以存在于执行进程自己的环境中，这和 `REDISCLI_AUTH` 的用法一致；不得出现在 `redis-cli` 或 `mongo` 的命令参数里，也不得拼进 `mongo` 的 eval 文本。现有客户端做不到这一点时，对应字段留空，不退回命令行传口令。
- 工作区里已有的临时行为删除：不得再把 SSH 密码映射成 `REDISCLI_AUTH`。
- 旧任务不迁移。原来的 `password` 仍是 SSH 密码。需要服务口令的任务在新字段里重新填写。
- 容器与本机共用同一份发现脚本和同一套 JSON 字段。查找顺序固定：
  1. 现有宿主机进程、`/proc` 和本机文件路径。找到真正的服务进程时走这条路径，输出与现在的宿主机安装一致。
  2. 没有真正的服务进程，或端口监听进程是 `docker-proxy` 时，用已发布端口确定容器，在容器内执行同一组只读命令。
  3. 没有 docker 命令，或当前用户不能执行 docker 时，保留第 1 步的结果。不把这次采集标记为失败。
- 进入容器时，服务凭据用「只带变量名、从当前进程环境取值」的方式传进容器。容器内命令参数同样不包含口令值。
- Redis 容器分支要补齐现在缺失的部分：容器内能登录时采集 `INFO`、`CONFIG GET` 和角色。只拿 `redis-server --version` 不够。宿主机 `redis-cli` 已经能登录已发布端口时，不必再进容器。
- MongoDB 容器分支要在容器内读配置并做角色查询。宿主机上看不到 `mongod` 时，今天脚本没有输出；容器分支成功时输出与宿主机安装相同的字段。
- 插件说明改成与表单一致：SSH 字段是登录凭据；服务口令是另一组字段；装了控制器时登录凭据可以不填，服务口令仍然要填。端口说明不再把 SSH 的 22 和 Redis 的 6379 写成同一个字段。

## Testing Decisions

好的测试只锁外部行为：凭据如何离开任务、执行请求里有什么、脚本输出的字段是什么、日志和命令文本里没有口令。不锁内部函数拆分。

- 凭据下发：沿用现有「落库、节点参数、Stargazer 最终参数」纵向测试。服务口令在配置正文中是环境变量占位，明文只在环境配置里；SSH 密码字段不被服务口令覆盖。
- 执行请求：本机执行和 SSH 远程都断言环境变量映射、命令正文不含口令、SSH 账号不会变成 Redis ACL 用户。覆盖空值、空白和未展开占位。MongoDB 只填用户名或只填口令时，请求里不带半套服务凭据。
- Redis 脚本：用假的 `redis-cli`。无口令时连接数、内存上限、角色为空；有对应环境变量时这些字段被填上。假 docker 覆盖三条路径：宿主机已有 `redis-server` 时不进容器；监听进程是 `docker-proxy` 且宿主机登录失败时进容器并采到上述字段；没有 docker 命令时保留宿主机结果且退出成功。
- MongoDB 脚本：用假的 `mongo` 和假 docker。无认证信息时角色为空、其余配置字段仍在；成对凭据时角色有值；容器路径与宿主机路径输出相同字段。断言命令参数和 eval 文本不含口令。
- 日志：执行调试日志的命令模板不包含口令值。沿用现有日志回归的哨兵断言方式。

## Out of Scope

- RabbitMQ、DB2、达梦企业版、IBM MQ 的服务口令字段。它们本期也不做容器分支。
- Nginx、Kafka、Elasticsearch、Tomcat 等其余只扫描宿主机进程的脚本。容器分支以后按同一顺序加，不在本期。
- 每个插件两份脚本，或让用户选择「本机安装 / 容器安装」。
- 服务端口字段，以及用该字段替换脚本的端口发现。
- 把旧 SSH 密码自动抄进服务口令。
- 自定义脚本的占位符注入。
- 协议采集（MySQL、PostgreSQL 等）、主机、物理机、配置文件、Windows 角色、Docker 引擎自身，以及企业版占位脚本。
- Podman、containerd 和 Kubernetes。本期容器只认本机 Docker。

## Further Notes

- 页面文案要让人看出两组凭据的差别：一组登录目标机，一组登录 Redis 或 MongoDB。装了控制器时可以不填登录凭据，这句话不能再理解成服务口令也可以不填。
- 达梦企业版若以后要支持「操作系统信任登录失败、必须提供 SYSDBA 口令」，另开变更。本期不预留该字段。
