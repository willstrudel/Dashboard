# Starts the dashboard's local web server (server.py, http://127.0.0.1:8420) if it
# isn't already running. Meant to be launched at logon via a Startup folder shortcut
# — Task Scheduler's "At log on" trigger is blocked by policy on this machine, so
# check-bluetooth-battery.ps1's scheduled task can no longer be relied on to do this
# (and that task is disabled anyway, see decisions/log.md 2026-07-21).
#
# python.exe, not pythonw.exe: pythonw has no console, so sys.stderr is None and
# http.server's per-request logging throws, silently dropping every connection.
# -WindowStyle Hidden hides the window while still giving the process real
# stdout/stderr handles.

$dashboardDir = $PSScriptRoot
$serverScript = Join-Path $dashboardDir 'server.py'
$serverPort = 8420
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
