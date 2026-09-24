' Run PKDK hourly with NO console flash (Task Scheduler).
' ASCII-only. Called by: wscript.exe //B //Nologo run_hourly_hidden.vbs
Option Explicit
Dim sh, fso, here, repo, ps1, cmd
Set fso = CreateObject("Scripting.FileSystemObject")
Set sh = CreateObject("WScript.Shell")
here = fso.GetParentFolderName(WScript.ScriptFullName)
repo = fso.GetParentFolderName(here)
ps1 = here & "\run_hourly.ps1"
If Not fso.FileExists(ps1) Then
  WScript.Quit 2
End If
' 0 = hidden window, False = do not wait (task can track process via powershell child)
cmd = "powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File """ & ps1 & """"
sh.CurrentDirectory = repo
sh.Run cmd, 0, True
WScript.Quit 0
