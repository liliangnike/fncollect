# fncollect

A clean-room, multi-vendor **Fixed Network (FN) OLT/ONT log collector** and
troubleshooting assistant. Written from scratch in Python (no proprietary
source), designed to be extended to any FN vendor's product line.

## What it does

fncollect connects to Fixed Network devices (OLT/ONT), runs declarative
**Data Collection Procedures (DCPs)** and **semantic actions** (inventory,
on-demand commands), organises the captured output into a timestamped run
directory with a machine-readable `manifest.json` plus human/CSV reports.

## Design goals

- **Clean architecture** — abstract `Vendor` / `Session` / `Device` / `Action` contracts.
- **Declarative DCPs** — collection procedures as YAML with variables, no code
  changes to add a new collection.
- **Configurable sessions** — per-session-type ports & prompts defined in YAML,
  not hardcoded.
- **Portable output** — every run has raw artifacts + `manifest.json` + reports
  for downstream tooling and AI.
- **Safe by default** — credentials redacted from logs; never logged.
- **Extensible** — add a new vendor (and its hardware/ONT chipsets) as a pack.

## Package layout

```
config/                 # committed defaults: fncollect.yml, vendor packs, DCPs
src/fncollect/
  cli.py                # entry point (run / collect / interact / init / ...)
  config.py             # Pydantic config loading + validation
  logging_setup.py      # console + rolling file, secret redaction
  session_ctx.py        # per-run dir + manifest
  variables.py          # typed variable context, safe expressions, templating
  sessions.py           # Endpoint + Session abstraction (port & prompt per type)
  vendor.py             # abstract Vendor/Device/Action contracts
  ont.py                # ONT devices specialised by SoC chipset
  cutthrough.py         # ONT cutthrough (OLT-gated access) workflow
  dcp.py                # DCP engine + meta-ops (loop / wait / condition)
  actions.py            # action registry + inventory / run_commands
  engine.py             # concurrent multi-device runner
  report.py             # summary.md / results.json / results.csv
  discovery.py          # hardware-type auto-discovery (importlib)
  menu.py               # interactive launch mode
  vendors/              # pluggable vendor packs
    mock/               # deterministic in-memory vendor (tests/demo)
    nokia_fx/           # exemplar CLI-dialect pack
    isam/               # Nokia ISAM (7360/7362) real interactive SSH
  net.py                # real interactive SSH session (prompt, paging, legacy)
tests/                  # pytest suite
```

## Quick start

```bash
python -m pip install -e '.[dev]'
python -m fncollect vendors          # list vendor packs
python -m fncollect actions          # list available actions
python -m fncollect run              # run with default mock vendor (no DCP)
python -m fncollect run --vendor mock --dcp config/dcps/basic_collect.yml
python -m fncollect collect --vendor mock --action inventory --devices 10.0.0.1
python -m fncollect interact         # guided interactive menu
python -m fncollect init             # scaffold user/ config tree
python -m pytest                     # run the test suite
```

## Linux installation

Tested on Ubuntu 22.04 LTS (Python 3.10) and other Linux distros with
Python >= 3.10. Requires `git`, `python3`, `python3-pip` and a virtual
environment.

```bash
# 1. Clone the repository
git clone https://github.com/liliangnike/fncollect.git
cd fncollect

# 2. (Recommended) create and activate a virtual environment
python3 -m venv .venv
source .venv/bin/activate

# 3. Upgrade tooling and install the package
python -m pip install --upgrade pip
python -m pip install -e '.[dev]'

# 4. Verify it works
python -m fncollect --version
python -m fncollect vendors
```

### From source (no venv)

For quick testing without a venv:

```bash
python3 -m pip install --user -e .
python3 -m fncollect --version
```

## Build a standalone binary with PyInstaller (Linux)

Build a single distributable `fncollect` binary so the tool runs on target
Linux machines **without Python installed**.

```bash
# 1. Install the build dependency
python -m pip install pyinstaller

# 2. Install fncollect (so its submodules are importable)
python -m pip install -e .

# 3. Build
pyinstaller fncollect.spec

# 4. The binary and its data are produced under dist/fncollect/
ls dist/fncollect/fncollect

# 5. Run on this or any compatible Linux host
./dist/fncollect/fncollect --version
./dist/fncollect/fncollect run --vendor mock --dcp config/dcps/basic_collect.yml
```

Notes:
- The spec file (`fncollect.spec`) bundles the `config/` tree and vendor
  modules so packaged runs find them at runtime.
- The CI workflow also builds the binary on every push and uploads it as an
  artifact (`Actions` → latest run → `fncollect-binary`).

## DCP with variables

A DCP can declare typed parameters, extract variables from command output,
derive new variables with safe expressions, and substitute them into
commands and save paths via `{{ name }}`:

```yaml
name: collect_with_vars
vendor: mock
parameters:                 # declared + validated inputs
  - {name: ont_id, type: string, default: "2"}
derivations:                # computed from other variables (safe expressions)
  - {name: ont_dir, from: [ont_id], expr: "ont_id + '-suffix'"}
steps:
  - id: s1
    command: "show version"
    extract:                # parse values out of the command output
      - {name: sw_version, regex: "Software: ([0-9.]+)", group: 1}
  - id: s2
    command: "show ont {{ ont_id }}"   # templated command
    save: "ont/{{ ont_id }}.txt"        # templated save path
```

Safety: only whitelisted string methods (`split`, `upper`, `lower`,
`strip`, `replace`), arithmetic/comparison operators and context variables
are allowed in expressions — no arbitrary code execution.

### DCP meta-operations

Each step can use meta-operations:

```yaml
steps:
  - {id: s1, command: "show ver", skip: false}                  # skip a step
  - {id: s2, command: "show ver", condition: "model == 'X'"}    # gate on an expression
  - {id: s3, command: "show ver", wait: 1}                      # delay before running
  - id: s4                                                      # repeat over items
    command: "show ont {{ item }}"
    save: "ont/{{ item }}.txt"
    loop: {items: [ont-1, ont-2]}
```

## Sessions, ports & prompts

Ports and prompts are **configurable per session type** via `vendor.yml`
(no code change), falling back to the session class default:

```yaml
sessions:
  cli: { port: 22,    prompt: "\\w+[>#]" }    # SSH console
  tnd: { port: 11130, prompt: "TND[>#]" }     # SSH, different port + prompt
```

Precedence: explicit `endpoint.port` → vendor config → session class default.

## ONT cutthrough & SoC chipsets

An ONT is reached *through* the OLT: the OLT must be provisioned before the
ONT session can open. `OntCutthroughSession.connect()` runs the OLT-side
`prepare()` first (and `restore()` on close), enforcing the precondition.

ONTs are specialised by their management SoC (`ont_device_for`):
`realtek`/`mediatek`/`bcm`→ `RealtekOnt` / `MediaTekOnt` / `BroadcomOnt`, with
a generic fallback.

## Terminals

- `fncollect run` — run a DCP against one device.
- `fncollect collect` — run a semantic action across many devices, concurrently:
  ```bash
  fncollect collect --vendor mock --action inventory --devices 10.0.0.1,10.0.0.2
  fncollect collect --vendor isam --action inventory --devices 10.52.142.74 --user admin --password ...
  ```
  Credentials can come from `--user`/`--password` or environment
  `FNCOLLECT_USER` / `FNCOLLECT_PASSWORD` (never logged).
- `fncollect interact` — guided interactive menu (vendor → action → target).
- `fncollect vendors` / `fncollect actions` — list what's available.
- `fncollect init` — scaffold local `user/` config.

Each run writes `manifest.json`, `app.log`, raw artifacts, and reports
(`summary.md`, `results.json`, `results.csv`) under `fncollect_out/`.

## Real devices (legacy SSH)

Nokia ISAM-style devices only offer the legacy `ssh-rsa` (RSA-SHA1) host key
and require an interactive PTY + context-based CLI navigation. fncollect's
interactive SSH session (`net.py`) handles prompt detection, paging and
multi-token navigation. For these devices install the `net` extra with
paramiko 2.x:

```bash
python -m pip install -e '.[net]'   # uses paramiko>=2.12
```

## License

MIT. This project shares no code with any proprietary product.
