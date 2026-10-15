### Overview
A custom collection runs the script stored in the plugin library. It does not run the built-in host, Nginx, or other collector scripts. Collected records are still written using the plugin's target model.

The script is loaded once per task run and shared by every target IP. The script body is not included in the dispatched configuration.

### Connection
The operating system is chosen when the plugin is created. Task credentials follow that operating system.

| Plugin OS | Connection | Default port | Credentials |
| :--- | :--- | :--- | :--- |
| Linux | Run locally when the target is already a managed node; otherwise SSH from the access point | 22 | Username and password |
| Windows | WinRM. Default scheme is HTTPS and default authentication is NTLM | 5986 | Username and password |

Linux scripts can use only bash or sh. Windows scripts can use only powershell or bat. The host picker filters by the plugin operating system. An IP range cannot tell the operating system in advance, so a protocol mismatch fails the connection.

### Execution
1. Upload the script in Custom Plugins and choose the target model and operating system.
2. Open Collection → Custom, select the plugin, and create a task with the cycle, access point, IP range or hosts, and the login credentials for that operating system.
3. When the task runs, the collector loads the script and executes it on the target. Script execution is limited to the task timeout, and never longer than 600 seconds.

### Returned data
Print a JSON array to stdout. Every record must include `inst_name`. Other field names must match the target model attributes. Records without `inst_name` are dropped.

```json
[
  {"inst_name": "demo-nginx", "ip_addr": "10.0.0.8", "port": "80"}
]
```

The stored metric name is `{plugin_id}_info`. For plugin id `custom_nginx_linux_scan`, the metric name is `custom_nginx_linux_scan_info`.
