# Measurements - target machine

Date: 2026-08-21
Host: <server-ip> (SSH alias `<ssh-host>`)
Remote directory: `/opt/grai-origin`

| Quantity | Value |
|---|---|
| Physical cores | 6 (AMD Ryzen 5 3600, 2 threads per core, 12 logical CPUs) |
| RAM | 62 GB (40 GB available) |
| Load average | 3.2 - 4.1 in the samples taken that day (most recent: 4.05 / 3.86 / 3.55) |
| Free space on /opt | 88 GB (`/opt` sits on `/`, 436 GB, 79% used) |
| Core quota for GRAI ORIGIN | 4 |

A quota of 4 is the default value of `ORIGIN_CPU_QUOTA` in `scripts/rt`, that is
`taskset -c 0-3`. Production for other projects keeps the load around 3.1, so
four cores for us leave it two physical cores untouched. Do not raise this
without measuring again.

The topology, because it is easy to draw the opposite conclusion from it. The
machine has **six** physical cores and twelve logical CPUs. Sibling threads are
numbered with an offset of 6, so `core_id` looks like this:

```
cpu0 -> core 0   cpu6  -> core 0
cpu1 -> core 1   cpu7  -> core 1
cpu2 -> core 2   cpu8  -> core 2
cpu3 -> core 4   cpu9  -> core 4
cpu4 -> core 5   cpu10 -> core 5
cpu5 -> core 6   cpu11 -> core 6
```

It follows that `taskset -c 0-5` takes **the whole physical processor**, not
half the machine, and leaves production not a single core of headroom. That is
why the quota is 4: `taskset -c 0-3` is physical cores 0, 1, 2 and 4, and cores
5 and 6 (`cpu4`, `cpu5`, `cpu10`, `cpu11`) stay with production.

## Environment

| Item | State |
|---|---|
| Python | 3.12.3 (system), venv in `/opt/grai-origin/.venv` |
| ffmpeg | 7.0.2 static from the pip package `imageio-ffmpeg`, **not** from apt |
| node | absent, Task 6 supplies it locally through nvm |
| rsync | 3.2.7 |
| CPU restriction | `nice -n 19` + `taskset -c 0-3` on pytest **and** on the venv and pip |
| Thread restriction | `OMP/OPENBLAS/MKL/NUMEXPR/NUMBA_NUM_THREADS` and `MAKEFLAGS` equal to the quota |

The machine hosts 84 production containers belonging to other projects. No
system-level installs via apt. Dependency installation runs under the same
throttling as the tests and only triggers when the checksum of `pyproject.toml`
changes (the `.venv/.deps-sha256` marker), so that building the `demucs` or
`basic-pitch` wheels in waves 6-7 does not eat the machine on every invocation
of `scripts/rt`.

## Operation timings (to be filled in during T15 and T14)

| Operation | 60 s clip | Notes |
|---|---|---|
| CQT + chroma | | |
| Acoustic fingerprint | | |
| faster-whisper base | | |
| demucs htdemucs | | |
