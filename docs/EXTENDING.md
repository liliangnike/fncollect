# fncollect Extending Guide

For **power users and integrators** who want to add vendors, procedures, or
understand the YAML behind fncollect. The whole design follows one idea:

> **Everything you do on an OLT/ONT is a YAML procedure. Code is only the
> engine (runner) + a library of value processors.**

- End users never need this file — see **`docs/USER_GUIDE.md`**.
- The runner itself is Python (`src/fncollect/`); customizing the *engine*
  requires a developer. Everything below customizes the *behavior* in YAML.

---

## 1. The architecture in one picture

```
fncollect_out/                      (run output)
config/fncollect.yml                (tool config: logging, retention, vendor)
config/vendors/<name>/vendor.yml    (per-vendor: sessions, actions, commands, probe)
config/vendors/<name>/dcps/*.yml    (procedures: probe, cutthrough, collections)

runner (src/fncollect engine):
   dial session -> run prepare/probe -> run collect procedures -> report
value processors (processors.py): regex | kv | grid | json | line
```

---

## 2. Vendor config — `config/vendors/<name>/vendor.yml`

```yaml
vendor: isam
transport: ssh
device_types: [7360-ISAM]
sessions:                      # session types: different port + prompt
  cli:  {port: 22,    prompt: "typ:\\S+(?:>[^>#]+)*#"}
  tnd:  {port: 11130, prompt: "[\\w-]+(?:>[^>#]+)*#"}   # NT_TND provisioning
actions: [inventory, ont_inventory, run_commands]
commands:                      # command catalog -> what each action runs
  inventory:
    - "show\nsystem\nentry"
    - "show\nequipment\nslot"
probe:                         # device-init: which procedure + how to map values
  procedure: probe.yml
  mappings:
    sw_version: version        # extracted var -> DeviceInfo field
    nt_board: attributes.nt_board
```

Key ideas:
- **Per-session-type ports & prompts** (CLI on 22, NT_TND on 11130) — even
  over the same SSH transport.
- Commands may be **multi-line** (`"show\nsystem\nentry"`) to express
  context navigation on ISAM-style CLIs.
- `probe.mappings` copies extracted values into the abstract **device**.

---

## 3. Procedures (DCP YAML)

A procedure is a list of steps. Each step runs a command and optionally
extracts values.

```yaml
name: isam_probe
vendor: isam
parameters:                       # optional typed inputs
  - {name: slot, type: string}
derivations:                      # optional computed variables
  - {name: upper_model, from: [model], expr: "model.upper()"}
steps:
  - id: release
    command: "show\nsoftware-mngt\nversion\nansi"
    extract:
      - {name: sw_version, parser: regex,
         regex: "R([0-9]+(?:\\.[0-9]+)+)", group: 1}

  - id: boards
    command: "show\nequipment\nslot"
    extract:
      - {name: slots, parser: grid, kind: count}

  - id: conditional    # meta-ops: skip / condition / wait / loop
    command: "show alarms"
    condition: "sw_version != ''"
    save: "alarms/alarms.txt"
```

### Value processors (`parser:`)
| parser | meaning |
|---|---|
| `regex` | capture by regex + `group`/`named_groups` |
| `kv` | `key : value` / `key=value` lines (`key:`) |
| `grid` | tables (`kind: count\u007crow\u007ccolumn\u007ccell`, `row:`, `column:`) |
| `json` | extract a JSON blob |
| `line` | pick a line / count lines |

### Variables & templating
- `parameters` declare typed inputs (`string`, `int`, `ip`, `enum`, `password`).
- `extract` values enter the variable context; use **`{{ name }}`** in commands
  and `save:` paths.
- `derivations` compute new values with **safe expressions** (no arbitrary code).
- Every run writes the context to `variables/variables.json`.

### Meta-operations per step
| meta-op | effect |
|---|---|
| `skip: true` | don't run |
| `condition: "<expr>"` | run only if expr is truthy |
| `wait: <sec>` | sleep before running |
| `loop: {items: [...]}` | repeat over items; `{{ item }}` in command/save |

---

## 4. The three operation types (unified framework)

`src/fncollect/operations.py` implements one dispatcher for three kinds:

| `type` | purpose | example |
|---|---|---|
| `exec` | just run + save output | run a command |
| `get` | run + process + **extract value** | get OLT version |
| `configure` | run config command(s) + optional **verify** | configure an ONT from the OLT |

Example:
```yaml
- type: get
  command: "show\nsoftware-mngt\nversion\nansi"
  get: {extract: [{name: ver, parser: regex, regex: "R(.+)", group: 1}]}
- type: configure
  configure: {commands: ["..."], verify: [{name: ok, parser: kv, key: status}]}
```

---

## 5. Device initialization (probe)

On connect, the `probe` procedure runs and its values populate the **abstract
device**:
- `DeviceInfo`: `version`, `model`, `serial`, `chipset`, ...
- `device.attributes`: extra rich data (`probe.mappings` `attributes.x`).

The same regexp/value-processor machinery powers `get`/probe and collection.

---

## 6. ONT cutthrough (configuring the OLT for an ONT)

ONT sessions are reached *through* the OLT. Two DCP procedures do the work:
- **setup** (`ont_cutthrough_setup.yml`) — OLT-side (NT_TND) provisioning:
  set client IP, provision GPON index with debug-VLAN, verify.
- **teardown** (`ont_cutthrough_teardown.yml`) — restore on close.

`IsamVendor.build_ont_cutthrough(...)` runs these via
`DcpCutthroughProvider` (prepare) and restore (teardown). Commands in the
two files are **placeholders** — replace with your device's real TND syntax.

ONT devices are specialised by SoC: `realtek` / `mediatek` / `bcm` / generic.

---

## 7. Semantic actions

`actions.py` has reusable `CommandBatchAction`s registered by name:
- `inventory` — run the vendor's `commands.inventory`
- `ont_inventory` — run `commands.ont_inventory`
- `run_commands` — run arbitrary commands (`--commands`)

Add your own by subclassing `CommandBatchAction` and registering it, or just
add commands to the vendor's YAML catalog.

---

## 8. Concurrency & reporting

- `engine.py::ConcurrentRunner` runs many devices in parallel
  (`concurrency.max_parallel_devices`).
- Each run writes `manifest.json`, `app.log`, raw artifacts, and
  `reports/{summary.md,results.json,results.csv}`.
- Logging redacts configured secrets (`logging.redact`) and never logs
  credentials.

---

## Adding a brand-new vendor (checklist)
1. `config/vendors/<name>/vendor.yml` — sessions, actions, commands, probe.
2. `config/vendors/<name>/dcps/` — `probe.yml`, any collections/cutthrough.
3. `src/fncollect/vendors/<name>/__init__.py` — a `Vendor` subclass that
   defines its `Session` classes and `hardware` dispatch; register it.
4. Run: `fncollect procedures --vendor <name>` then `fncollect run --vendor
   <name> --procedure probe ...`.
