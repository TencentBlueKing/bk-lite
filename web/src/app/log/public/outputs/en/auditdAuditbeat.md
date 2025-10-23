### Auditbeat auditd Introduction

- &zwnj;**Basic Functions**&zwnj;
  - Security event collection

  - Rule management

  - Real-time transmission

  - System call monitoring

- &zwnj;**Key Features**&zwnj;
  - Lightweight alternative to auditd

  - Security auditing and compliance

  - Flexible rule configuration

  - Rich contextual information

  - Elastic Stack integration

  - Typical use cases

### Auditbeat auditd Output Fields


|Group Name|Field Name (Full)|Field Description (English)|Type|
|--------|------|------|--------|
|Built-in Fields|collect_type|Collection type|-|
|Built-in Fields|collector|Collector|-|
|Built-in Fields|instance_id|Instance ID|-|
|user|user.auid|Audit user ID|alias|
|user|user.uid|User ID|alias|
|user|user.fsuid|Filesystem user ID|alias|
|user|user.suid|Saved user ID|alias|
|user|user.gid|Group ID|alias|
|user|user.sgid|Saved group ID|alias|
|user|user.fsgid|Filesystem group ID|alias|
|user.name_map|user.name_map.auid|Audit username|alias|
|user.name_map|user.name_map.uid|Username|alias|
|user.name_map|user.name_map.fsuid|Filesystem username|alias|
|user.name_map|user.name_map.suid|Saved username|alias|
|user.name_map|user.name_map.gid|Group name|alias|
|user.name_map|user.name_map.sgid|Saved group name|alias|
|user.name_map|user.name_map.fsgid|Filesystem group name|alias|
|selinux|user.selinux.user|SELinux user for authentication|keyword|
|selinux|user.selinux.role|SELinux role|keyword|
|selinux|user.selinux.domain|SELinux domain/type|keyword|
|selinux|user.selinux.level|SELinux level|keyword|
|selinux|user.selinux.category|SELinux category/compartment|keyword|
|process|process.cwd|Current working directory|alias|
|source|source.path|UNIX socket path|keyword|
|destination|destination.path|UNIX socket path|keyword|
|auditd|auditd.message_type|Audit message type|keyword|
|auditd|auditd.sequence|Kernel-assigned event sequence number|long|
|auditd|auditd.session|Login session ID|keyword|
|auditd|auditd.result|Audit operation result (success/failure)|keyword|
|actor|auditd.summary.actor.primary|Primary identity (original login ID)|keyword|
|actor|auditd.summary.actor.secondary|Secondary identity (may differ when su is used)|keyword|
|object|auditd.summary.object.type|Object type (e.g., file, socket, user session)|keyword|
|object|auditd.summary.object.primary|Primary object identifier|keyword|
|object|auditd.summary.object.secondary|Secondary object identifier|keyword|
|object|auditd.summary.how|Method of action execution (command/executable)|keyword|
|paths|auditd.paths.inode|Inode number|keyword|
|paths|auditd.paths.dev|Device name (under /dev)|keyword|
|paths|auditd.paths.obj_user|Object user|keyword|
|paths|auditd.paths.obj_role|Object role|keyword|
|paths|auditd.paths.obj_domain|Object domain|keyword|
|paths|auditd.paths.obj_level|Object level|keyword|
|paths|auditd.paths.objtype|Object type|keyword|
|paths|auditd.paths.ouid|File owner user ID|keyword|
|paths|auditd.paths.rdev|Special file device identifier|keyword|
|paths|auditd.paths.nametype|File operation type|keyword|
|paths|auditd.paths.ogid|File owner group ID|keyword|
|paths|auditd.paths.item|Recorded item|keyword|
|paths|auditd.paths.mode|File mode flags|keyword|
|paths|auditd.paths.name|Filename (AVCS)|keyword|
|data|auditd.data.action|Netfilter packet processing result|keyword|
|data|auditd.data.minor|Device minor number|keyword|
|data|auditd.data.acct|User account name|keyword|
|data|auditd.data.addr|Remote address of user connection|keyword|
|data|auditd.data.cipher|Encryption algorithm used|keyword|
|data|auditd.data.id|ID during account change|keyword|
|data|auditd.data.entries|Number of entries in netfilter table|keyword|
|data|auditd.data.kind|Client or server for encryption operation|keyword|
|data|auditd.data.ksize|Key size for encryption operation|keyword|
|data|auditd.data.spid|Sending process ID|keyword|
|data|auditd.data.arch|ELF architecture flags|keyword|
|data|auditd.data.argc|Number of arguments for execve system call|keyword|
|data|auditd.data.major|Device major number|keyword|
|data|auditd.data.unit|Systemd unit|keyword|
|data|auditd.data.table|Netfilter table name|keyword|
|data|auditd.data.terminal|Terminal where user runs program|keyword|
|data|auditd.data.grantors|PAM modules that approved the operation|keyword|
|data|auditd.data.direction|Direction of encryption operation|keyword|
|data|auditd.data.op|Operation being audited|keyword|
|data|auditd.data.tty|TTY device where user runs program|keyword|
|data|auditd.data.syscall|System call number|keyword|
|data|auditd.data.data|TTY text|keyword|
|data|auditd.data.family|Netfilter protocol|keyword|
|data|auditd.data.mac|Selected encryption MAC algorithm|keyword|
|data|auditd.data.pfs|Perfect forward secrecy method|keyword|
|data|auditd.data.items|Number of path records in the event|keyword|
|data|auditd.data.a0|System call argument 0|keyword|
|data|auditd.data.a1|System call argument 1|keyword|
|data|auditd.data.a2|System call argument 2|keyword|
|data|auditd.data.a3|System call argument 3|keyword|
|data|auditd.data.hostname|Hostname of user connection|keyword|
|data|auditd.data.lport|Local network port|keyword|
|data|auditd.data.rport|Remote port|keyword|
|data|auditd.data.exit|System call return code|keyword|
|data|auditd.data.fp|Encryption key fingerprint|keyword|
|data|auditd.data.laddr|Local network address|keyword|
|data|auditd.data.sport|Local port number|keyword|
|data|auditd.data.capability|POSIX capability|keyword|
|data|auditd.data.nargs|Number of socket call arguments|keyword|
|data|auditd.data.new-enabled|New TTY audit enable setting|keyword|
|data|auditd.data.audit_backlog_limit|Audit system backlog queue size|keyword|
|data|auditd.data.dir|Directory name|keyword|
|data|auditd.data.cap_pe|Process effective capability mapping|keyword|
|data|auditd.data.model|Security model used by virtualization|keyword|
|data|auditd.data.new_pp|New process permitted capability mapping|keyword|
|data|auditd.data.old-enabled|Current TTY audit enable setting|keyword|
|data|auditd.data.oauid|Object's login user ID|keyword|
|data|auditd.data.old|Old value|keyword|
|data|auditd.data.banners|Banner used for printing pages|keyword|
|data|auditd.data.feature|Kernel feature being changed|keyword|
|data|auditd.data.vm-ctx|Virtual machine context string|keyword|
|data|auditd.data.opid|Object process ID|keyword|
|data|auditd.data.seperms|SELinux permissions used|keyword|
|data|auditd.data.seresult|SELinux AVC decision (allow/deny)|keyword|
|data|auditd.data.new-rng|New virtual machine RNG device name|keyword|
|data|auditd.data.old-net|Current MAC address assigned to VM|keyword|
|data|auditd.data.sigev_signo|Signal number|keyword|
|data|auditd.data.ino|Inode number|keyword|
|data|auditd.data.old_enforcing|Old MAC enforcement state|keyword|
|data|auditd.data.old-vcpu|Current CPU core count|keyword|
|data|auditd.data.range|User's SELinux range|keyword|
|data|auditd.data.res|Audit operation result (success/failure)|keyword|
|data|auditd.data.added|Number of files added|keyword|
|data|auditd.data.fam|Socket address family|keyword|
|data|auditd.data.nlnk-pid|Netlink packet sender PID|keyword|
|data|auditd.data.subj|LSPP subject context string|keyword|
|data|auditd.data.a[0-3]|System call arguments|keyword|
|data|auditd.data.cgroup|Cgroup path in sysfs|keyword|
|data|auditd.data.kernel|Kernel version number|keyword|
|data|auditd.data.ocomm|Object command line name|keyword|
|data|auditd.data.new-net|New MAC address assigned to VM|keyword|
|data|auditd.data.permissive|Whether SELinux is in permissive mode|keyword|
|data|auditd.data.class|Resource category assigned to VM|keyword|
|data|auditd.data.compat|is_compat_task result|keyword|
|data|auditd.data.fi|File inheritance capability mapping|keyword|
|data|auditd.data.changed|Number of files changed|keyword|
|data|auditd.data.msg|Audit record payload|keyword|
|data|auditd.data.dport|Remote port number|keyword|
|data|auditd.data.new-seuser|New SELinux user|keyword|
|data|auditd.data.invalid_context|SELinux context|keyword|
|data|auditd.data.dmac|Remote MAC address|keyword|
|data|auditd.data.ipx-net|IPX network number|keyword|
|data|auditd.data.iuid|IPC object user ID|keyword|
|data|auditd.data.macproto|Ethernet packet type ID field|keyword|
|data|auditd.data.obj|LSPP object context string|keyword|
|data|auditd.data.ipid|IP datagram fragment identifier|keyword|
|data|auditd.data.new-fs|New virtual machine filesystem|keyword|
|data|auditd.data.vm-pid|Virtual machine process ID|keyword|
|data|auditd.data.cap_pi|Process inheritance capability mapping|keyword|
|data|auditd.data.old-auid|Previous AUID value|keyword|
|data|auditd.data.oses|Object session ID|keyword|
|data|auditd.data.fd|File descriptor number|keyword|
|data|auditd.data.igid|IPC object group ID|keyword|
|data|auditd.data.new-disk|New virtual machine disk|keyword|
|data|auditd.data.parent|Parent file's inode number|keyword|
|data|auditd.data.len|Length|keyword|
|data|auditd.data.oflag|Open system call flags|keyword|
|data|auditd.data.uuid|UUID|keyword|
|data|auditd.data.code|Seccomp action code|keyword|
|data|auditd.data.nlnk-grp|Netlink group number|keyword|
|data|auditd.data.cap_fp|File permitted capability mapping|keyword|
|data|auditd.data.new-mem|New memory (KB)|keyword|
|data|auditd.data.seperm|SELinux permission being decided|keyword|
|data|auditd.data.enforcing|New MAC enforcement state|keyword|
|data|auditd.data.new-chardev|New virtual machine character device|keyword|
|data|auditd.data.old-rng|Removed virtual machine RNG device|keyword|
|data|auditd.data.outif|Output interface number|keyword|
|data|auditd.data.cmd|Command executed|keyword|
|data|auditd.data.hook|Netfilter hook source|keyword|
|data|auditd.data.new-level|New run level|keyword|
|data|auditd.data.sauid|Sending login user ID|keyword|
|data|auditd.data.sig|Signal number|keyword|
|data|auditd.data.audit_backlog_wait_time|Audit system backlog wait time|keyword|
|data|auditd.data.printer|Printer name|keyword|
|data|auditd.data.old-mem|Current memory amount (KB)|keyword|
|data|auditd.data.perm|File permissions|keyword|
|data|auditd.data.old_pi|Old process inheritance capability mapping|keyword|
|data|auditd.data.state|Audit daemon configuration result state|keyword|
|data|auditd.data.format|Audit log format|keyword|
|data|auditd.data.new_gid|New assigned group ID|keyword|
|data|auditd.data.tcontext|Object context string|keyword|
|data|auditd.data.maj|Device major number|keyword|
|data|auditd.data.watch|Filename in watch record|keyword|
|data|auditd.data.device|Device name|keyword|
|data|auditd.data.grp|Group name|keyword|
|data|auditd.data.bool|SELinux boolean name|keyword|
|data|auditd.data.icmp_type|ICMP message type|keyword|
|data|auditd.data.new_lock|New value of feature lock|keyword|
|data|auditd.data.old_prom|Current network promiscuous mode flag|keyword|
|data|auditd.data.acl|Resource access mode assigned to VM|keyword|
|data|auditd.data.ip|Printer network address|keyword|
|data|auditd.data.new_pi|New process inheritance capability mapping|keyword|
|data|auditd.data.default-context|Default MAC context|keyword|
|data|auditd.data.inode_gid|Group ID of inode|keyword|
|data|auditd.data.new-log_passwd|New TTY password logging value|keyword|
|data|auditd.data.new_pe|New process effective capability mapping|keyword|
|data|auditd.data.selected-context|New MAC context assigned to session|keyword|
|data|auditd.data.cap_fver|Filesystem capability version number|keyword|
|data|auditd.data.file|Filename|keyword|
|data|auditd.data.net|Network MAC address|keyword|
|data|auditd.data.virt|Virtualization type|keyword|
|data|auditd.data.cap_pp|Process permitted capability mapping|keyword|
|data|auditd.data.old-range|Current SELinux range|keyword|
|data|auditd.data.resrc|Resource being allocated|keyword|
|data|auditd.data.new-range|New SELinux range|keyword|
|data|auditd.data.obj_gid|Object group ID|keyword|
|data|auditd.data.proto|Network protocol|keyword|
|data|auditd.data.old-disk|Removed virtual machine disk|keyword|
|data|auditd.data.audit_failure|Audit system failure mode|keyword|
|data|auditd.data.inif|Input interface number|keyword|
|data|auditd.data.vm|Virtual machine name|keyword|
|data|auditd.data.flags|Mmap system call flags|keyword|
|data|auditd.data.nlnk-fam|Netlink protocol number|keyword|
|data|auditd.data.old-fs|Removed virtual machine filesystem|keyword|
|data|auditd.data.old-ses|Previous session value|keyword|
|data|auditd.data.seqno|Sequence number|keyword|
|data|auditd.data.fver|Filesystem capability version number|keyword|
|data|auditd.data.qbytes|IPC object byte count|keyword|
|data|auditd.data.seuser|SELinux user account|keyword|
|data|auditd.data.cap_fe|File effective capability mapping|keyword|
|data|auditd.data.new-vcpu|New CPU core count|keyword|
|data|auditd.data.old-level|Old run level|keyword|
|data|auditd.data.old_pp|Old process permitted capability mapping|keyword|
|data|auditd.data.daddr|Remote IP address|keyword|
|auditd.data|auditd.data.old-role|Current SELinux role|keyword|
|auditd.data|auditd.data.ioctlcmd|Request parameter for ioctl system call|keyword|
|auditd.data|auditd.data.smac|Local MAC address|keyword|
|auditd.data|auditd.data.apparmor|AppArmor event information|keyword|
|auditd.data|auditd.data.fe|File allocated effective capability mapping|keyword|
|auditd.data|auditd.data.perm_mask|File permission mask that triggered monitoring event|keyword|
|auditd.data|auditd.data.ses|Login session ID|keyword|
|auditd.data|auditd.data.cap_fi|File inherited capability mapping|keyword|
|auditd.data|auditd.data.obj_uid|Object user ID|keyword|
|auditd.data|auditd.data.reason|Text describing the reason for the operation|keyword|
|auditd.data|auditd.data.list|Audit system filter list number|keyword|
|auditd.data|auditd.data.old_lock|Current value of feature lock|keyword|
|auditd.data|auditd.data.bus|Subsystem bus name for VM resource|keyword|
|auditd.data|auditd.data.old_pe|Old process effective capability mapping|keyword|
|auditd.data|auditd.data.new-role|New SELinux role|keyword|
|auditd.data|auditd.data.prom|Network promiscuous mode flag|keyword|
|auditd.data|auditd.data.uri|URI pointing to the printer|keyword|
|auditd.data|auditd.data.audit_enabled|Audit system enable/disable state|keyword|
|auditd.data|auditd.data.old-log_passwd|Current TTY password logging value|keyword|
|auditd.data|auditd.data.old-seuser|Current SELinux user|keyword|
|auditd.data|auditd.data.per|Linux personality information|keyword|
|auditd.data|auditd.data.scontext|Subject context string|keyword|
|auditd.data|auditd.data.tclass|Target object classification|keyword|
|auditd.data|auditd.data.ver|Audit daemon version number|keyword|
|auditd.data|auditd.data.new|Set capability value|keyword|
|auditd.data|auditd.data.val|Generic value related to operation|keyword|
|auditd.data|auditd.data.img-ctx|VM disk image context string|keyword|
|auditd.data|auditd.data.old-chardev|Character device currently assigned to VM|keyword|
|auditd.data|auditd.data.old_val|Current value of SELinux boolean|keyword|
|auditd.data|auditd.data.success|Whether system call succeeded|keyword|
|auditd.data|auditd.data.inode_uid|User ID of inode owner|keyword|
|auditd.data|auditd.data.removed|Number of files removed|keyword|
|auditd.data|auditd.data.socket.port|Port number|keyword|
|auditd.data|auditd.data.socket.saddr|Raw socket address structure|keyword|
|auditd.data|auditd.data.socket.addr|Remote address|keyword|
|auditd.data|auditd.data.socket.family|Socket type (unix, ipv4, ipv6, netlink)|keyword|
|auditd.data|auditd.data.socket.path|Unix socket path|keyword|
|auditd|auditd.messages|List of raw messages received from kernel|alias|
|auditd|auditd.warnings|Warnings generated when building the event|alias|
|geoip|geoip.continent_name|Continent name|keyword|
|geoip|geoip.city_name|City name|keyword|
|geoip|geoip.region_name|Region/state name|keyword|
|geoip|geoip.country_iso_code|Country ISO code|keyword|
|geoip|geoip.location|Latitude and longitude coordinates|geo_point|