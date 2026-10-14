# tokenscope monitor

`tokenscope_monitor.py` runs [tokenscope](https://github.com/rstagi/tokenscope) on a schedule on the machine that holds
your Claude Code transcripts (`~/.claude/projects`). It does not work in a cloud session, which has none of your history.

Each run it:

- writes a dated HTML report to `~/tokenscope-reports/YYYY-MM-DD.html` (last 7 days);
- appends a digest line to `~/tokenscope-reports/monitor.log`;
- alerts when spend in the last 5 h passes a threshold, at most once per window (`TOKENSCOPE_MON_USD`, default 10, or
  `TOKENSCOPE_MON_CW`, default 3,000,000 cost-weighted tokens);
- records each new `tokenscope fixes` finding in the log (seen ids are kept in `state.json`) and sends one summary
  notification per run, so the first run does not flood you.

Alerts go to the log and, when available, a desktop notification (`osascript` on macOS, `notify-send` on Linux).
A failed tokenscope call is logged and
never stops later runs.

## Install

First install tokenscope (`pipx install /path/to/tokenscope`) and do a test run, then check
`~/tokenscope-reports/monitor.log`:

```sh
python3 monitor/tokenscope_monitor.py
```

**macOS: launchd (recommended).** A launchd agent runs inside your login session, so desktop notifications show.
Cron jobs often run outside it, and their notifications can silently fail.

```sh
cp monitor/com.tokenscope.monitor.plist ~/Library/LaunchAgents/
# edit the two absolute paths (python3 and the script) and /Users/YOU in that copy
launchctl load ~/Library/LaunchAgents/com.tokenscope.monitor.plist
```

**Linux: cron.** Use an absolute path to `python3` (`which python3`) and to the script. Runs hourly:

```cron
0 * * * * TOKENSCOPE_MON_CW=2000000 /usr/bin/python3 /path/to/legendary-octo-potato/monitor/tokenscope_monitor.py
```

`notify-send` from cron may need `DISPLAY` or `DBUS_SESSION_BUS_ADDRESS` set; the log always works.

The script looks for `tokenscope` on PATH, then in `~/.local/bin`, `/opt/homebrew/bin` and `/usr/local/bin`, then
falls back to `python3 -m tokenscope`. Set `TOKENSCOPE_MON_BIN` to override.

## Tuning the thresholds

tokenscope 0.1.0 may not price your current models, in which case `usd=` stays `0.00` and the USD limit never fires.
Check a few `DIGEST window=...` lines in `monitor.log`, then set `TOKENSCOPE_MON_CW` from the `cw=` values you see on
normal days. The default of 3,000,000 is a guess.

## Uninstall

macOS: `launchctl unload ~/Library/LaunchAgents/com.tokenscope.monitor.plist` and delete that file.
Linux: remove the line with `crontab -e`.
Then delete `~/tokenscope-reports/` if you no longer want the history.

## Settings

See the header of `tokenscope_monitor.py` for all environment variables. `--root`, `--out-dir`, `--window`, `--since`,
`--now`, `--no-notify` and `--no-report` are also command-line flags.

For real-time watching instead, `tokenscope live` can run as a background service.
