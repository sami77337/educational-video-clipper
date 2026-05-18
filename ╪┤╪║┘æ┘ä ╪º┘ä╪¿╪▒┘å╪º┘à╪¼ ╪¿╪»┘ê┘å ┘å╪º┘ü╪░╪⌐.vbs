Option Explicit
Dim shell, fso, appDir, batPath
Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
appDir = fso.GetParentFolderName(WScript.ScriptFullName)
batPath = fso.BuildPath(appDir, "run_app.bat")
If Not fso.FileExists(batPath) Then
    MsgBox "run_app.bat was not found next to this launcher.", 16, "Almiqs AlBaseet"
    WScript.Quit 1
End If
shell.CurrentDirectory = appDir
shell.Run "cmd.exe /c """ & batPath & """", 0, False
