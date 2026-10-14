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
2. Put `D2RJoin.ahk` and `D2RJoinTest.ahk` in their own folder, for example `C:\D2RJoin\`.
3. Double-click `D2RJoin.ahk`. A green "H" icon appears in the system tray,
   and the script creates `D2RJoin.ini` in the same folder.
4. Open `D2RJoin.ini` in Notepad and set these values:

   | Setting | Meaning |
   |---|---|
   | `Prefix` | Start of every game name, e.g. `baal-`. The prefix plus 3 digits must be 15 characters or fewer. |
   | `Password` | Game password. Leave it blank for no password. |
   | `Counter` | Game number. Leave it at `0` on first run. |
   | `LeaderID` | Account ID (from Accounts.csv) that creates games. Join keys never type into it; only Ctrl+Alt+C does. `0` means no leader. |
   | `SkipIDs` | Accounts you always join by hand, comma-separated, e.g. `3,5`. Blank means none. |
   | `AutoEnter` | `1` presses Enter after the password. `0` leaves it to you. |
   | `FieldNav` | `tab` or `click`. See step 6. |
   | `NameField`, `PassField` | Join Game field positions for click mode. Set them in step 7. |
   | `CreateNameField`, `CreatePassField` | Leader's Create Game field positions for click mode. Set them in step 7. |
   | `KeyDelayMs` | Typing speed. Raise it if letters go missing. |
   | `JoinAllEnabled` | `1` turns on Ctrl+Alt+A. Default `0` (off). |
   | `JoinAllGapMs` | Pause between windows during join all, in ms. Default `2500`. |
   | `AbortOnInput` | `1` stops a run when you touch the mouse or keyboard. Default `1`. |
   | `DryRun` | `1` targets test windows instead of the game. See step 6. |

5. Save the file, then press **Ctrl+Alt+R** to reload the script.
6. Test without the game (recommended):
   1. Set `DryRun=1` and press **Ctrl+Alt+R**. The tray tip says "DRY RUN".
   2. Double-click `D2RJoinTest.ahk`. Four test windows open; window 1 is the
      leader. Each has name and password fields and a log.
   3. Run the steps in **Each game** below. Each Enter adds a log line showing
      the name and password that window received.
   4. Try Esc or moving the mouse during Ctrl+Alt+A. The run should stop.
   5. Close a test window to end the test. Set `DryRun=0` and press
      **Ctrl+Alt+R** before playing.
7. In the game, choose how the script moves between the two fields:
   - **Tab mode (try first).** Open **Lobby > Join Game** in one follower and
     click in the game-name field. Press Ctrl+Alt+N, then Ctrl+Alt+J. If the
     name lands in the name field and the password in the password field,
     keep `FieldNav=tab`. Try Ctrl+Alt+C on the leader's Create Game tab too.
   - **Click mode (if tab fails).** Set `FieldNav=click`. In any follower,
     open the Join Game tab:
     1. Hover the mouse over the game-name field and press **Ctrl+Alt+K**.
        Paste the copied value after `NameField=`.
     2. Hover over the password field and press **Ctrl+Alt+K**. Paste the
        value after `PassField=`.
     3. In the leader, open the Create Game tab and do the same for
        `CreateNameField` and `CreatePassField`.
     4. Save and press **Ctrl+Alt+R**.

     One calibration covers every window, as long as all windows are the same
     size. Different window shapes can move the fields.
8. Check that Enter creates the game on the Create Game tab. If it doesn't,
   set `AutoEnter=0` and click Create and Join yourself.
9. Optional: to use join all, set `JoinAllEnabled=1` (read the risk note
   above first), save, and press **Ctrl+Alt+R**.

## Each game

1. Create the game. Either:
   - press **Ctrl+Alt+C**: the game number goes up by one and the leader
     window gets the name and password typed in, or
   - press **Ctrl+Alt+N** to get the next name on the clipboard, then paste it
     in the leader window and create the game by hand.
2. Join the followers:
   - **One at a time:** press **Ctrl+Alt+J** once per follower window.
   - **All at once:** press **Ctrl+Alt+A**. Don't touch the keyboard or mouse
     until the tooltip says it's done.
   - **Stop a run:** press **Esc**, or move the mouse if `AbortOnInput=1`.
     Windows already joined stay joined; the next join press resumes from
     the window that stopped.
3. After the run, leave every follower on the Join Game tab, ready for the
   next game.

## Hotkeys

| Keys | Action |
|---|---|
| Ctrl+Alt+N | New game: counter +1, game name copied to clipboard |
| Ctrl+Alt+C | New game, created in the leader window |
| Ctrl+Alt+J | Join the next follower window (lowest account ID first) |
| Ctrl+Alt+A | Join all remaining followers (needs `JoinAllEnabled=1`) |
| Ctrl+Alt+B | Step back: the last joined window becomes next again |
| Ctrl+Alt+M | Mark the active window as joined (you joined it by hand) |
| Ctrl+Alt+K | Copy the mouse position for click mode |
| Ctrl+Alt+R | Reload after editing `D2RJoin.ini` |
| Esc | Stop a running join (only active while one runs) |

## Troubleshooting

| Problem | Fix |
|---|---|
| Letters missing from the game name | Raise `KeyDelayMs`, e.g. to `30`. |
| Join all misses windows or the PC stutters | Raise `JoinAllGapMs`, e.g. to `4000`. |
| Text lands in the wrong field | Switch to click mode, or recalibrate. |
| "Couldn't focus account N" | Restore the window if it's minimized. Keep windows open, not minimized. |
| "Stopped: you used the mouse or keyboard" when you didn't | A bumped mouse counts. Keep hands off during a run, or set `AbortOnInput=0` (Esc and the focus check still work). |
| "Stopped: focus left account N" | Another app took focus, e.g. a popup. Press the join key again. |
| Ctrl+Alt+C says leader not found | Set `LeaderID` to the leader's account ID, then Ctrl+Alt+R. |
| A window you joined by hand gets typed into | Press Ctrl+Alt+M in that window, or add its ID to `SkipIDs`. |
| Hotkeys do nothing | Check the tray icon is running. Another program may be using the same keys. |
| No windows found | Launch the accounts with Diablo2RLoader so the windows get its titles. Check `DryRun=0`. |
| Changed `JoinAllGapMs` in the script but nothing changed | The ini file wins. Edit `D2RJoin.ini`, then Ctrl+Alt+R. |
