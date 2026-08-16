# Queries Windows for paired Bluetooth/media devices that expose a battery level
# and writes the results to battery.json next to this script, for dashboard.html to poll.
# Uses the undocumented-but-stable PnP device battery property key that Windows
# itself uses to show battery in Settings > Bluetooth & other devices.
#
# Also makes sure the local dashboard web server is up. dashboard.html must be loaded
# over http://127.0.0.1 (not file://) because Chrome/Edge block XHR reads of a second
# local file from a file:// page. This script's scheduled task ("At log on" triggers
# are blocked by policy on this machine) doubles as the thing that (re)starts the
# server if it's ever not running.

$dashboardDir = $PSScriptRoot
$outPath = Join-Path $dashboardDir 'battery.json'
$batteryKey = '{104EA319-6EE2-4701-BD47-8DDBF425BBE5} 2'
$serverPort = 8420
$serverScript = Join-Path $dashboardDir 'server.py'
# python.exe, not pythonw.exe: pythonw has no console, so sys.stderr is None and
# http.server's per-request logging throws, silently dropping every connection.
# -WindowStyle Hidden hides the window while still giving the process real
# stdout/stderr handles.
$python = 'C:\Users\Will\AppData\Local\Programs\Python\Python314\python.exe'

function Test-PortOpen($port) {
    try {
        $client = New-Object System.Net.Sockets.TcpClient
        $iar = $client.BeginConnect('127.0.0.1', $port, $null, $null)
        $ok = $iar.AsyncWaitHandle.WaitOne(300, $false) -and $client.Connected
        $client.Close()
        return $ok
    } catch { return $false }
}

if (-not (Test-PortOpen $serverPort)) {
    Start-Process -FilePath $python -ArgumentList @("$serverScript") -WindowStyle Hidden
}

# Raw Windows FriendlyName -> preferred display name. Windows' own name for a device
# isn't editable, so relabel here rather than in battery.json (which gets overwritten
# every 5 minutes).
$displayNames = @{
    'yz75pro5.0'  = 'YZ75 Pro Keyboard'
    'BT5.1 Mouse' = 'Reddragon Taipan Max'
}

$devices = Get-PnpDevice -PresentOnly | Where-Object {
    $_.Class -in @('Bluetooth', 'MEDIA', 'AudioEndpoint') -or
    $_.FriendlyName -match 'mouse|keyboard|headphone|headset|earbuds|buds|airpods'
}

$results = foreach ($d in $devices) {
    $prop = Get-PnpDeviceProperty -InstanceId $d.InstanceId -KeyName $batteryKey -ErrorAction SilentlyContinue
    if ($null -ne $prop.Data) {
        $rawName = $d.FriendlyName -replace ' Hands-Free AG$', ''
        [PSCustomObject]@{
            name    = if ($displayNames.ContainsKey($rawName)) { $displayNames[$rawName] } else { $rawName }
            battery = [int]$prop.Data
            online  = ($d.Status -eq 'OK')
        }
    }
}

$payload = [PSCustomObject]@{
    updated = (Get-Date).ToString('o')
    devices = @($results)
}

$payload | ConvertTo-Json -Depth 3 | Set-Content -Path $outPath -Encoding UTF8
