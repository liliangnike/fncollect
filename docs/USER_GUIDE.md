# fncollect User Guide

Welcome! fncollect is a tool that talks to Fixed Network devices (OLT/ONT)
and collects logs/status/data for you — **no programming needed**. This guide
shows you the easy ways to use it.

> If you just want to start: **`fncollect interact`** guides you step by step.

---

## 1. Install (once)

See the **README** for full install steps. In short:
```bash
pip install -e '.[net]'      # .net enables the device SSH libraries
```
If your devices are older Nokia ISAMs, parametize **paramiko 2.x** (legacy
SSH). The README covers this.

---

## 2. The three easy ways to collect

### A. Interactive menu — easiest
```bash
fncollect interact
```
It asks you:
1. which vendor (e.g. `isam`, `mock`),
2. which action (e.g. `inventory`),
3. which device(s).

That's it.

### B. One command, built-in action
```bash
fncollect collect --vendor isam --action inventory --devices 10.0.0.1
```
- `--action` choices: `inventory`, `ont_inventory`, `run_commands`
- a comma-separated list of device IPs runs them **in parallel**

### C. A pre-built procedure by name
```bash
fncollect procedures --vendor isam             # list what's built in
fncollect run --vendor isam --procedure probe --device 10.0.0.1
```
Built-in procedures (`probe`, ones in the vendor's `dcps/` folder) run as-is —
no setup on your side.

---

## 3. Where does the output go?

Every run makes a timestamped folder under `fncollect_out/`:

```
fncollect_out/run-20260827T.../
  manifest.json                # index of everything (machine-readable)
  app.log                      # what the tool did
  inventory/  or  ont/  ...    # the raw collected output
  reports/summary.md           # human summary  (open this!)
  reports/results.json
  reports/results.csv
```

Open **`reports/summary.md`** to see a clean summary of what was collected.

---

## 4. Login credentials

Provide them per-command:
```bash
fncollect collect --vendor isam --action inventory --devices 10.0.0.1 \
    --user <username> --password '<password>'
```
or set them once in your environment (so they're not in your command history):
```bash
export FNCOLLECT_USER=<username>
export FNCOLLECT_PASSWORD='...'
```
Credentials are **never written to logs**.

---

## 5. Progress bars

You'll see Linux-install-style progress bars as it runs. If you're piping
output to a file and want clean text, add `--no-progress`.

---

## 6. Discovering new commands / data — no regex needed

`fncollect wizard` builds a collection step from a live example — you never
write a regular expression:
```bash
fncollect wizard --vendor isam
```
1. it connects and asks you to run a command,
2. shows the device output with line numbers,
3. you type the line + the exact value (e.g. `6.6.02` from `R6.6.02g`),
4. fncollect **auto-generates the pattern**, verifies it, and names the variable,
5. it writes a ready-to-run procedure file for you.

---

## 7. Troubleshooting quick tips

| Problem | Fix |
|---|---|
| "no acceptable host key" / won't connect to old OLT | install the `net` extra with **paramiko 2.x** (legacy SSH) |
| Connection/auth error | check IP, user, password (env or flags) |
| Want only text output | add `--no-progress` |
| I need a custom collection | use `fncollect wizard` (no coding) |

---

## Next steps
- Want to customize or add your own procedures/vendors? That's for *power
  users* — see **`docs/EXTENDING.md`**.
- Full command reference lives in the README.
