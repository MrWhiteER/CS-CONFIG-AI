<#
    Hardware probe for cs2-autoconfig.

    Emits a single compressed JSON object on stdout and nothing else, so the
    Python side can parse it without heuristics. Every section is wrapped in
    its own try/catch: a machine that refuses one WMI class should still give
    us the rest rather than failing the whole run.
#>

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'

function Try-Section {
    param([scriptblock]$Body, $Fallback = $null)
    try { & $Body } catch { return $Fallback }
}

# --- OS -------------------------------------------------------------------
$os = Try-Section {
    $o = Get-CimInstance Win32_OperatingSystem
    [pscustomobject]@{
        caption      = $o.Caption
        version      = $o.Version
        build        = $o.BuildNumber
        architecture = $o.OSArchitecture
    }
}

# --- CPU ------------------------------------------------------------------
$cpu = Try-Section {
    $c = @(Get-CimInstance Win32_Processor)[0]
    [pscustomobject]@{
        name          = ($c.Name -replace '\s+', ' ').Trim()
        manufacturer  = $c.Manufacturer
        cores         = [int]$c.NumberOfCores
        threads       = [int]$c.NumberOfLogicalProcessors
        max_clock_mhz = [int]$c.MaxClockSpeed
    }
}

# --- GPUs -----------------------------------------------------------------
# Win32_VideoController.AdapterRAM is a signed 32-bit field, so it saturates at
# ~4 GB and lies about every modern card. The registry holds the real number.
$vramByName = @{}
$null = Try-Section {
    $classKey = 'HKLM:\SYSTEM\CurrentControlSet\Control\Class\{4d36e968-e325-11ce-bfc1-08002be10318}'
    Get-ChildItem $classKey -ErrorAction SilentlyContinue | ForEach-Object {
        $props = Get-ItemProperty $_.PSPath -ErrorAction SilentlyContinue
        $desc = $props.'HardwareInformation.AdapterString'
        if ($desc -is [byte[]]) { $desc = [System.Text.Encoding]::Unicode.GetString($desc).Trim([char]0) }
        $mem = $props.'HardwareInformation.qwMemorySize'
        if ($desc -and $mem) { $vramByName[[string]$desc] = [int64]$mem }
    }
}

$gpus = Try-Section {
    Get-CimInstance Win32_VideoController | ForEach-Object {
        $name = ($_.Name -replace '\s+', ' ').Trim()
        $vram = $null
        foreach ($k in $vramByName.Keys) {
            if ($k -and ($name -like "*$k*" -or $k -like "*$name*")) { $vram = $vramByName[$k]; break }
        }
        if (-not $vram -and $_.AdapterRAM -gt 0) { $vram = [int64]$_.AdapterRAM }

        $vendorId = $null; $deviceId = $null
        if ($_.PNPDeviceID -match 'VEN_([0-9A-Fa-f]{4})&DEV_([0-9A-Fa-f]{4})') {
            $vendorId = [Convert]::ToInt32($Matches[1], 16)
            $deviceId = [Convert]::ToInt32($Matches[2], 16)
        }

        [pscustomobject]@{
            name            = $name
            driver_version  = $_.DriverVersion
            driver_date     = if ($_.DriverDate) { $_.DriverDate.ToString('yyyy-MM-dd') } else { $null }
            vram_bytes      = $vram
            vendor_id       = $vendorId
            device_id       = $deviceId
            current_width   = [int]$_.CurrentHorizontalResolution
            current_height  = [int]$_.CurrentVerticalResolution
            current_refresh = [int]$_.CurrentRefreshRate
            status          = $_.Status
        }
    }
} @()

# --- Memory ---------------------------------------------------------------
$memory = Try-Section {
    $cs = Get-CimInstance Win32_ComputerSystem
    $sticks = @(Get-CimInstance Win32_PhysicalMemory)
    [pscustomobject]@{
        total_bytes = [int64]$cs.TotalPhysicalMemory
        modules     = $sticks.Count
        speed_mts   = if ($sticks) { [int](@($sticks | ForEach-Object { $_.Speed }) | Measure-Object -Maximum).Maximum } else { $null }
    }
}

# --- Display modes --------------------------------------------------------
# EnumDisplaySettings gives every mode the driver will accept, which is the
# only reliable way to learn the panel's true maximum refresh rate.
$displays = Try-Section {
    Add-Type -ErrorAction Stop -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
public class Cs2Disp {
    [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Ansi)]
    public struct DEVMODE {
        [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 32)] public string dmDeviceName;
        public short dmSpecVersion; public short dmDriverVersion; public short dmSize; public short dmDriverExtra;
        public int dmFields; public int dmPositionX; public int dmPositionY;
        public int dmDisplayOrientation; public int dmDisplayFixedOutput;
        public short dmColor; public short dmDuplex; public short dmYResolution; public short dmTTOption; public short dmCollate;
        [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 32)] public string dmFormName;
        public short dmLogPixels; public int dmBitsPerPel; public int dmPelsWidth; public int dmPelsHeight;
        public int dmDisplayFlags; public int dmDisplayFrequency;
        public int dmICMMethod; public int dmICMIntent; public int dmMediaType; public int dmDitherType;
        public int dmReserved1; public int dmReserved2; public int dmPanningWidth; public int dmPanningHeight;
    }
    [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Ansi)]
    public struct DISPLAY_DEVICE {
        public int cb;
        [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 32)] public string DeviceName;
        [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 128)] public string DeviceString;
        public int StateFlags;
        [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 128)] public string DeviceID;
        [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 128)] public string DeviceKey;
    }
    [DllImport("user32.dll", CharSet = CharSet.Ansi)]
    public static extern bool EnumDisplaySettings(string dev, int mode, ref DEVMODE dm);
    [DllImport("user32.dll", CharSet = CharSet.Ansi)]
    public static extern bool EnumDisplayDevices(string dev, uint num, ref DISPLAY_DEVICE dd, uint flags);
}
'@

    $result = @()
    $devNum = 0
    while ($true) {
        $dd = New-Object Cs2Disp+DISPLAY_DEVICE
        $dd.cb = [System.Runtime.InteropServices.Marshal]::SizeOf($dd)
        if (-not [Cs2Disp]::EnumDisplayDevices($null, $devNum, [ref]$dd, 0)) { break }
        $devNum++
        if (($dd.StateFlags -band 0x1) -eq 0) { continue }   # not attached to desktop

        $dm = New-Object Cs2Disp+DEVMODE
        $dm.dmSize = [short][System.Runtime.InteropServices.Marshal]::SizeOf($dm)

        $modes = @()
        $i = 0
        while ([Cs2Disp]::EnumDisplaySettings($dd.DeviceName, $i, [ref]$dm)) {
            if ($dm.dmBitsPerPel -ge 32) {
                $modes += [pscustomobject]@{ w = $dm.dmPelsWidth; h = $dm.dmPelsHeight; hz = $dm.dmDisplayFrequency }
            }
            $i++
            if ($i -gt 4000) { break }
        }

        $cur = New-Object Cs2Disp+DEVMODE
        $cur.dmSize = [short][System.Runtime.InteropServices.Marshal]::SizeOf($cur)
        $null = [Cs2Disp]::EnumDisplaySettings($dd.DeviceName, -1, [ref]$cur)   # ENUM_CURRENT_SETTINGS

        $native = $modes | Sort-Object @{e={$_.w * $_.h}}, @{e={$_.hz}} -Descending | Select-Object -First 1
        $maxHzAtNative = 0
        if ($native) {
            $maxHzAtNative = ($modes | Where-Object { $_.w -eq $native.w -and $_.h -eq $native.h } |
                              Measure-Object hz -Maximum).Maximum
        }

        $result += [pscustomobject]@{
            device          = $dd.DeviceName
            monitor         = $dd.DeviceString
            primary         = (($dd.StateFlags -band 0x4) -ne 0)
            current_width   = $cur.dmPelsWidth
            current_height  = $cur.dmPelsHeight
            current_refresh = $cur.dmDisplayFrequency
            native_width    = if ($native) { $native.w } else { $null }
            native_height   = if ($native) { $native.h } else { $null }
            max_refresh     = [int]$maxHzAtNative
            mode_count      = $modes.Count
        }
    }
    ,$result
} @()

$displaySource = 'enum_display_settings'

# Fallback 1: the WMI monitor tables. EnumDisplayDevices needs a real window
# station, so it returns nothing when we run from a service or a detached
# shell. WMI still answers there, and still knows the panel's mode list.
if (-not $displays -or @($displays).Count -eq 0) {
    $displays = Try-Section {
        $modeSets = @(Get-CimInstance -Namespace root\wmi -ClassName WmiMonitorListedSupportedSourceModes -ErrorAction Stop)
        $out = @()
        foreach ($set in $modeSets) {
            $modes = @($set.MonitorSourceModes | ForEach-Object {
                $den = if ($_.VerticalRefreshRateDenominator) { $_.VerticalRefreshRateDenominator } else { 1 }
                [pscustomobject]@{
                    w  = [int]$_.HorizontalActivePixels
                    h  = [int]$_.VerticalActivePixels
                    hz = [int][math]::Round($_.VerticalRefreshRateNumerator / $den)
                }
            })
            if (-not $modes) { continue }
            $native = $modes | Sort-Object @{e={$_.w * $_.h}}, @{e={$_.hz}} -Descending | Select-Object -First 1
            $maxHz = ($modes | Where-Object { $_.w -eq $native.w -and $_.h -eq $native.h } |
                      Measure-Object hz -Maximum).Maximum
            $out += [pscustomobject]@{
                device          = $set.InstanceName
                monitor         = $null
                primary         = ($out.Count -eq 0)
                current_width   = $null
                current_height  = $null
                current_refresh = $null
                native_width    = $native.w
                native_height   = $native.h
                max_refresh     = [int]$maxHz
                mode_count      = $modes.Count
            }
        }
        ,$out
    } @()
    if (@($displays).Count -gt 0) { $displaySource = 'wmi_monitor_modes' }
}

# Fallback 2: whatever the adapter reports it is currently driving. No mode
# list, so max_refresh can only be the current refresh rate.
if (-not $displays -or @($displays).Count -eq 0) {
    $displays = Try-Section {
        $out = @()
        foreach ($g in @($gpus)) {
            if ($g.current_width -gt 0) {
                $out += [pscustomobject]@{
                    device          = $g.name
                    monitor         = $null
                    primary         = ($out.Count -eq 0)
                    current_width   = $g.current_width
                    current_height  = $g.current_height
                    current_refresh = $g.current_refresh
                    native_width    = $g.current_width
                    native_height   = $g.current_height
                    max_refresh     = $g.current_refresh
                    mode_count      = 0
                }
            }
        }
        ,$out
    } @()
    if (@($displays).Count -gt 0) { $displaySource = 'video_controller' }
}

if (-not $displays -or @($displays).Count -eq 0) { $displaySource = 'none' }

# --- Storage --------------------------------------------------------------
$disks = Try-Section {
    Get-Volume -ErrorAction SilentlyContinue |
        Where-Object { $_.DriveLetter -and $_.DriveType -eq 'Fixed' } |
        ForEach-Object {
            $letter = $_.DriveLetter
            $media = Try-Section {
                (Get-Partition -DriveLetter $letter -ErrorAction Stop |
                 Get-Disk -ErrorAction Stop |
                 Get-PhysicalDisk -ErrorAction Stop).MediaType
            } 'Unknown'
            [pscustomobject]@{
                letter     = [string]$letter
                media_type = [string]$media
                free_bytes = [int64]$_.SizeRemaining
            }
        }
} @()

# --- Power plan -----------------------------------------------------------
# CS2 is latency sensitive; a Balanced plan parks cores and costs frametime.
$power = Try-Section {
    $line = powercfg /getactivescheme
    if ($line -match '\(([^)]+)\)') { $Matches[1] } else { $null }
}

[pscustomobject]@{
    schema     = 1
    os         = $os
    cpu        = $cpu
    gpus       = @($gpus)
    memory     = $memory
    displays   = @($displays)
    display_source = $displaySource
    disks      = @($disks)
    power_plan = $power
} | ConvertTo-Json -Depth 6 -Compress
