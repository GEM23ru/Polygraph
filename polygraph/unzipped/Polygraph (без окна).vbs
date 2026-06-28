' Polygraph - zapusk BEZ chyornogo okna.
' Server zapuskaetsya skryto, brauzer otkroetsya sam.
' Chtoby ostanovit - zavershi "python.exe" / "pythonw.exe" v Dispetchere zadach.

Set sh = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
curDir = fso.GetParentFolderName(WScript.ScriptFullName)

cmd = "cmd /c cd /d """ & curDir & """ && (pythonw web.py 2>nul || python web.py)"
sh.Run cmd, 0, False
