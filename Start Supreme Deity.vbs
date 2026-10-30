Option Explicit
Dim shell, fso, base, python, command, config, stream
Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
base = fso.GetParentFolderName(WScript.ScriptFullName)
shell.CurrentDirectory = base
python = "pythonw.exe"
If fso.FileExists(base & "\.venv\Scripts\pythonw.exe") Then python = base & "\.venv\Scripts\pythonw.exe"
config = base & "\supreme-deity-python.txt"
If fso.FileExists(config) Then
    Set stream = fso.OpenTextFile(config, 1)
    ' VBScript Trim removes spaces, but leaves CR/LF in a text file.
    python = Trim(Replace(Replace(stream.ReadAll, vbCr, ""), vbLf, ""))
    stream.Close
    If Not fso.FileExists(python) Then
        MsgBox "Configured Python was not found: " & python & vbCrLf & "Update " & config, 16, "Supreme Deity"
        WScript.Quit 1
    End If
    python = fso.BuildPath(fso.GetParentFolderName(python), "pythonw.exe")
End If
command = Chr(34) & python & Chr(34) & " " & Chr(34) & base & "\scripts\SupremeDeityGUI.pyw" & Chr(34)
On Error Resume Next
shell.Run command, 1, False
If Err.Number <> 0 Then MsgBox "Could not open the launcher. Python must be installed and on PATH." & vbCrLf & Err.Description, 16, "Supreme Deity"
