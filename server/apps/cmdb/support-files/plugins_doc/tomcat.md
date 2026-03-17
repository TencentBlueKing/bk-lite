### 说明
基于脚本解析 server.xml 与 JVM 启动参数，采集版本、端口、堆/非堆内存及日志路径，同步至 CMDB。

### 前置要求
1. Tomcat 已运行

### 版本兼容性
- 兼容官方 Tomcat 7.x - Tomcat 11.x 版本（包括：8.5.x、9.0.x、10.1.x、11.0.x 等）。

### 采集内容
| Key 名称      | 含义                                 |
| :------------ | :----------------------------------- |
| inst_name     | 实例展示名：`{内网IP}-tomcat-{端口}` |
| obj_id        | 固定对象标识 tomcat                  |
| ip_addr       | 主机内网 IP                          |
| port          | 监听端口                             |
| catalina_path | 启动脚本路径                         |
| version       | Tomcat 版本                          |
| xms           | JVM 初始堆大小                       |
| xmx           | JVM 最大堆大小                       |
| max_perm_size | 最大非堆/元空间大小                  |
| permsize      | 初始非堆/元空间大小                  |
| log_path      | 主日志文件路径                       |
| java_version  | Java 版本                            |

> 补充说明：`version` 字段依次尝试通过 `${catalina_home}/bin/version.sh`、`${catalina_home}/bin/catalina.sh version` 以及 RPM/DEB 包信息推断，若均未获取到有效版本号则为空；`xms`、`xmx`、`max_perm_size`、`permsize` 仅在 JVM 启动参数或相关配置文件中显式设置对应参数时才有值，未配置会为空；`log_path` 默认指向 `${catalina_home}/logs/catalina.out`，当该文件不存在且在日志目录中无法找到 `catalina.out` 时会为空；