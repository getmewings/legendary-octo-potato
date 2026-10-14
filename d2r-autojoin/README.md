# D2RJoin

Join helper for Diablo II: Resurrected windows launched with
[Diablo2RLoader](https://github.com/shupershuff/Diablo2RLoader). It types the
game name and password into each follower window's Join Game tab and presses
Enter.

> **Risk:** Blizzard's EULA prohibits unauthorized automation. Joining one
> window per keypress (Ctrl+Alt+J) is the lower-risk mode. Join all
> (Ctrl+Alt+A) joins every window from one press and can put every account
> involved at risk of a ban. It is off by default. Use it at your own risk.

## Requirements

- Windows 10 or 11
- [AutoHotkey v2](https://www.autohotkey.com/) (v1 will not run this script)
- Diablo2RLoader, used to launch every account. D2RJoin finds windows by the
  titles the loader gives them, such as
  `2 - Alt (us.actual.battle.net) - Diablo II: Resurrected`.

## Setup

1. Install AutoHotkey v2 from https://www.autohotkey.com/.
2. Put `D2RJoin.ahk` in its own folder, for example `C:\D2RJoin\`.
3. Double-click `D2RJoin.ahk`. A green "H" icon appears in the system tray,
   and the script creates `D2RJoin.ini` in the same folder.
4. Open `D2RJoin.ini` in Notepad and set these values:

   | Setting | Meaning |
   |---|---|
   | `Prefix` | Start of every game name, e.g. `baal-`. The prefix plus 3 digits must be 15 characters or fewer. |
   | `Password` | Game password. Leave it blank for no password. |
   | `Counter` | Game number. Leave it at `0` on first run. |
   | `LeaderID` | Account ID (from Accounts.csv) that creates games. D2RJoin never types into it. `0` means no leader. |
   | `SkipIDs` | Accounts you always join by hand, comma-separated, e.g. `3,5`. Blank means none. |
   | `AutoEnter` | `1` presses Enter after the password. `0` leaves it to you. |
   | `FieldNav` | `tab` or `click`. See step 6. |
   | `NameField`, `PassField` | Field positions for click mode. Set them in step 6. |
   | `KeyDelayMs` | Typing speed. Raise it if letters go missing. |
   | `JoinAllEnabled` | `1` turns on Ctrl+Alt+A. Default `0` (off). |
   | `JoinAllGapMs` | Pause between windows during join all, in ms. Default `2500`. |

5. Save the file, then press **Ctrl+Alt+R** to reload the script.
6. Choose how the script moves between the two fields:
   - **Tab mode (try first).** Launch one follower, open **Lobby > Join Game**
     and click in the game-name field. Press Ctrl+Alt+N, then Ctrl+Alt+J.
     If the name lands in the name field and the password in the password
     field, keep `FieldNav=tab`.
   - **Click mode (if tab fails).** Set `FieldNav=click`. In any follower,
     open the Join Game tab:
     1. Hover the mouse over the game-name field and press **Ctrl+Alt+K**.
        Paste the copied value after `NameField=`.
     2. Hover over the password field and press **Ctrl+Alt+K**. Paste the
        value after `PassField=`.
     3. Save and press **Ctrl+Alt+R**.

     One calibration covers every window, as long as all windows are the same
     size. Different window shapes can move the fields.
7. Optional: to use join all, set `JoinAllEnabled=1` (read the risk note
   above first), save, and press **Ctrl+Alt+R**.

## Each game

1. Press **Ctrl+Alt+N**. The game number goes up by one and the game name is
   copied to the clipboard.
2. In the leader window, create the game: paste the name, type the password
   and click Create.
3. Join the followers:
   - **One at a time:** press **Ctrl+Alt+J** once per follower window.
   - **All at once:** press **Ctrl+Alt+A**. Don't touch the keyboard or mouse
     until the tooltip says it's done.
4. After the run, leave every follower on the Join Game tab, ready for the
   next game.

## Hotkeys

| Keys | Action |
|---|---|
| Ctrl+Alt+N | New game: counter +1, game name copied to clipboard |
| Ctrl+Alt+J | Join the next follower window (lowest account ID first) |
| Ctrl+Alt+A | Join all remaining followers (needs `JoinAllEnabled=1`) |
| Ctrl+Alt+B | Step back: the last joined window becomes next again |
| Ctrl+Alt+M | Mark the active window as joined (you joined it by hand) |
| Ctrl+Alt+K | Copy the mouse position for click mode |
| Ctrl+Alt+R | Reload after editing `D2RJoin.ini` |

## Troubleshooting

| Problem | Fix |
|---|---|
| Letters missing from the game name | Raise `KeyDelayMs`, e.g. to `30`. |
| Join all misses windows or the PC stutters | Raise `JoinAllGapMs`, e.g. to `4000`. |
| Text lands in the wrong field | Switch to click mode, or recalibrate. |
| "Couldn't focus account N" | Restore the window if it's minimized. Keep windows open, not minimized. |
| A window you joined by hand gets typed into | Press Ctrl+Alt+M in that window, or add its ID to `SkipIDs`. |
| Hotkeys do nothing | Check the tray icon is running. Another program may be using the same keys. |
| No windows found | Launch the accounts with Diablo2RLoader so the windows get its titles. |
| Changed `JoinAllGapMs` in the script but nothing changed | The ini file wins. Edit `D2RJoin.ini`, then Ctrl+Alt+R. |
