; Collector Sidecar Installer
; NSIS + Go worker architecture
; Key: Worker runs from $INSTDIR (not TEMP) to avoid malware detection

!include "MUI2.nsh"
!include "nsDialogs.nsh"
!include "LogicLib.nsh"
!include "FileFunc.nsh"
!include "WinMessages.nsh"

!ifndef ES_READONLY
!define ES_READONLY 0x0800
!endif
!ifndef WS_EX_CLIENTEDGE
!define WS_EX_CLIENTEDGE 0x00000200
!endif

; ============================================================================
; Settings
; ============================================================================

Name "Collector Sidecar Installer"
OutFile "collector-sidecar-installer.exe"
InstallDir "C:\fusion-collectors"
RequestExecutionLevel admin
Unicode True
ManifestDPIAware true

VIProductVersion "1.0.0.0"
VIAddVersionKey "ProductName" "Collector Sidecar"
VIAddVersionKey "CompanyName" "BK-Lite"
VIAddVersionKey "FileDescription" "Collector Sidecar Installer"
VIAddVersionKey "FileVersion" "1.0.0"
VIAddVersionKey "LegalCopyright" "MIT License"

; ============================================================================
; UI
; ============================================================================

!define MUI_ABORTWARNING
!define MUI_ABORTWARNING_TEXT "Are you sure you want to cancel?"
!define MUI_ICON "installer.ico"
!define MUI_UNICON "installer.ico"

!define MUI_HEADERIMAGE
!define MUI_HEADERIMAGE_BITMAP "header.bmp"
!define MUI_HEADERIMAGE_RIGHT
!define MUI_WELCOMEFINISHPAGE_BITMAP "wizard.bmp"

!define MUI_WELCOMEPAGE_TITLE "Collector Sidecar Setup"
!define MUI_WELCOMEPAGE_TEXT "This wizard will install Collector Sidecar.$\r$\n$\r$\nClick Next to continue."

!define MUI_FINISHPAGE_TITLE "Installation Complete"
!define MUI_FINISHPAGE_TEXT "Collector Sidecar has been installed.$\r$\n$\r$\nClick Finish to close."

; ============================================================================
; Variables
; ============================================================================

Var ConfigURL
Var ConfigURLInput
Var Dialog
Var Label
Var ConfigInfoBox
Var FetchButton
Var ConfigFetched

; ============================================================================
; Pages
; ============================================================================

!insertmacro MUI_PAGE_WELCOME
Page custom ConfigPage ConfigPageLeave
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH

!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES

!insertmacro MUI_LANGUAGE "English"

; ============================================================================
; Config Page
; ============================================================================

Function ConfigPage
    !insertmacro MUI_HEADER_TEXT "Configuration" "Enter the configuration URL"

    nsDialogs::Create 1018
    Pop $Dialog
    ${If} $Dialog == error
        Abort
    ${EndIf}

    ${NSD_CreateLabel} 0 0 100% 12u "Configuration URL:"
    Pop $Label

    ${NSD_CreateText} 0 14u 76% 14u "$ConfigURL"
    Pop $ConfigURLInput
    ${NSD_SetFocus} $ConfigURLInput

    ${NSD_CreateButton} 78% 13u 22% 16u "Fetch"
    Pop $FetchButton
    ${NSD_OnClick} $FetchButton OnFetchClick

    ${NSD_CreateLabel} 0 34u 100% 12u "Example: https://server/api/config/node-id"
    Pop $Label

    ${NSD_CreateLabel} 0 52u 100% 12u "Details:"
    Pop $Label

    nsDialogs::CreateControl "EDIT" \
        ${ES_MULTILINE}|${ES_READONLY}|${ES_AUTOVSCROLL}|${WS_VSCROLL}|${WS_VISIBLE}|${WS_CHILD}|${WS_TABSTOP} \
        ${WS_EX_CLIENTEDGE} \
        0 66u 100% 72u ""
    Pop $ConfigInfoBox

    CreateFont $0 "Segoe UI" 9
    SendMessage $ConfigInfoBox ${WM_SETFONT} $0 1

    nsDialogs::Show
FunctionEnd

Function OnFetchClick
    ${NSD_GetText} $ConfigURLInput $ConfigURL

    ${If} $ConfigURL == ""
        ${NSD_SetText} $ConfigInfoBox "Error: Please enter a URL"
        StrCpy $ConfigFetched "0"
        Return
    ${EndIf}

    StrCpy $0 $ConfigURL 4
    ${If} $0 != "http"
        ${NSD_SetText} $ConfigInfoBox "Error: URL must start with http:// or https://"
        StrCpy $ConfigFetched "0"
        Return
    ${EndIf}

    ${NSD_SetText} $ConfigInfoBox "Fetching..."

    ; Create install dir first, extract worker there
    CreateDirectory "$INSTDIR"
    SetOutPath "$INSTDIR"
    File "setup-worker.exe"

    ; Run fetch-only mode
    nsExec::ExecToStack '"$INSTDIR\setup-worker.exe" --url "$ConfigURL" --fetch-only --skip-tls'
    Pop $0
    Pop $1

    ${If} $0 != 0
        ${NSD_SetText} $ConfigInfoBox "Error: $1"
        StrCpy $ConfigFetched "0"
    ${Else}
        ${NSD_SetText} $ConfigInfoBox "$1"
        StrCpy $ConfigFetched "1"
    ${EndIf}
FunctionEnd

Function ConfigPageLeave
    ${NSD_GetText} $ConfigURLInput $ConfigURL

    ${If} $ConfigURL == ""
        MessageBox MB_ICONEXCLAMATION|MB_OK "Please enter a URL"
        Abort
    ${EndIf}

    ${If} $ConfigFetched != "1"
        MessageBox MB_ICONEXCLAMATION|MB_OK "Please click Fetch to verify configuration"
        Abort
    ${EndIf}
FunctionEnd

; ============================================================================
; Install
; ============================================================================

Section "Install" SecInstall
    SetOutPath $INSTDIR

    ; Worker already extracted during config page
    IfFileExists "$INSTDIR\setup-worker.exe" +2
        File "setup-worker.exe"

    DetailPrint "Install: $INSTDIR"
    DetailPrint "URL: $ConfigURL"
    DetailPrint ""

    nsExec::ExecToLog '"$INSTDIR\setup-worker.exe" --url "$ConfigURL" --install-dir "$INSTDIR" --skip-tls'
    Pop $0

    ${If} $0 != 0
        DetailPrint ""
        DetailPrint "Installation failed (code $0)"
        MessageBox MB_ICONEXCLAMATION|MB_OK "Installation failed"
        Abort
    ${EndIf}

    ; Cleanup worker
    Delete "$INSTDIR\setup-worker.exe"

    DetailPrint ""
    DetailPrint "Done!"

    ; Registry
    WriteRegStr HKLM "Software\FusionCollectors\Sidecar" "InstallDir" "$INSTDIR"
    WriteRegStr HKLM "Software\FusionCollectors\Sidecar" "ConfigURL" "$ConfigURL"

    WriteUninstaller "$INSTDIR\uninstall.exe"

    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\CollectorSidecar" "DisplayName" "Collector Sidecar"
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\CollectorSidecar" "UninstallString" '"$INSTDIR\uninstall.exe"'
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\CollectorSidecar" "InstallLocation" "$INSTDIR"
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\CollectorSidecar" "Publisher" "BK-Lite"
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\CollectorSidecar" "DisplayVersion" "1.0.0"
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\CollectorSidecar" "DisplayIcon" "$INSTDIR\installer.ico"
    WriteRegDWORD HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\CollectorSidecar" "NoModify" 1
    WriteRegDWORD HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\CollectorSidecar" "NoRepair" 1

    ${GetSize} "$INSTDIR" "/S=0K" $0 $1 $2
    IntFmt $0 "0x%08X" $0
    WriteRegDWORD HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\CollectorSidecar" "EstimatedSize" "$0"

    File "installer.ico"
SectionEnd

; ============================================================================
; Uninstall
; ============================================================================

Section "Uninstall"
    DetailPrint "Stopping service..."
    nsExec::ExecToLog 'sc.exe stop sidecar'
    Sleep 2000

    DetailPrint "Removing service..."
    nsExec::ExecToLog 'sc.exe delete sidecar'
    Sleep 1000

    DetailPrint "Removing files..."
    Delete "$INSTDIR\collector-sidecar.exe"
    Delete "$INSTDIR\sidecar.yml"
    Delete "$INSTDIR\installer.ico"
    Delete "$INSTDIR\uninstall.exe"
    Delete "$INSTDIR\setup-worker.exe"

    RMDir /r "$INSTDIR\bin"
    RMDir /r "$INSTDIR\cache"
    RMDir /r "$INSTDIR\logs"
    RMDir /r "$INSTDIR\generated"
    RMDir "$INSTDIR"

    DeleteRegKey HKLM "Software\FusionCollectors\Sidecar"
    DeleteRegKey HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\CollectorSidecar"

    DetailPrint "Done."
SectionEnd
