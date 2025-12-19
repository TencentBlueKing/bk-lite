#Requires -RunAsAdministrator

$INSTALL_PATH = "C:\bklite\fusion-collectors\"

# Get user confirmation
Write-Host "This operation will remove the sidecar service and its configuration files and log files"
$confirm = Read-Host "Confirm uninstalling sidecar service? [yes/n]"

if ($confirm -eq "yes") {
    # Stop sidecar service
    Write-Host "Stopping sidecar service"
    Stop-Service -Name "sidecar" -Force -ErrorAction SilentlyContinue

    # Delete sidecar service
    Write-Host "Deleting sidecar service"
    sc.exe delete sidecar

    # Delete sidecar folder
    Write-Host "Clearing $INSTALL_PATH folder"
    if (Test-Path $INSTALL_PATH) {
        Remove-Item -Path $INSTALL_PATH -Recurse -Force
    }

    Write-Host "Uninstall completed"
}
elseif ($confirm -eq "n") {
    Write-Host "Uninstall cancelled"
}
else {
    Write-Host "Invalid input. Please enter 'yes' or 'n'."
    exit 1
}
