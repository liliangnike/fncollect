# fncollect

A clean-room, multi-vendor **Fixed Network (FN) OLT/ONT log collector** and
troubleshooting assistant. Written from scratch in Python (no proprietary
source), designed to be extended to any FN vendor's product line.

> Status: early scaffold / MVP.

## What it does

fncollect connects to Fixed Network devices (OLT/ONT), runs declarative
**Data Collection Procedures (DCPs)**, and organises the captured output into
a timestamped run directory with a machine-readable `manifest.json`.

## Design goals

- **Clean architecture** — abstract `Vendor` / `Device` / `Action` interfaces.
- **Declarative DCPs** — collection procedures as YAML, no code changes to add
  a new collection.
- **Portable output** — every run has raw artifacts + a `manifest.json` for
  downstream tooling and AI.
- **Safe by default** — credentials redacted from logs; never logged.
- **Extensible** — add a new vendor by dropping in a pack (see below).

## Package layout

```
config/                 # committed defaults: fncollect.yml, vendor packs
src/fncollect/
  cli.py                # entry point (fncollect run/init/vendors)
  config.py             # Pydantic config loading + validation
  logging_setup.py      # console + rolling file, secret redaction
  session_ctx.py        # per-run dir + manifest
  variables.py          # typed variable context, safe expressions, templating
  vendor.py             # abstract Vendor/Device/Action contracts
  dcp.py                # DCP engine + meta-ops (loop/wait/skip) [WIP]
  vendors/              # pluggable vendor packs
    mock.py             # deterministic in-memory device (tests/demo)
tests/                  # pytest suite
```

## Quick start

```bash
python -m pip install -e '.[dev]'
python -m fncollect vendors          # list vendor packs
python -m fncollect run              # run with default mock vendor (no DCP)
python -m fncollect run --vendor mock --dcp config/dcps/basic_collect.yml
python -m fncollect init             # scaffold user/ config tree
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

## Terminals

- `fncollect run` — collect from a device via a DCP.
- `fncollect vendors` — list registered vendors.
- `fncollect init` — scaffold local `user/` config.

## License

MIT. This project shares no code with any proprietary product.
