# CS CONFIG AI helper: one-time setup. Runs behind the app's only
# administrator prompt, from the first-run setup (or "Run setup again").
#
# Does, once:
#   1. Copies broker.ps1 to Program Files, where only administrators can
#      change it.
#   2. Makes the request/result folders under ProgramData: this Windows user
#      may drop requests and read results; only administrators run anything.
#   3. Registers a scheduled task that runs broker.ps1 with highest privileges
#      for this user, on demand only. Starting it later raises no prompt.
#   4. Adds this user to "Performance Log Users", so the overlay can read
#      performance counters without administrator (takes effect at next sign-in).
#   5. Makes CS2's cfg folder writable for this user, if one was given.
#
# Remove with -Remove: deletes the task, the firewall rules the helper made,
# and both folders. Leaves the group membership (harmless, and removing it
# could break something else that relies on it).

param(
    [string]$Source = $PSScriptRoot,
    [string]$CfgPath = '',
    [switch]$Remove
)

$ErrorActionPreference = 'Stop'
$Program  = Join-Path $env:ProgramFiles 'CS CONFIG AI Helper'
$Root     = Join-Path $env:ProgramData 'CS CONFIG AI Helper'
$TaskPath = '\CS CONFIG AI\'
$TaskName = 'Helper'
$FwGroup  = 'CS CONFIG AI region lock'
$me = [Security.Principal.WindowsIdentity]::GetCurrent()
$user = $me.User
$steps = @()

if ($Remove) {
    Unregister-ScheduledTask -TaskPath $TaskPath -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
    Remove-NetFirewallRule -Group $FwGroup -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $Program -Recurse -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $Root -Recurse -Force -ErrorAction SilentlyContinue
    return @{ ok = $true; detail = 'helper removed' }
}

# 1. The broker, where a normal user cannot rewrite it.
New-Item -ItemType Directory -Force -Path $Program | Out-Null
Copy-Item -LiteralPath (Join-Path $Source 'broker.ps1') -Destination (Join-Path $Program 'broker.ps1') -Force
$steps += 'helper installed'

# 2. The mailbox. Inheritance is cut so ProgramData's own defaults (which let
#    any user create files) do not leak in.
$admins = New-Object Security.Principal.SecurityIdentifier('S-1-5-32-544')
$system = New-Object Security.Principal.SecurityIdentifier('S-1-5-18')
function New-Folder([string]$path, [string]$userRights) {
    New-Item -ItemType Directory -Force -Path $path | Out-Null
    $acl = New-Object Security.AccessControl.DirectorySecurity
    $acl.SetAccessRuleProtection($true, $false)
    $inherit = 'ContainerInherit,ObjectInherit'
    $acl.AddAccessRule((New-Object Security.AccessControl.FileSystemAccessRule($admins, 'FullControl', $inherit, 'None', 'Allow')))
    $acl.AddAccessRule((New-Object Security.AccessControl.FileSystemAccessRule($system, 'FullControl', $inherit, 'None', 'Allow')))
    if ($userRights) {
        $acl.AddAccessRule((New-Object Security.AccessControl.FileSystemAccessRule($user, $userRights, $inherit, 'None', 'Allow')))
    }
    $acl.SetOwner($admins)
    Set-Acl -LiteralPath $path -AclObject $acl
}
New-Folder $Root 'ReadAndExecute'
New-Folder (Join-Path $Root 'requests') 'Modify'
New-Folder (Join-Path $Root 'claimed') ''
New-Folder (Join-Path $Root 'results') 'ReadAndExecute'
$steps += 'request folders made'

# 3. The task. On demand only, this user, highest privileges, hidden.
$broker = Join-Path $Program 'broker.ps1'
$action = New-ScheduledTaskAction -Execute 'powershell.exe' `
    -Argument "-NoProfile -NonInteractive -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$broker`""
$principal = New-ScheduledTaskPrincipal -UserId $me.Name -LogonType Interactive -RunLevel Highest
$settings = New-ScheduledTaskSettingsSet -MultipleInstances Parallel -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Hours 12) -Hidden
Register-ScheduledTask -TaskPath $TaskPath -TaskName $TaskName -Action $action -Principal $principal `
    -Settings $settings -Description 'Does a fixed list of jobs for CS CONFIG AI without asking for administrator each time.' `
    -Force | Out-Null
$steps += 'task registered'

# 4. Performance counters for the overlay.
try {
    Add-LocalGroupMember -SID 'S-1-5-32-559' -Member $user.Value -ErrorAction Stop
    $steps += 'added to Performance Log Users'
} catch {
    if ($_.Exception.Message -match 'already a member') { $steps += 'already in Performance Log Users' }
    else { $steps += ('could not join Performance Log Users: ' + $_.Exception.Message) }
}

# 5. CS2's cfg folder.
if ($CfgPath -and ($CfgPath -match '\\game\\csgo\\cfg\\?$') -and (Test-Path -LiteralPath $CfgPath -PathType Container)) {
    $acl = Get-Acl -LiteralPath $CfgPath
    $acl.AddAccessRule((New-Object Security.AccessControl.FileSystemAccessRule($user, 'Modify', 'ContainerInherit,ObjectInherit', 'None', 'Allow')))
    Set-Acl -LiteralPath $CfgPath -AclObject $acl
    $steps += 'CS2 cfg folder writable'
}

return @{ ok = $true; detail = ($steps -join '; ') }
