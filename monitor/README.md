# tokenscope monitor

`tokenscope_monitor.py` runs [tokenscope](https://github.com/rstagi/tokenscope) on a schedule on the machine that holds
your Claude Code transcripts (`~/.claude/projects`). It does not work in a cloud session, which has none of your history.

Each run it:

- writes a dated HTML report to `~/tokenscope-reports/YYYY-MM-DD.html` (last 7 days);
- appends a digest line to `~/tokenscope-reports/monitor.log`;
- alerts when spend in the last 5 h passes a threshold (`TOKENSCOPE_MON_USD`, default 10, or
  `TOKENSCOPE_MON_CW`, default 3,000,000 cost-weighted tokens);
- alerts once per new `tokenscope fixes` finding (seen ids are kept in `state.json`).

Alerts go to the log and, when available, a desktop notification (`osascript` on macOS, `notify-send` on Linux).
The spend alert repeats on every run while the window stays over the limit. A failed tokenscope call is logged and
never stops later runs.

## Install

```sh
pipx install /path/to/tokenscope          # provides the tokenscope command
python3 monitor/tokenscope_monitor.py     # test run, then check ~/tokenscope-reports/monitor.log
crontab -e
```

Add this line to run every hour (adjust the path, and add any `TOKENSCOPE_MON_*` settings before the command):

```cron
0 * * * * TOKENSCOPE_MON_USD=15 python3 /path/to/legendary-octo-potato/monitor/tokenscope_monitor.py
```

cron has a minimal PATH. The script looks for `tokenscope` on PATH, then in `~/.local/bin`, `/opt/homebrew/bin` and
`/usr/local/bin`, then falls back to `python3 -m tokenscope`. Set `TOKENSCOPE_MON_BIN` to override.

On Linux, `notify-send` from cron may need `DISPLAY` or `DBUS_SESSION_BUS_ADDRESS` set; the log always works.

## Uninstall

Remove the cron line with `crontab -e`, then delete `~/tokenscope-reports/` if you no longer want the history.

## Settings

See the header of `tokenscope_monitor.py` for all environment variables. `--root`, `--out-dir`, `--window`, `--since`,
`--now`, `--no-notify` and `--no-report` are also command-line flags.

For real-time watching instead, `tokenscope live` can run as a background service.
