<#
  Schedule the daily update  (Step 6)
  ===================================
  What this file does:
      Creates a Windows Task Scheduler job that runs etl\daily_etl.py every day.

  Why 9:00 AM?
      AMFI publishes each day's NAV by about 11 PM, so a morning run picks up
      yesterday's NAV. If the PC is off at 9:00, Windows runs the task as soon
      as you switch it on.

  How to run (in the project folder):
      Create / update :  powershell -ExecutionPolicy Bypass -File scripts\schedule_daily_etl.ps1
      Remove          :  powershell -ExecutionPolicy Bypass -File scripts\schedule_daily_etl.ps1 -Remove
      Run it now      :  Start-ScheduledTask -TaskName "MF Portfolio Daily ETL"
      Last result     :  Get-ScheduledTaskInfo -TaskName "MF Portfolio Daily ETL"
                         (LastTaskResult 0 = success)
#>

param(
    [switch]$Remove,          # add -Remove to delete the task
    [string]$At = "09:00"     # add -At "20:00" to pick another time
)

# ---------------------------------------------------------------
# Settings
# ---------------------------------------------------------------
$TaskName   = "MF Portfolio Daily ETL"
$ProjectDir = Split-Path -Parent $PSScriptRoot                 # the folder above \scripts
$Python     = Join-Path $ProjectDir ".venv\Scripts\python.exe"


# ---------------------------------------------------------------
# Option: remove the task
# ---------------------------------------------------------------
if ($Remove) {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
    Write-Host "Removed task '$TaskName'."
    return
}


# STEP 1: make sure the virtual environment from Step 2 exists
if (-not (Test-Path $Python)) {
    throw "Python not found at $Python - create the virtual environment first (Step 2)."
}

# STEP 2: WHAT to run -> python.exe etl\daily_etl.py, inside the project folder
$action = New-ScheduledTaskAction `
    -Execute $Python `
    -Argument "etl\daily_etl.py" `
    -WorkingDirectory $ProjectDir

# STEP 3: WHEN to run -> every day at $At
$trigger = New-ScheduledTaskTrigger -Daily -At $At

# STEP 4: HOW to run
#   -StartWhenAvailable          : PC was off at 9:00? run as soon as it is on
#   -AllowStartIfOnBatteries     : laptops - Windows skips tasks on battery by default
#   -DontStopIfGoingOnBatteries  : don't stop the run if the charger is unplugged
#   -RestartCount / Interval     : if the run fails, try again 2 more times, 15 min apart
#   -ExecutionTimeLimit          : stop it if it somehow runs longer than 30 min
$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -RestartCount 2 `
    -RestartInterval (New-TimeSpan -Minutes 15) `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 30)

# STEP 5: create the task (-Force replaces it if it already exists)
Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Description "Loads latest mutual fund NAVs into MFPortfolioDB (project: $ProjectDir)" `
    -Force | Out-Null

Write-Host "Task '$TaskName' will run daily at $At."
Write-Host "Logs: $ProjectDir\logs\"
