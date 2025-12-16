## 说明
基于脚本解析 server.xml 与 JVM 启动参数，采集版本、端口、堆/非堆内存及日志路径，同步至 CMDB。

## 前置要求
1. Tomcat 已运行

## 采集内容
| Key 名称 | 含义 |
| :----------- | :--- |
| inst_name | 实例展示名：`{内网IP}-tomcat-{端口}` |
| obj_id | 固定对象标识 tomcat |
| ip_addr | 主机内网 IP |
| port | 监听端口（Connector 提取） |
| catalina_path | 启动脚本路径（catalina.sh） |
| version | Tomcat 版本（version.sh） |
| xms | JVM 初始堆大小 (-Xms) |
| xmx | JVM 最大堆大小 (-Xmx) |
| max_perm_size | 最大非堆/元空间大小 (MaxMetaspaceSize/MaxPermSize) |
| permsize | 初始非堆/元空间大小 (MetaspaceSize/PermSize) |
| log_path | 主日志文件路径（catalina.out） |
| java_version | Java 版本（java -version） |