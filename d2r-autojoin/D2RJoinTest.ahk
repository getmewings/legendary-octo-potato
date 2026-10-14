#Requires AutoHotkey v2.0
#SingleInstance Force
; Fake Diablo2RLoader windows for testing D2RJoin without the game.
; Set DryRun=1 in D2RJoin.ini, reload D2RJoin, then run this script.
; Optional argument: number of windows (default 4). Window 1 is the leader.
; Each window logs what it received when Enter or Join is pressed.
; Closing any window exits the test.

count := A_Args.Length ? Integer(A_Args[1]) : 4
Loop count
    MakeWindow(A_Index)

MakeWindow(id) {
    g := Gui(, id " - Test" (id = 1 ? " leader" : "") " (dry-run) - Diablo II: Resurrected")
    g.AddText(, "Game name")
    nameBox := g.AddEdit("w200")
    g.AddText(, "Password")
    passBox := g.AddEdit("w200")
    log := g.AddEdit("w300 r6 ReadOnly")
    g.AddButton("Default w80", "Join").OnEvent("Click", (*) => Submit(nameBox, passBox, log))
    g.OnEvent("Close", (*) => ExitApp())
    g.Show(Format("x{} y{}", 20 + Mod(id - 1, 4) * 340, 20 + (id - 1) // 4 * 320))
    nameBox.Focus()
}

; Like the game, the fields keep their text; D2RJoin must clear them.
Submit(nameBox, passBox, log) {
    log.Value := FormatTime(, "HH:mm:ss") "  name='" nameBox.Value "'  pw='" passBox.Value "'`r`n" log.Value
    nameBox.Focus()
}
