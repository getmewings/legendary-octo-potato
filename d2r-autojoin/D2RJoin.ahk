#Requires AutoHotkey v2.0
#SingleInstance Force
; D2RJoin - hand-paced join helper for Diablo2RLoader windows.
;
; One press of Ctrl+Alt+J joins ONE follower window: focus it, type the game
; name and password, press Enter. The next window waits for your next press.
;
; Ctrl+Alt+A (join all) is off by default. It joins every follower from one
; press, which Blizzard's EULA treats as automation: enabling it risks the
; accounts involved. It reads no game memory, injects nothing, never repeats
; on its own, and stops at the first window that fails a check.
;
; Setup
;   1. Launch accounts with Diablo2RLoader (window titles look like
;      "2 - Alt (us.actual.battle.net) - Diablo II: Resurrected").
;   2. Run this script once to create D2RJoin.ini next to it, then edit:
;        [Game]    Prefix, Password (prefix + 3 digits must be 15 chars or less)
;        [Windows] LeaderID = account ID that creates games (0 = none)
;                  SkipIDs  = accounts you always join by hand, eg "3,5"
;        [Join]    FieldNav = tab   -> name field must have the cursor
;                  JoinAllEnabled = 1 turns on Ctrl+Alt+A
;                  JoinAllGapMs   = pause between windows for join all
;                  FieldNav = click -> clicks NameField / PassField (calibrate)
;   3. Leave each follower window on the Join Game tab.
;
; Hotkeys
;   Ctrl+Alt+N  next game: counter +1, game name copied for the leader window
;   Ctrl+Alt+J  join the next follower window (lowest account ID first)
;   Ctrl+Alt+A  join all remaining follower windows (needs JoinAllEnabled=1)
;   Ctrl+Alt+B  step back: the last joined window becomes next again
;   Ctrl+Alt+M  mark the active window as joined (you joined it by hand)
;   Ctrl+Alt+K  calibrate: copy mouse position (as window ratio) for click mode
;   Ctrl+Alt+R  reload script after editing D2RJoin.ini

SetTitleMatchMode "RegEx"
SendMode "Event"  ; games often drop SendInput; Event mode with a fixed key delay is reliable

IniFile := A_ScriptDir "\D2RJoin.ini"
EnsureIni()

GamePrefix   := IniRead(IniFile, "Game", "Prefix")
GamePassword := IniRead(IniFile, "Game", "Password")
Counter      := Integer(IniRead(IniFile, "Game", "Counter"))
LeaderID     := Integer(IniRead(IniFile, "Windows", "LeaderID"))
SkipIDs      := []
for id in StrSplit(IniRead(IniFile, "Windows", "SkipIDs"), ",", " ")
    if id != ""
        SkipIDs.Push(Integer(id))
AutoEnter    := IniRead(IniFile, "Join", "AutoEnter") = "1"
FieldNav     := IniRead(IniFile, "Join", "FieldNav")
NameField    := IniRead(IniFile, "Join", "NameField")
PassField    := IniRead(IniFile, "Join", "PassField")
JoinAllEnabled := IniRead(IniFile, "Join", "JoinAllEnabled") = "1"
JoinAllGapMs := Integer(IniRead(IniFile, "Join", "JoinAllGapMs"))
KeyDelay     := Integer(IniRead(IniFile, "Join", "KeyDelayMs"))
SetKeyDelay KeyDelay, KeyDelay

TitleRegex   := "^\d+ - .* - Diablo II: Resurrected$"
WinMatch     := TitleRegex " ahk_exe i)^d2r\.exe$"
MaxFieldLen  := 16  ; D2R name/password fields hold 15 chars; one extra backspace to be safe

Joined := []    ; account IDs joined to the current game, in order
Busy   := false

TrayTip "Ctrl+Alt+N new game, Ctrl+Alt+J join next window", "D2RJoin ready"

^!n::NewGame()
^!j::JoinNext()
^!a::JoinAll()
^!b::StepBack()
^!m::MarkJoined()
^!k::Calibrate()
^!r::Reload()

NewGame() {
    global Counter, Joined
    Counter += 1
    IniWrite(Counter, IniFile, "Game", "Counter")
    Joined := []
    A_Clipboard := GameName()
    Tip("Game " GameName() " copied to clipboard. Create it in the leader window.")
}

JoinNext() {
    global Busy
    if Busy
        return
    Busy := true
    try {
        if !ReadyToJoin()
            return
        target := NextFollower()
        if !target {
            Tip("All windows joined " GameName() ". Ctrl+Alt+N starts the next game.")
            return
        }
        if JoinOne(target)
            Tip("Account " target.id " -> " GameName())
    } finally {
        Busy := false
    }
}

; Opt-in (JoinAllEnabled=1). Joins every remaining follower in ID order and
; stops at the first window that fails a check, so it never types blind.
JoinAll() {
    global Busy
    if Busy
        return
    if !JoinAllEnabled {
        Tip("Join all is off. Set JoinAllEnabled=1 in D2RJoin.ini, then Ctrl+Alt+R.")
        return
    }
    Busy := true
    try {
        if !ReadyToJoin()
            return
        startWin := WinExist("A")
        count := 0
        while target := NextFollower() {
            if count > 0
                Sleep JoinAllGapMs  ; let the previous window take the Enter before focus moves
            if !JoinOne(target)
                return  ; JoinOne already showed why
            count += 1
        }
        if startWin && WinExist(startWin)
            WinActivate(startWin)
        Tip(count ? count " window(s) joined " GameName() "." : "All windows already joined " GameName() ".")
    } finally {
        Busy := false
    }
}

ReadyToJoin() {
    if Counter = 0 {
        Tip("Press Ctrl+Alt+N first to pick a game name.")
        return false
    }
    WaitForModifiers()
    return true
}

NextFollower() {
    for w in GetFollowers()
        if !HasValue(Joined, w.id)
            return w
    return ""
}

; Focus one window, check it, type name and password, press Enter.
JoinOne(target) {
    WinActivate(target.hwnd)
    if !WinWaitActive(target.hwnd, , 1) {
        Tip("Couldn't focus account " target.id ". Nothing typed.")
        return false
    }
    if !RegExMatch(WinGetTitle(target.hwnd), TitleRegex) {
        Tip("Account " target.id " window title changed. Nothing typed.")
        return false
    }
    FillField(target.hwnd, NameField, GameName(), true)
    FillField(target.hwnd, PassField, GamePassword, false)
    if AutoEnter
        Send "{Enter}"
    Joined.Push(target.id)
    return true
}

StepBack() {
    if Joined.Length = 0 {
        Tip("Nothing to step back.")
        return
    }
    Tip("Account " Joined.Pop() " is next again.")
}

; For a window you joined by hand, so Ctrl+Alt+J doesn't type into it in-game.
MarkJoined() {
    if !RegExMatch(WinGetTitle("A"), TitleRegex) || !RegExMatch(WinGetTitle("A"), "^(\d+) ", &m) {
        Tip("Active window isn't a loader D2R window.")
        return
    }
    id := Integer(m[1])
    if !HasValue(Joined, id)
        Joined.Push(id)
    Tip("Account " id " marked as joined.")
}

; Hover the mouse over a field in the active D2R window, then press Ctrl+Alt+K.
Calibrate() {
    CoordMode "Mouse", "Client"
    MouseGetPos(&x, &y)
    WinGetClientPos(, , &w, &h, "A")
    spec := Format("{:.3f},{:.3f}", x / w, y / h)
    A_Clipboard := spec
    Tip("Position " spec " copied. Paste it as NameField or PassField in D2RJoin.ini, then Ctrl+Alt+R.")
}

; Puts the cursor in a field, clears leftover text, types the new value.
FillField(hwnd, spec, text, isFirst) {
    if FieldNav = "click"
        ClickClient(hwnd, spec)
    else if !isFirst
        Send "{Tab}"
    Send "{End}{BackSpace " MaxFieldLen "}"
    if text != ""
        SendText text
}

; spec is "x,y" as fractions of the client area, so it survives window resizes.
ClickClient(hwnd, spec) {
    parts := StrSplit(spec, ",", " ")
    WinGetClientPos(, , &w, &h, hwnd)
    CoordMode "Mouse", "Client"
    Click(Round(parts[1] * w), Round(parts[2] * h))
}

; Loader windows except the leader, sorted by account ID.
GetFollowers() {
    found := []
    for hwnd in WinGetList(WinMatch) {
        if !RegExMatch(WinGetTitle(hwnd), "^(\d+) ", &m)
            continue
        id := Integer(m[1])
        if id = LeaderID || HasValue(SkipIDs, id)
            continue
        i := 1
        while i <= found.Length && found[i].id < id
            i++
        found.InsertAt(i, {id: id, hwnd: hwnd})
    }
    return found
}

GameName() => Format("{}{:03}", GamePrefix, Counter)

HasValue(arr, val) {
    for v in arr
        if v = val
            return true
    return false
}

; Held Ctrl/Alt from the hotkey would turn typed letters into shortcuts.
WaitForModifiers() {
    for key in ["Ctrl", "Alt", "Shift", "LWin"]
        KeyWait(key, "T1")
}

; Clears the tooltip only; no timer here touches the game.
Tip(msg) {
    ToolTip msg
    SetTimer () => ToolTip(), -4000
}

EnsureIni() {
    defaults := [
        ["Game", "Prefix", "baal-"],
        ["Game", "Password", ""],
        ["Game", "Counter", "0"],
        ["Windows", "LeaderID", "1"],
        ["Windows", "SkipIDs", ""],
        ["Join", "AutoEnter", "1"],
        ["Join", "FieldNav", "tab"],
        ["Join", "NameField", "0.800,0.300"],
        ["Join", "PassField", "0.800,0.360"],
        ["Join", "KeyDelayMs", "15"],
        ["Join", "JoinAllEnabled", "0"],
        ["Join", "JoinAllGapMs", "400"],
    ]
    for d in defaults
        if IniRead(IniFile, d[1], d[2], "<missing>") = "<missing>"
            IniWrite(d[3], IniFile, d[1], d[2])
}
