## 说明
基于脚本（JOB）解析 ActiveMQ 运行进程与配置文件，自动采集实例核心参数并同步至 CMDB。

## 前置要求
1. ActiveMQ 已部署并启动


## 采集内容
| Key 名称     | 含义 |
| :----------- | :--- |
| inst_name    | 内网IP-activemq-端口 |
| install_path | 进程当前工作目录 |
| port         | 监听端口（activemq.xml，缺省 61616） |
| user         | 运行进程的系统用户 |
| conf_path    | 配置目录（-Dactivemq.conf 或 base_path/conf） |
| java_path    | Java 可执行路径 |
| ip_addr      | 主机内网 IP |
| java_version | JDK 版本 |
| version      | ActiveMQ 版本 |
| xms          | JVM 初始堆大小 |
| xmx          | JVM 最大堆大小 |