#!/usr/bin/env python3
"""Run tokenscope on a schedule: write a report, log a digest, alert on spikes and new fixes.

Standard library only. Meant to run from cron or launchd on the machine that holds
your Claude Code transcripts (~/.claude/projects). See monitor/README.md.

Settings (environment variables, all optional):
  TOKENSCOPE_ROOT          transcripts root (default ~/.claude/projects)
  TOKENSCOPE_MON_DIR       output dir for reports, log and state (default ~/tokenscope-reports)
  TOKENSCOPE_MON_WINDOW    spend window for the alert check (default 5h)
  TOKENSCOPE_MON_USD       alert when window spend exceeds this many USD (default 10)
  TOKENSCOPE_MON_CW        alert when window cost-weighted tokens exceed this (default 3000000)
  TOKENSCOPE_MON_SINCE     lookback for the report and fixes (default 7d)
  TOKENSCOPE_MON_BIN       explicit path to the tokenscope executable
"""
import argparse
import datetime as dt
import json
import os
import platform
import shutil
import subprocess
import sys
import time

HOME = os.path.expanduser("~")
KNOWN_BINS = [
    os.path.join(HOME, ".local", "bin", "tokenscope"),
    "/opt/homebrew/bin/tokenscope",
    "/usr/local/bin/tokenscope",
]


def env_float(name, default):
    try:
        return float(os.environ.get(name, default))
    except ValueError:
        return float(default)


def window_seconds(spec):
    units = {"m": 60, "h": 3600, "d": 86400, "w": 604800}
    try:
        return int(spec[:-1]) * units[spec[-1]]
    except (ValueError, KeyError, IndexError):
        return 5 * 3600


def find_cmd():
    """cron has a minimal PATH, so look in the usual pipx/pip locations too."""
    explicit = os.environ.get("TOKENSCOPE_MON_BIN")
    if explicit:
        return [explicit]
    found = shutil.which("tokenscope")
    if found:
        return [found]
    for path in KNOWN_BINS:
        if os.access(path, os.X_OK):
            return [path]
    return [sys.executable, "-m", "tokenscope"]


class Monitor:
    def __init__(self, args):
        self.out_dir = os.path.expanduser(args.out_dir)
        os.makedirs(self.out_dir, exist_ok=True)
        self.log_path = os.path.join(self.out_dir, "monitor.log")
        self.state_path = os.path.join(self.out_dir, "state.json")
        self.root = os.path.expanduser(args.root)
        self.now = args.now
        self.window = args.window
        self.since = args.since
        self.max_usd = args.max_usd
        self.max_cw = args.max_cw
        self.cmd = find_cmd()
        self.notify_enabled = not args.no_notify
        self.alerts = []

    def log(self, msg):
        line = f"{dt.datetime.now().isoformat(timespec='seconds')} {msg}"
        with open(self.log_path, "a", encoding="utf-8") as fh:
            fh.write(line + "\n")
        print(line)

    def run(self, *argv, as_json=False):
        """Run tokenscope; return parsed JSON (or True) on success, None on any failure."""
        try:
            proc = subprocess.run(self.cmd + list(argv), capture_output=True, text=True, timeout=900)
        except (OSError, subprocess.TimeoutExpired) as exc:
            self.log(f"ERROR running tokenscope {argv[0]}: {exc}")
            return None
        if proc.returncode != 0:
            tail = ((proc.stderr or proc.stdout).strip().splitlines()[-1:] or ["no output"])[0]
            level = "INFO" if "no sessions found" in tail else "ERROR"  # normal after a quiet period
            self.log(f"{level} tokenscope {argv[0]} exited {proc.returncode}: {tail}")
            return None
        if not as_json:
            return True
        try:
            return json.loads(proc.stdout)
        except ValueError:
            self.log(f"ERROR tokenscope {argv[0]} printed invalid JSON")
            return None

    def load_state(self):
        try:
            with open(self.state_path, encoding="utf-8") as fh:
                return json.load(fh)
        except (OSError, ValueError):
            return {}

    def save_state(self, state):
        tmp = self.state_path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(state, fh, indent=1)
        os.replace(tmp, self.state_path)

    def notify(self, title, body, desktop=True):
        self.alerts.append(f"{title}: {body}")
        self.log(f"ALERT {title}: {body}")
        if not (desktop and self.notify_enabled):
            return
        try:
            if platform.system() == "Darwin":
                # ensure_ascii=False: AppleScript strings do not understand \uXXXX escapes
                script = "display notification {} with title {}".format(
                    json.dumps(body, ensure_ascii=False), json.dumps(title, ensure_ascii=False))
                subprocess.run(["osascript", "-e", script], timeout=10, check=False)
            elif shutil.which("notify-send"):
                subprocess.run(["notify-send", title, body], timeout=10, check=False)
        except (OSError, subprocess.TimeoutExpired):
            pass  # the log line above is the fallback

    def check_spend(self):
        top = self.run("top", "--window", self.window, "--json", "--index-root", self.root,
                       *(["--now", self.now] if self.now else []), as_json=True)
        if not top:
            return
        total = top.get("total", {})
        usd, cw = float(total.get("usd", 0)), float(total.get("cw", 0))
        biggest = (top.get("sessions") or [{}])[0].get("label", "n/a")
        self.log(f"DIGEST window={self.window} sessions={total.get('sessions', 0)} "
                 f"calls={total.get('calls', 0)} cw={cw:,.0f} usd={usd:.2f} top_session={biggest!r}")
        if usd > self.max_usd:
            msg = f"${usd:.2f} in last {self.window} (limit ${self.max_usd:g}). Top: {biggest}"
        elif cw > self.max_cw:
            msg = f"{cw:,.0f} CW in last {self.window} (limit {self.max_cw:,.0f}). Top: {biggest}"
        else:
            return
        # one alert per window, so an hourly schedule does not repeat a single spike
        state = self.load_state()
        if time.time() - state.get("last_spend_alert", 0) < window_seconds(self.window):
            self.log(f"INFO spend still over limit, alert already sent this window: {msg}")
            return
        self.notify("tokenscope: spend", msg)
        state["last_spend_alert"] = time.time()
        self.save_state(state)

    def check_fixes(self):
        fixes = self.run("fixes", "--since", self.since, "--root", self.root, "--json", as_json=True)
        if fixes is None:
            return
        state = self.load_state()
        seen = set(state.get("seen_fixes", []))
        new = [f for f in fixes if f.get("id") not in seen]
        self.log(f"DIGEST fixes total={len(fixes)} new={len(new)}")
        for fix in new:  # details go to the log; the desktop gets one summary per run
            self.notify(f"tokenscope fix [{fix.get('severity', '?')}]", fix.get("title", fix.get("id", "")), desktop=False)
        if new:
            first = new[0].get("title", new[0].get("id", ""))
            self.notify("tokenscope: new fixes", f"{len(new)} new, e.g. {first}. See monitor.log and the latest report.")
        state["seen_fixes"] = sorted(seen | {f["id"] for f in fixes if "id" in f})
        self.save_state(state)

    def write_report(self):
        stamp = dt.date.today().isoformat()
        path = os.path.join(self.out_dir, f"{stamp}.html")
        if self.run("report", "--since", self.since, "--root", self.root, "-o", path):
            self.log(f"REPORT {path}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", default=os.environ.get("TOKENSCOPE_ROOT", "~/.claude/projects"))
    ap.add_argument("--out-dir", default=os.environ.get("TOKENSCOPE_MON_DIR", "~/tokenscope-reports"))
    ap.add_argument("--window", default=os.environ.get("TOKENSCOPE_MON_WINDOW", "5h"))
    ap.add_argument("--since", default=os.environ.get("TOKENSCOPE_MON_SINCE", "7d"))
    ap.add_argument("--max-usd", type=float, default=env_float("TOKENSCOPE_MON_USD", 10))
    ap.add_argument("--max-cw", type=float, default=env_float("TOKENSCOPE_MON_CW", 3000000))
    ap.add_argument("--now", help="end of the spend window, ISO time (testing)")
    ap.add_argument("--no-notify", action="store_true", help="log alerts only, no desktop notification")
    ap.add_argument("--no-report", action="store_true", help="skip the HTML report")
    args = ap.parse_args()

    mon = Monitor(args)
    try:
        mon.check_spend()
        mon.check_fixes()
        if not args.no_report:
            mon.write_report()
    except Exception as exc:  # one bad run must not stop the schedule
        mon.log(f"ERROR unexpected: {exc!r}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
