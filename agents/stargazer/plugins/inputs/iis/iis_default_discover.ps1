$ErrorActionPreference = "SilentlyContinue"
$WarningPreference = "SilentlyContinue"

function ConvertToJson {
    param(
        $InputObject
    )
    return $InputObject | ConvertTo-Json -Compress
}

function Get-IISProperties {
    $appCmdExe = 'C:/Windows/System32/inetsrv/appcmd.exe'
    $siteCmd = "$appCmdExe list app /text:SITE.NAME"
    $siteResult = Invoke-Expression $siteCmd

    if (-not $siteResult) {
        Write-Output "{}"
        exit 0
    }

    $sites = $siteResult.Split("`n") | Where-Object { $_ } | Sort-Object -Unique
    $siteCount = ($sites | Measure-Object).Count
    $allPools = @()

    foreach ($siteName in $sites) {
        $bindingCmd = "$appCmdExe list site /site.name:`"$siteName`" /text:bindings"
        $bindingResult = Invoke-Expression $bindingCmd

        $listenIp, $port = $null, $null
        foreach ($s in $bindingResult.Split(',')) {
            if ($s -match 'http' -and $s -notmatch 'https') {
                $binding = $s.Trim(':').Split(':')
                $listenIp, $port = $binding[0], $binding[1]
                break
            }
        }

        $maxConnCmd = "$appCmdExe list site /site.name:`"$siteName`" /text:limits.maxConnections"
        $maxConnections = (Invoke-Expression $maxConnCmd).Trim()

        $appPoolCmd = "$appCmdExe list app /app.name:`"$siteName`"/ /text:applicationPool"
        $appPoolName = (Invoke-Expression $appPoolCmd).Trim()
        if ($appPoolName) {
            $allPools += $appPoolName
        }

        $physicalPathCmd = "$appCmdExe list vdir /vdir.name:`"$siteName`"/ /text:physicalPath"
        $physicalPath = (Invoke-Expression $physicalPathCmd).Trim() -replace '%SystemDrive%', $env:SystemDrive

        $webAppsCmd = "$appCmdExe list app /site.name:`"$siteName`" /text:path"
        $webApps = (Invoke-Expression $webAppsCmd) -split "`n" | Where-Object { $_ }

        $version = $null
        try {
            $verPath = Get-ItemProperty -Path "HKLM:\SOFTWARE\Microsoft\InetStp"
            $version = $verPath.VersionString -replace "Version ", ""
        } catch {
            $version = ""
        }

        $siteConfigPath = "$env:windir\System32\inetsrv\config\applicationHost.config"
        $bk_inst_name = "{{bk_host_innerip}}-iis-$port"

        $iisProperty = [pscustomobject]@{
            ip_addr = "{{bk_host_innerip}}"
            port = $port
            version = $version
            webapp = ($webApps -join ',')
            virdir = "/$siteName"
            configfile = $siteConfigPath
            apppool = if ($appPoolName) { $appPoolName } else { "" }
            website = $siteName
            apppool_count = (($allPools | Sort-Object -Unique | Measure-Object).Count)
            webapp_count = ($webApps | Measure-Object).Count
            phys_path = if ($physicalPath) { $physicalPath } else { "" }
            server_name = $siteName
            max_concur_connect = $maxConnections
            bk_inst_name = $bk_inst_name
            bk_obj_id = "iis"
        }

        $jsonString = ConvertToJson $iisProperty
        Write-Output $jsonString
    }
}

Get-IISProperties
