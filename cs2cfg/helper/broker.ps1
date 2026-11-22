# CS CONFIG AI helper: the one part of the app that runs as administrator.
#
# Installed once, from the first-run setup, behind the only administrator
# prompt the app ever raises. After that the app asks this script to do a
# short, fixed list of jobs by dropping a request file and starting a
# scheduled task, and Windows does not prompt again.
#
# What keeps that safe:
#   * This file lives under Program Files, where only administrators can
#     change it. Nothing the app can rewrite as a normal user is ever run
#     elevated.
#   * It does a FIXED list of jobs (see $Jobs below). There is no "run this
#     command", no paths to programs taken from a request, no script text
#     taken from a request. Every argument is checked against a strict shape
#     here, whatever the app already checked.
#   * Firewall rules it makes are all in one group of its own and only ever
#     block CS2's own traffic; it never removes a rule it did not make.
#   * Requests are read, never echoed back, and never followed through links.
#
# Version must match HELPER_VERSION in cs2cfg/elevated.py. A newer app with a
# newer helper asks once more to put the new one in place; nothing else does.

$ErrorActionPreference = 'Stop'
$Version = 3

$Root     = Join-Path $env:ProgramData 'CS CONFIG AI Helper'
$Requests = Join-Path $Root 'requests'
$Claimed  = Join-Path $Root 'claimed'
$Results  = Join-Path $Root 'results'
$FwGroup  = 'CS CONFIG AI region lock'
$Program  = Join-Path $env:ProgramFiles 'CS CONFIG AI Helper'

$NameShape = '^[A-Za-z0-9 _\-\.\(\)]{1,48}$'
$IdShape   = '^[A-Za-z0-9\-]{8,64}$'
$GuidShape = '^[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}$'
$Peripheral = @('Mouse','Keyboard','HIDClass','AudioEndpoint','Media','USB','Bluetooth','Image')
$Essential  = @('Mouse','Keyboard')

function Test-Cidr([string]$text) {
    if ($text -notmatch '^(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})(/(\d{1,2}))?$') { return $false }
    foreach ($i in 1..4) { if ([int]$Matches[$i] -gt 255) { return $false } }
    if ($Matches[6] -and ([int]$Matches[6] -lt 8 -or [int]$Matches[6] -gt 32)) { return $false }
    return $true
}

function Get-Cs2Program([string]$path) {
    # Only ever CS2 itself. The path comes from the app, so it is checked by
    # shape AND by what is actually there.
    if (-not $path) { throw 'no CS2 path given' }
    if ($path -notmatch '\\game\\bin\\win64\\cs2\.exe$') { throw 'that is not CS2' }
    $item = Get-Item -LiteralPath $path -ErrorAction Stop
    if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'that is not CS2' }
    return $item.FullName
}

function Invoke-FirewallLock($a) {
    $program = Get-Cs2Program ([string]$a.program)
    $regions = @($a.regions)
    if ($regions.Count -lt 1 -or $regions.Count -gt 64) { throw 'between 1 and 64 regions' }
    $total = 0
    foreach ($r in $regions) {
        if ([string]$r.name -notmatch $NameShape) { throw 'bad region name' }
        $cidrs = @($r.cidrs)
        if ($cidrs.Count -lt 1) { throw 'a region with no addresses' }
        foreach ($c in $cidrs) { if (-not (Test-Cidr ([string]$c))) { throw "bad address $c" } }
        $total += $cidrs.Count
    }
    if ($total -gt 2000) { throw 'too many addresses' }

    Remove-NetFirewallRule -Group $FwGroup -ErrorAction SilentlyContinue
    foreach ($r in $regions) {
        New-NetFirewallRule -DisplayName ("CS CONFIG AI lock - " + $r.name) -Group $FwGroup `
            -Direction Outbound -Action Block -Program $program `
            -RemoteAddress ([string[]]@($r.cidrs)) -Profile Any | Out-Null
    }
    return @{ ok = $true; detail = "blocked $($regions.Count) regions for CS2"; rules = $regions.Count }
}

function Invoke-FirewallUnlock($a) {
    Remove-NetFirewallRule -Group $FwGroup -ErrorAction SilentlyContinue
    return @{ ok = $true; detail = 'all regions open again' }
}

function Invoke-FirewallStatus($a) {
    $names = @(Get-NetFirewallRule -Group $FwGroup -ErrorAction SilentlyContinue |
               ForEach-Object { $_.DisplayName -replace '^CS CONFIG AI lock - ', '' })
    return @{ ok = $true; blocked = $names }
}

function Invoke-DnsFlush($a) {
    Clear-DnsClientCache
    return @{ ok = $true; detail = 'DNS cache cleared' }
}

function Invoke-AdapterRestart($a) {
    $name = [string]$a.name
    $adapter = Get-NetAdapter -Physical | Where-Object { $_.Name -ceq $name } | Select-Object -First 1
    if (-not $adapter) { throw 'that adapter is not on this PC' }
    Restart-NetAdapter -InputObject $adapter -Confirm:$false
    Start-Sleep -Seconds 4
    $now = Get-NetAdapter -Name $adapter.Name -ErrorAction SilentlyContinue
    $up = [bool]($now -and $now.Status -eq 'Up')
    return @{ ok = $up; detail = $(if ($up) { "$name came back up" } else { "$name has not come back yet" }) }
}

function Invoke-AudioRestart($a) {
    Restart-Service -Name audiosrv -Force
    Start-Sleep -Seconds 2
    $up = ((Get-Service -Name audiosrv).Status -eq 'Running')
    return @{ ok = $up; detail = $(if ($up) { 'Windows Audio restarted' } else { 'Windows Audio did not come back' }) }
}

function Invoke-DeviceRestart($a) {
    $id = [string]$a.instance_id
    $d = Get-PnpDevice -InstanceId $id -PresentOnly
    if ($Peripheral -notcontains $d.Class) { throw 'only peripherals can be restarted' }
    if ($Essential -contains $d.Class) {
        $same = @(Get-PnpDevice -PresentOnly -Status OK | Where-Object { $_.Class -eq $d.Class })
        if ($same.Count -le 1) { throw "this is the only $($d.Class.ToLower()) on the PC" }
    }
    try {
        Disable-PnpDevice -InstanceId $id -Confirm:$false
        Start-Sleep -Milliseconds 900
    } finally {
        Enable-PnpDevice -InstanceId $id -Confirm:$false -ErrorAction SilentlyContinue
    }
    Start-Sleep -Seconds 2
    $back = Get-PnpDevice -InstanceId $id -ErrorAction SilentlyContinue
    $okay = [bool]($back -and $back.Status -eq 'OK')
    return @{ ok = $okay; detail = $(if ($okay) { "$($d.FriendlyName) is back" } else { "$($d.FriendlyName) has not come back -- unplug and replug it" }) }
}

function Invoke-PowerSet($a) {
    $guid = [string]$a.guid
    if ($guid -notmatch $GuidShape) { throw 'bad power plan id' }
    $list = (cmd /c 'powercfg /list') -join "`n"
    if ($list -notmatch [regex]::Escape($guid)) { throw 'no such power plan' }
    $msg = cmd /c "powercfg /setactive $guid 2>&1"
    if ($LASTEXITCODE -ne 0) { throw ($msg -join "`n") }
    return @{ ok = $true }
}

function Invoke-CfgGrant($a) {
    # Lets this Windows user write CS2's cfg folder without asking again --
    # for a game installed after setup, or a library on a locked drive.
    $path = [string]$a.path
    if ($path -notmatch '\\steamapps\\common\\[^\\]+\\game\\csgo\\cfg\\?$') { throw 'that is not a CS2 cfg folder' }
    $item = Get-Item -LiteralPath $path
    if (-not $item.PSIsContainer -or ($item.Attributes -band [IO.FileAttributes]::ReparsePoint)) { throw 'that is not a CS2 cfg folder' }
    $user = [Security.Principal.WindowsIdentity]::GetCurrent().User
    $acl = Get-Acl -LiteralPath $item.FullName
    $rule = New-Object Security.AccessControl.FileSystemAccessRule($user, 'Modify', 'ContainerInherit,ObjectInherit', 'None', 'Allow')
    $acl.AddAccessRule($rule)
    Set-Acl -LiteralPath $item.FullName -AclObject $acl
    return @{ ok = $true; detail = 'CS2 cfg folder is writable' }
}

function Invoke-TempsWatch($a) {
    # Samples the two sensors that need administrator until the app closes.
    $appPid = [int]$a.pid
    $proc = Get-Process -Id $appPid -ErrorAction SilentlyContinue
    if (-not $proc) { throw 'the app is not running' }
    $out = Join-Path $Results 'temps.json'
    $deadline = (Get-Date).AddHours(12)
    while ((Get-Process -Id $appPid -ErrorAction SilentlyContinue) -and (Get-Date) -lt $deadline) {
        $zones = @(Get-CimInstance -Namespace root/wmi -ClassName MSAcpi_ThermalZoneTemperature -ErrorAction SilentlyContinue |
                   ForEach-Object { $_.CurrentTemperature })
        $drives = @(Get-PhysicalDisk -ErrorAction SilentlyContinue | ForEach-Object {
            $c = $_ | Get-StorageReliabilityCounter -ErrorAction SilentlyContinue
            [pscustomobject]@{ Name = $_.FriendlyName; Temp = $c.Temperature } })
        $payload = @{ at = [double](([DateTimeOffset]::UtcNow).ToUnixTimeMilliseconds() / 1000); zones = $zones; drives = $drives }
        Set-Content -LiteralPath $out -Encoding UTF8 -Value ($payload | ConvertTo-Json -Compress -Depth 4)
        Start-Sleep -Seconds 5
    }
    Remove-Item -LiteralPath $out -ErrorAction SilentlyContinue
    return @{ ok = $true; detail = 'stopped with the app' }
}

function Invoke-FaceitAc($a) {
    # The path comes from FACEIT's own uninstall entry, which only an
    # administrator could have written -- never from the request.
    $keys = @('HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\*',
              'HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\*')
    $entry = Get-ItemProperty $keys -ErrorAction SilentlyContinue |
             Where-Object { $_.DisplayName -match '^FACEIT' -and $_.DisplayName -match 'Anti' -and $_.InstallLocation } |
             Select-Object -First 1
    if (-not $entry) { throw 'FACEIT Anti-Cheat is not installed' }
    $exe = Join-Path $entry.InstallLocation 'faceitclient.exe'
    if (-not (Test-Path -LiteralPath $exe)) { throw 'FACEIT Anti-Cheat is not where its installer put it' }
    if (Get-Process -Name faceitclient -ErrorAction SilentlyContinue) { return @{ ok = $true; already = $true } }
    Start-Process -FilePath $exe -WorkingDirectory $entry.InstallLocation
    return @{ ok = $true; detail = 'FACEIT Anti-Cheat started' }
}

function Invoke-DefenderCs2($a) {
    # Only ever CS2's own install folder, found from cs2.exe itself.
    $exe = Get-Cs2Program ([string]$a.program)
    $folder = (Get-Item -LiteralPath $exe).Directory.Parent.Parent.Parent.FullName
    if ([bool]$a.on) { Add-MpPreference -ExclusionPath $folder; $d = 'CS2 folder excluded from real-time scanning' }
    else { Remove-MpPreference -ExclusionPath $folder; $d = 'CS2 folder is scanned normally again' }
    return @{ ok = $true; detail = $d; excluded = [bool]$a.on }
}

# NVIDIA's settings database, CS2's program profile only (Edy, Nov 21 2026).
# The driver saves settings only for an administrator, so this is the one
# place the app writes them. Fixed code, compiled here from this file under
# Program Files; a request only supplies setting numbers and values.
$NvSource = @'
using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;
public static class CsCfgNv {
    [DllImport("nvapi64.dll", EntryPoint = "nvapi_QueryInterface", CallingConvention = CallingConvention.Cdecl)]
    static extern IntPtr QueryInterface(uint id);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int Fn0();
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int FnOut(out IntPtr h);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int Fn1(IntPtr a);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int FnFindApp(IntPtr s, IntPtr name, out IntPtr p, IntPtr app);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int FnFind(IntPtr s, IntPtr name, out IntPtr p);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int FnCreate(IntPtr s, IntPtr info, out IntPtr p);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int FnPP(IntPtr s, IntPtr p, IntPtr x);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int FnPId(IntPtr s, IntPtr p, uint id);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int FnGet(IntPtr s, IntPtr p, uint id, IntPtr x);

    const int SettingSize = 12320, ProfileSize = 4116, AppSize = 20488;
    const string Cs2 = "cs2.exe", OwnProfile = "CS CONFIG AI - Counter-Strike 2";

    static T F<T>(uint id) where T : class {
        IntPtr at = QueryInterface(id);
        if (at == IntPtr.Zero) throw new Exception("this NVIDIA driver does not allow changing settings");
        return (T)(object)Marshal.GetDelegateForFunctionPointer(at, typeof(T));
    }
    static void Check(int code, string what) {
        if (code != 0) throw new Exception(what + " failed (NVIDIA code " + code + ")");
    }
    static IntPtr Buf(int size, List<IntPtr> held) {
        IntPtr p = Marshal.AllocHGlobal(size);
        held.Add(p);
        Marshal.Copy(new byte[size], 0, p, size);
        return p;
    }
    static void Wide(IntPtr p, int offset, string text) {
        for (int i = 0; i < text.Length; i++) Marshal.WriteInt16(p, offset + 2 * i, (short)text[i]);
    }
    static IntPtr Cs2Profile(IntPtr session, List<IntPtr> held) {
        IntPtr name = Buf(4096, held); Wide(name, 0, Cs2);
        IntPtr app = Buf(AppSize, held); Marshal.WriteInt32(app, 0, AppSize | (4 << 16));
        IntPtr profile;
        int code = F<FnFindApp>(0xEEE566B2)(session, name, out profile, app);
        if (code == 0) return profile;
        if (code != -166 && code != -163) Check(code, "finding CS2's NVIDIA profile");
        IntPtr own = Buf(4096, held); Wide(own, 0, OwnProfile);
        code = F<FnFind>(0x7E4A9A0B)(session, own, out profile);
        if (code == -163) {
            IntPtr info = Buf(ProfileSize, held);
            Marshal.WriteInt32(info, 0, ProfileSize | (1 << 16));
            Wide(info, 4, OwnProfile);
            Check(F<FnCreate>(0xCC176068)(session, info, out profile), "making a profile for CS2");
        } else Check(code, "finding the app's CS2 profile");
        IntPtr add = Buf(AppSize, held);
        Marshal.WriteInt32(add, 0, AppSize | (4 << 16));
        Wide(add, 8, Cs2);
        Check(F<FnPP>(0x4347A9DE)(session, profile, add), "adding CS2 to its profile");
        return profile;
    }
    static string Read(IntPtr session, IntPtr profile, uint id, IntPtr setting) {
        Marshal.Copy(new byte[SettingSize], 0, setting, SettingSize);
        Marshal.WriteInt32(setting, 0, SettingSize | (1 << 16));
        int code = F<FnGet>(0x73BF8338)(session, profile, id, setting);
        if (code == -160 || code == -163 || code == -166) return "none";
        Check(code, "reading CS2's NVIDIA profile");
        if (Marshal.ReadInt32(setting, 4104) != 0) return "none";
        if (Marshal.ReadInt32(setting, 4112) != 0) return "default";
        return ((uint)Marshal.ReadInt32(setting, 8220)).ToString();
    }
    static void Change(IntPtr session, IntPtr profile, uint id, string value, IntPtr setting) {
        int code;
        if (value == "none") {
            code = F<FnPId>(0xE4A26362)(session, profile, id);
            if (code != -160) Check(code, "removing a CS2 NVIDIA setting");
            return;
        }
        if (value == "default") {
            code = F<FnPId>(0x53F0381E)(session, profile, id);
            if (code != -160 && code != -169) Check(code, "putting back NVIDIA's own CS2 setting");
            return;
        }
        uint number = UInt32.Parse(value);
        Marshal.Copy(new byte[SettingSize], 0, setting, SettingSize);
        Marshal.WriteInt32(setting, 0, SettingSize | (1 << 16));
        Marshal.WriteInt32(setting, 4100, (int)id);
        Marshal.WriteInt32(setting, 4104, 0);
        Marshal.WriteInt32(setting, 8220, unchecked((int)number));
        Check(F<FnPP>(0x577DD202)(session, profile, setting), "changing CS2's NVIDIA profile");
    }
    public static string[] Apply(uint[] ids, string[] values) {
        var held = new List<IntPtr>();
        IntPtr session = IntPtr.Zero;
        Check(F<Fn0>(0x0150E828)(), "starting the NVIDIA driver");
        try {
            Check(F<FnOut>(0x0694D52E)(out session), "opening NVIDIA settings");
            Check(F<Fn1>(0x375DBD6B)(session), "loading NVIDIA settings");
            IntPtr profile = Cs2Profile(session, held);
            IntPtr setting = Buf(SettingSize, held);
            var before = new string[ids.Length];
            for (int i = 0; i < ids.Length; i++) before[i] = Read(session, profile, ids[i], setting);
            for (int i = 0; i < ids.Length; i++) Change(session, profile, ids[i], values[i], setting);
            Check(F<Fn1>(0xFCBC7E14)(session), "saving NVIDIA settings");
            return before;
        } finally {
            if (session != IntPtr.Zero) { try { F<Fn1>(0xDAD9CFF8)(session); } catch {} }
            try { F<Fn0>(0xD22BDD7E)(); } catch {}
            foreach (IntPtr p in held) Marshal.FreeHGlobal(p);
        }
    }
}
'@

function Invoke-NvidiaSet($a) {
    # Only DWORD settings, only CS2's program profile (never the global one).
    $changes = @($a.changes)
    if ($changes.Count -lt 1 -or $changes.Count -gt 64) { throw 'between 1 and 64 NVIDIA settings' }
    $ids = New-Object 'uint32[]' $changes.Count
    $values = New-Object 'string[]' $changes.Count
    for ($i = 0; $i -lt $changes.Count; $i++) {
        $id = [int64]$changes[$i].id
        if ($id -le 0 -or $id -gt 4294967295) { throw 'bad NVIDIA setting' }
        $ids[$i] = [uint32]$id
        $v = $changes[$i].value
        if ($null -eq $v) { $values[$i] = 'none' }
        elseif ([string]$v -eq 'default') { $values[$i] = 'default' }
        else {
            if ([string]$v -notmatch '^\d{1,10}$') { throw 'bad NVIDIA value' }
            $n = [int64][string]$v
            if ($n -gt 4294967295) { throw 'bad NVIDIA value' }
            $values[$i] = [string]$n
        }
    }
    if (-not ('CsCfgNv' -as [type])) { Add-Type -TypeDefinition $NvSource -Language CSharp }
    $before = [CsCfgNv]::Apply($ids, $values)
    $list = @()
    for ($i = 0; $i -lt $ids.Count; $i++) {
        $was = $before[$i]
        $value = $null
        if ($was -eq 'default') { $value = 'default' } elseif ($was -ne 'none') { $value = [int64]$was }
        $list += @{ id = [int64]$ids[$i]; value = $value }
    }
    return @{ ok = $true; detail = "changed $($ids.Count) NVIDIA settings for CS2"; before = $list }
}

function Invoke-HelperUninstall($a) {
    # The app is being uninstalled: take back everything the helper made.
    # Nothing from the request is used; every path below is a constant.
    Remove-NetFirewallRule -Group $FwGroup -ErrorAction SilentlyContinue
    # Defender exclusions on a CS2 install folder: the only kind this app adds
    # (defender.cs2 here, and Fix It's "Exclude CS2 from antivirus scanning").
    $excluded = 0
    try {
        foreach ($path in @((Get-MpPreference).ExclusionPath)) {
            if ([string]$path -match '\\steamapps\\common\\Counter-Strike Global Offensive\\?$') {
                Remove-MpPreference -ExclusionPath $path
                $excluded++
            }
        }
    } catch {}
    # The task, its folder and both helper folders go after this broker has
    # written its answer and exited, since it is running from them.
    $later = "Start-Sleep -Seconds 6; " +
        "Unregister-ScheduledTask -TaskPath '\CS CONFIG AI\' -TaskName 'Helper' -Confirm:`$false -ErrorAction SilentlyContinue; " +
        "try { `$s = New-Object -ComObject Schedule.Service; `$s.Connect(); `$s.GetFolder('\').DeleteFolder('CS CONFIG AI', 0) } catch {}; " +
        "Remove-Item -LiteralPath '" + $Program + "' -Recurse -Force -ErrorAction SilentlyContinue; " +
        "Remove-Item -LiteralPath '" + $Root + "' -Recurse -Force -ErrorAction SilentlyContinue"
    $posh = Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
    Start-Process -FilePath $posh -WindowStyle Hidden -ArgumentList @('-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass', '-Command', $later)
    return @{ ok = $true; detail = "firewall rules removed; $excluded Defender exclusion(s) removed; helper removes itself in a few seconds" }
}

$Jobs = @{
    'helper.uninstall' = { param($a) Invoke-HelperUninstall $a }
    'defender.cs2'     = { param($a) Invoke-DefenderCs2 $a }
    'nvidia.set'       = { param($a) Invoke-NvidiaSet $a }
    'ping'             = { param($a) @{ ok = $true; version = $Version } }
    'firewall.lock'    = { param($a) Invoke-FirewallLock $a }
    'firewall.unlock'  = { param($a) Invoke-FirewallUnlock $a }
    'firewall.status'  = { param($a) Invoke-FirewallStatus $a }
    'dns.flush'        = { param($a) Invoke-DnsFlush $a }
    'adapter.restart'  = { param($a) Invoke-AdapterRestart $a }
    'audio.restart'    = { param($a) Invoke-AudioRestart $a }
    'device.restart'   = { param($a) Invoke-DeviceRestart $a }
    'power.set'        = { param($a) Invoke-PowerSet $a }
    'cfg.grant'        = { param($a) Invoke-CfgGrant $a }
    'temps.watch'      = { param($a) Invoke-TempsWatch $a }
    'faceit_ac.start'  = { param($a) Invoke-FaceitAc $a }
}

function Write-Result([string]$id, $result) {
    $result['version'] = $Version
    $tmp = Join-Path $Results ($id + '.tmp')
    Set-Content -LiteralPath $tmp -Encoding UTF8 -Value ($result | ConvertTo-Json -Compress -Depth 4)
    Move-Item -LiteralPath $tmp -Destination (Join-Path $Results ($id + '.json')) -Force
}

# Old results nobody collected.
Get-ChildItem -LiteralPath $Results -File -ErrorAction SilentlyContinue |
    Where-Object { $_.Name -ne 'temps.json' -and $_.LastWriteTime -lt (Get-Date).AddMinutes(-10) } |
    Remove-Item -Force -ErrorAction SilentlyContinue

foreach ($file in @(Get-ChildItem -LiteralPath $Requests -File -Filter '*.json' -ErrorAction SilentlyContinue)) {
    if ($file.Attributes -band [IO.FileAttributes]::ReparsePoint) {
        Remove-Item -LiteralPath $file.FullName -Force -ErrorAction SilentlyContinue
        continue
    }
    $id = [IO.Path]::GetFileNameWithoutExtension($file.Name)
    if ($id -notmatch $IdShape -or $file.Length -gt 262144) {
        Remove-Item -LiteralPath $file.FullName -Force -ErrorAction SilentlyContinue
        continue
    }
    # Claim it by moving it, so two copies of this task never run one job twice.
    $mine = Join-Path $Claimed $file.Name
    try { Move-Item -LiteralPath $file.FullName -Destination $mine -ErrorAction Stop } catch { continue }

    try {
        $request = Get-Content -LiteralPath $mine -Raw -Encoding UTF8 | ConvertFrom-Json
        $op = [string]$request.op
        if (-not $Jobs.ContainsKey($op)) { throw 'the helper does not do that' }
        $result = & $Jobs[$op] $request.args
        if (-not ($result -is [hashtable])) { $result = @{ ok = $true } }
    } catch {
        $result = @{ ok = $false; error = $_.Exception.Message }
    } finally {
        Remove-Item -LiteralPath $mine -Force -ErrorAction SilentlyContinue
    }
    Write-Result $id $result
}
