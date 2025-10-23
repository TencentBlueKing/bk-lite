### Auditbeat auditd简介

- &zwnj;**基本功能**&zwnj;
  - 安全事件采集

  - 规则管理

  - 实时传输

  - 系统调用监控

- &zwnj;**主要特点**&zwnj;
  - auditd 的轻量替代方案

  - 安全审计与合规

  - 灵活的规则配置

  - 丰富的上下文信息

  - Elastic Stack 集成

  - 典型应用场景

### Auditbeat auditd 输出字段


|分组名|字段名（完整）|字段介绍（中文）|类型|
|--------|------|------|--------|
|内置字段|collect_type|采集类型|-|
|内置字段|collector|采集器|-|
|内置字段|instance_id|实例id|-|
|user|user.auid|审计用户ID|alias|
|user|user.uid|用户ID|alias|
|user|user.fsuid|文件系统用户ID|alias|
|user|user.suid|保存的用户ID|alias|
|user|user.gid|用户组ID|alias|
|user|user.sgid|保存的组ID|alias|
|user|user.fsgid|文件系统组ID|alias|
|user.name_map|user.name_map.auid|审计用户名|alias|
|user.name_map|user.name_map.uid|用户名|alias|
|user.name_map|user.name_map.fsuid|文件系统用户名|alias|
|user.name_map|user.name_map.suid|保存的用户名|alias|
|user.name_map|user.name_map.gid|用户组名|alias|
|user.name_map|user.name_map.sgid|保存的组名|alias|
|user.name_map|user.name_map.fsgid|文件系统组名|alias|
|selinux|user.selinux.user|提交认证的SELinux用户|keyword|
|selinux|user.selinux.role|SELinux角色|keyword|
|selinux|user.selinux.domain|SELinux域/类型|keyword|
|selinux|user.selinux.level|SELinux等级|keyword|
|selinux|user.selinux.category|SELinux类别/隔离区|keyword|
|process|process.cwd|当前工作目录|alias|
|source|source.path|UNIX套接字路径|keyword|
|destination|destination.path|UNIX套接字路径|keyword|
|auditd|auditd.message_type|审计消息类型|keyword|
|auditd|auditd.sequence|内核分配的事件序列号|long|
|auditd|auditd.session|登录会话ID|keyword|
|auditd|auditd.result|审计操作结果（成功/失败）|keyword|
|actor|auditd.summary.actor.primary|主身份（原始登录ID）|keyword|
|actor|auditd.summary.actor.secondary|次身份（su切换时可能不同）|keyword|
|object|auditd.summary.object.type|对象类型（如文件、套接字、用户会话）|keyword|
|object|auditd.summary.object.primary|主对象标识|keyword|
|object|auditd.summary.object.secondary|次对象标识|keyword|
|object|auditd.summary.how|执行动作方式（命令/可执行文件）|keyword|
|paths|auditd.paths.inode|inode编号|keyword|
|paths|auditd.paths.dev|设备名（/dev下）|keyword|
|paths|auditd.paths.obj_user|对象用户|keyword|
|paths|auditd.paths.obj_role|对象角色|keyword|
|paths|auditd.paths.obj_domain|对象域|keyword|
|paths|auditd.paths.obj_level|对象级别|keyword|
|paths|auditd.paths.objtype|对象类型|keyword|
|paths|auditd.paths.ouid|文件所有者用户ID|keyword|
|paths|auditd.paths.rdev|特殊文件设备标识符|keyword|
|paths|auditd.paths.nametype|文件操作类型|keyword|
|paths|auditd.paths.ogid|文件所有者组ID|keyword|
|paths|auditd.paths.item|被记录的项|keyword|
|paths|auditd.paths.mode|文件模式标志|keyword|
|paths|auditd.paths.name|文件名（AVCS）|keyword|
|data|auditd.data.action|netfilter数据包处理结果|keyword|
|data|auditd.data.minor|设备次编号|keyword|
|data|auditd.data.acct|用户账户名|keyword|
|data|auditd.data.addr|用户连接的远程地址|keyword|
|data|auditd.data.cipher|使用的加密算法|keyword|
|data|auditd.data.id|账户变更期间ID|keyword|
|data|auditd.data.entries|netfilter表中的条目数量|keyword|
|data|auditd.data.kind|加密操作的客户端或服务器|keyword|
|data|auditd.data.ksize|加密操作的密钥大小|keyword|
|data|auditd.data.spid|发送进程ID|keyword|
|data|auditd.data.arch|ELF架构标志|keyword|
|data|auditd.data.argc|execve系统调用的参数数量|keyword|
|data|auditd.data.major|设备主编号|keyword|
|data|auditd.data.unit|systemd单元|keyword|
|data|auditd.data.table|netfilter表名|keyword|
|data|auditd.data.terminal|用户运行程序的终端|keyword|
|data|auditd.data.grantors|批准操作的PAM模块|keyword|
|data|auditd.data.direction|加密操作方向|keyword|
|data|auditd.data.op|被审计的操作|keyword|
|data|auditd.data.tty|用户运行程序的tty设备|keyword|
|data|auditd.data.syscall|系统调用号|keyword|
|data|auditd.data.data|TTY文本|keyword|
|data|auditd.data.family|netfilter协议|keyword|
|data|auditd.data.mac|选择的加密MAC算法|keyword|
|data|auditd.data.pfs|完美前向保密方法|keyword|
|data|auditd.data.items|事件中的路径记录数量|keyword|
|data|auditd.data.a0|系统调用参数0|keyword|
|data|auditd.data.a1|系统调用参数1|keyword|
|data|auditd.data.a2|系统调用参数2|keyword|
|data|auditd.data.a3|系统调用参数3|keyword|
|data|auditd.data.hostname|用户连接的主机名|keyword|
|data|auditd.data.lport|本地网络端口|keyword|
|data|auditd.data.rport|远程端口|keyword|
|data|auditd.data.exit|系统调用返回码|keyword|
|data|auditd.data.fp|加密密钥指纹|keyword|
|data|auditd.data.laddr|本地网络地址|keyword|
|data|auditd.data.sport|本地端口号|keyword|
|data|auditd.data.capability|POSIX能力|keyword|
|data|auditd.data.nargs|socket调用参数数量|keyword|
|data|auditd.data.new-enabled|新的TTY审计启用设置|keyword|
|data|auditd.data.audit_backlog_limit|审计系统的积压队列大小|keyword|
|data|auditd.data.dir|目录名|keyword|
|data|auditd.data.cap_pe|进程有效能力映射|keyword|
|data|auditd.data.model|虚拟化使用的安全模型|keyword|
|data|auditd.data.new_pp|新进程允许的能力映射|keyword|
|data|auditd.data.old-enabled|当前TTY审计启用设置|keyword|
|data|auditd.data.oauid|对象的登录用户ID|keyword|
|data|auditd.data.old|旧值|keyword|
|data|auditd.data.banners|打印页面使用的横幅|keyword|
|data|auditd.data.feature|被更改的内核特性|keyword|
|data|auditd.data.vm-ctx|虚拟机上下文字符串|keyword|
|data|auditd.data.opid|对象进程ID|keyword|
|data|auditd.data.seperms|使用的SELinux权限|keyword|
|data|auditd.data.seresult|SELinux AVC决策（允许/拒绝）|keyword|
|data|auditd.data.new-rng|新增虚拟机RNG设备名|keyword|
|data|auditd.data.old-net|当前分配给虚拟机的MAC地址|keyword|
|data|auditd.data.sigev_signo|信号编号|keyword|
|data|auditd.data.ino|inode编号|keyword|
|data|auditd.data.old_enforcing|旧MAC强制状态|keyword|
|data|auditd.data.old-vcpu|当前CPU核心数|keyword|
|data|auditd.data.range|用户的SELinux范围|keyword|
|data|auditd.data.res|审计操作结果（成功/失败）|keyword|
|data|auditd.data.added|新增文件数量|keyword|
|data|auditd.data.fam|socket地址族|keyword|
|data|auditd.data.nlnk-pid|netlink数据包发送方PID|keyword|
|data|auditd.data.subj|LSPP主体上下文字符串|keyword|
|data|auditd.data.a[0-3]|系统调用参数|keyword|
|data|auditd.data.cgroup|sysfs中cgroup路径|keyword|
|data|auditd.data.kernel|内核版本号|keyword|
|data|auditd.data.ocomm|对象命令行名|keyword|
|data|auditd.data.new-net|分配给虚拟机的新MAC地址|keyword|
|data|auditd.data.permissive|SELinux是否为宽容模式|keyword|
|data|auditd.data.class|分配给虚拟机的资源类别|keyword|
|data|auditd.data.compat|is_compat_task结果|keyword|
|data|auditd.data.fi|文件继承能力映射|keyword|
|data|auditd.data.changed|变更的文件数量|keyword|
|data|auditd.data.msg|审计记录载荷|keyword|
|data|auditd.data.dport|远程端口号|keyword|
|data|auditd.data.new-seuser|新SELinux用户|keyword|
|data|auditd.data.invalid_context|SELinux上下文|keyword|
|data|auditd.data.dmac|远程MAC地址|keyword|
|data|auditd.data.ipx-net|IPX网络号|keyword|
|data|auditd.data.iuid|IPC对象用户ID|keyword|
|data|auditd.data.macproto|以太网数据包类型ID字段|keyword|
|data|auditd.data.obj|LSPP对象上下文字符串|keyword|
|data|auditd.data.ipid|IP数据报片段标识符|keyword|
|data|auditd.data.new-fs|新增虚拟机文件系统|keyword|
|data|auditd.data.vm-pid|虚拟机进程ID|keyword|
|data|auditd.data.cap_pi|进程继承能力映射|keyword|
|data|auditd.data.old-auid|先前的AUID值|keyword|
|data|auditd.data.oses|对象会话ID|keyword|
|data|auditd.data.fd|文件描述符编号|keyword|
|data|auditd.data.igid|IPC对象组ID|keyword|
|data|auditd.data.new-disk|新增虚拟机磁盘|keyword|
|data|auditd.data.parent|父文件的inode编号|keyword|
|data|auditd.data.len|长度|keyword|
|data|auditd.data.oflag|打开系统调用标志|keyword|
|data|auditd.data.uuid|UUID|keyword|
|data|auditd.data.code|seccomp动作代码|keyword|
|data|auditd.data.nlnk-grp|netlink组编号|keyword|
|data|auditd.data.cap_fp|文件允许能力映射|keyword|
|data|auditd.data.new-mem|新增内存（KB）|keyword|
|data|auditd.data.seperm|SELinux正在决定的权限|keyword|
|data|auditd.data.enforcing|新MAC强制状态|keyword|
|data|auditd.data.new-chardev|新增虚拟机字符设备|keyword|
|data|auditd.data.old-rng|移除虚拟机RNG设备|keyword|
|data|auditd.data.outif|出接口编号|keyword|
|data|auditd.data.cmd|执行的命令|keyword|
|data|auditd.data.hook|netfilter钩子来源|keyword|
|data|auditd.data.new-level|新运行级别|keyword|
|data|auditd.data.sauid|发送登录用户ID|keyword|
|data|auditd.data.sig|信号编号|keyword|
|data|auditd.data.audit_backlog_wait_time|审计系统积压等待时间|keyword|
|data|auditd.data.printer|打印机名称|keyword|
|data|auditd.data.old-mem|当前内存量（KB）|keyword|
|data|auditd.data.perm|文件权限|keyword|
|data|auditd.data.old_pi|旧进程继承能力映射|keyword|
|data|auditd.data.state|审计守护进程配置结果状态|keyword|
|data|auditd.data.format|审计日志格式|keyword|
|data|auditd.data.new_gid|新分配组ID|keyword|
|data|auditd.data.tcontext|对象上下文字符串|keyword|
|data|auditd.data.maj|设备主编号|keyword|
|data|auditd.data.watch|watch记录中的文件名|keyword|
|data|auditd.data.device|设备名|keyword|
|data|auditd.data.grp|组名|keyword|
|data|auditd.data.bool|SELinux布尔名称|keyword|
|data|auditd.data.icmp_type|ICMP消息类型|keyword|
|data|auditd.data.new_lock|特性锁的新值|keyword|
|data|auditd.data.old_prom|当前网络混杂模式标志|keyword|
|data|auditd.data.acl|分配给虚拟机的资源访问模式|keyword|
|data|auditd.data.ip|打印机网络地址|keyword|
|data|auditd.data.new_pi|新进程继承能力映射|keyword|
|data|auditd.data.default-context|默认MAC上下文|keyword|
|data|auditd.data.inode_gid|inode所属组ID|keyword|
|data|auditd.data.new-log_passwd|新TTY密码记录值|keyword|
|data|auditd.data.new_pe|新进程有效能力映射|keyword|
|data|auditd.data.selected-context|新MAC上下文分配给会话|keyword|
|data|auditd.data.cap_fver|文件系统能力版本号|keyword|
|data|auditd.data.file|文件名|keyword|
|data|auditd.data.net|网络MAC地址|keyword|
|data|auditd.data.virt|虚拟化类型|keyword|
|data|auditd.data.cap_pp|进程允许能力映射|keyword|
|data|auditd.data.old-range|当前SELinux范围|keyword|
|data|auditd.data.resrc|被分配的资源|keyword|
|data|auditd.data.new-range|新SELinux范围|keyword|
|data|auditd.data.obj_gid|对象组ID|keyword|
|data|auditd.data.proto|网络协议|keyword|
|data|auditd.data.old-disk|移除虚拟机磁盘|keyword|
|data|auditd.data.audit_failure|审计系统故障模式|keyword|
|data|auditd.data.inif|入接口编号|keyword|
|data|auditd.data.vm|虚拟机名称|keyword|
|data|auditd.data.flags|mmap系统调用标志|keyword|
|data|auditd.data.nlnk-fam|netlink协议编号|keyword|
|data|auditd.data.old-fs|移除虚拟机文件系统|keyword|
|data|auditd.data.old-ses|先前会话值|keyword|
|data|auditd.data.seqno|序列号|keyword|
|data|auditd.data.fver|文件系统能力版本号|keyword|
|data|auditd.data.qbytes|IPC对象字节数|keyword|
|data|auditd.data.seuser|SELinux用户账户|keyword|
|data|auditd.data.cap_fe|文件有效能力映射|keyword|
|data|auditd.data.new-vcpu|新CPU核心数|keyword|
|data|auditd.data.old-level|旧运行级别|keyword|
|data|auditd.data.old_pp|旧进程允许能力映射|keyword|
|data|auditd.data.daddr|远程IP地址|keyword|
|auditd.data|auditd.data.old-role|当前 SELinux 角色|keyword|
|auditd.data|auditd.data.ioctlcmd|ioctl 系统调用的请求参数|keyword|
|auditd.data|auditd.data.smac|本地 MAC 地址|keyword|
|auditd.data|auditd.data.apparmor|AppArmor 事件信息|keyword|
|auditd.data|auditd.data.fe|文件分配的有效能力映射|keyword|
|auditd.data|auditd.data.perm_mask|触发监控事件的文件权限掩码|keyword|
|auditd.data|auditd.data.ses|登录会话 ID|keyword|
|auditd.data|auditd.data.cap_fi|文件继承的能力映射|keyword|
|auditd.data|auditd.data.obj_uid|对象的用户 ID|keyword|
|auditd.data|auditd.data.reason|描述操作原因的文本|keyword|
|auditd.data|auditd.data.list|审计系统的过滤列表编号|keyword|
|auditd.data|auditd.data.old_lock|功能锁当前值|keyword|
|auditd.data|auditd.data.bus|VM 资源所属子系统总线名称|keyword|
|auditd.data|auditd.data.old_pe|旧进程有效能力映射|keyword|
|auditd.data|auditd.data.new-role|新 SELinux 角色|keyword|
|auditd.data|auditd.data.prom|网络混杂模式标志|keyword|
|auditd.data|auditd.data.uri|指向打印机的 URI|keyword|
|auditd.data|auditd.data.audit_enabled|审计系统启用/禁用状态|keyword|
|auditd.data|auditd.data.old-log_passwd|当前 TTY 密码日志值|keyword|
|auditd.data|auditd.data.old-seuser|当前 SELinux 用户|keyword|
|auditd.data|auditd.data.per|Linux 个性化信息|keyword|
|auditd.data|auditd.data.scontext|主体上下文字符串|keyword|
|auditd.data|auditd.data.tclass|目标对象分类|keyword|
|auditd.data|auditd.data.ver|审计守护进程版本号|keyword|
|auditd.data|auditd.data.new|设置的功能值|keyword|
|auditd.data|auditd.data.val|与操作相关的通用值|keyword|
|auditd.data|auditd.data.img-ctx|VM 磁盘镜像上下文字符串|keyword|
|auditd.data|auditd.data.old-chardev|当前分配给 VM 的字符设备|keyword|
|auditd.data|auditd.data.old_val|SELinux 布尔值当前值|keyword|
|auditd.data|auditd.data.success|系统调用是否成功|keyword|
|auditd.data|auditd.data.inode_uid|inode 所有者的用户 ID|keyword|
|auditd.data|auditd.data.removed|删除的文件数量|keyword|
|auditd.data|auditd.data.socket.port|端口号|keyword|
|auditd.data|auditd.data.socket.saddr|原始 socket 地址结构|keyword|
|auditd.data|auditd.data.socket.addr|远程地址|keyword|
|auditd.data|auditd.data.socket.family|Socket 类型（unix, ipv4, ipv6, netlink）|keyword|
|auditd.data|auditd.data.socket.path|unix socket 的路径|keyword|
|auditd|auditd.messages|从内核接收的原始消息列表|alias|
|auditd|auditd.warnings|构建事件时产生的警告|alias|
|geoip|geoip.continent_name|洲名|keyword|
|geoip|geoip.city_name|城市名|keyword|
|geoip|geoip.region_name|区域名/省份名|keyword|
|geoip|geoip.country_iso_code|国家 ISO 代码|keyword|
|geoip|geoip.location|经纬度坐标|geo_point|