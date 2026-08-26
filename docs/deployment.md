# Production deployment

Public address: **https://grai-origin.agentshub.pl**

The application runs on a shared server, behind a single Caddy that terminates
TLS and routes traffic by host name. Containers belonging to other projects run
on the same machine, so resource limits apply.

## Environment

The repository names no server. Two variables carry the identity, both required,
neither with a default:

- `ORIGIN_REMOTE` - the ssh host alias of the target machine, used by
  `scripts/rt`, `scripts/rt-web` and `scripts/install-heavy`. Example:
  `export ORIGIN_REMOTE=my-server`.
- `CADDY_NETWORK` - the name of the shared external Docker network the reverse
  proxy is on, required by `docker-compose.prod.yml`. Example:
  `export CADDY_NETWORK=my-proxy-net`.

`ORIGIN_REMOTE_DIR` (default `/opt/grai-origin`) and `ORIGIN_CPU_QUOTA`
(default `4`) are optional overrides on the same scripts.

## Overriding principle

**Everything reaches production through the repository.** Changes are made
locally, committed and pushed, and the server pulls them. Nothing is copied to
the server with rsync or scp, and **nothing is edited directly on production**.
The `/var/www/grai-origin` directory on the server is an ordinary git clone and
its working tree is to stay clean.

## What is made of what

| Item | File | Container | Internal port |
|---|---|---|---|
| FastAPI backend (uvicorn) | `Dockerfile.api` | `grai-origin-api` | 8000 |
| Next.js front end | `web/Dockerfile` | `grai-origin-web` | 3000 |

Neither of them exposes a port on the host. Caddy reaches them by container name
through Docker DNS on the shared external network named by `$CADDY_NETWORK`.

The backend image installs only the dependencies from `[project.dependencies]`.
The `heavy` group (demucs, faster-whisper, basic-pitch) is **not installed**:
that is several gigabytes, and in mock mode nobody calls it.

`ffmpeg` is likewise not installed in the image. It is only needed for real
audio downloading (`ORIGIN_FFMPEG` in `src/origin/ingest.py`), that is with
`ORIGIN_MOCK=0`. That is a task for the moment the engine is wired in.

## Operating mode

`ORIGIN_MOCK=1`. The engine is not yet wired into the API, so without mock mode
`/api/analyze` responds with 503. The mock returns a complete response: the SSE
stream, the two-stage verdict and the full ranking.

`ORIGIN_MOCK_DELAY=0.4` sets the interval between stream events. Zero is the
pace for tests; a live demo needs to see the stages arriving one after another.

## Resource limits

They live in `docker-compose.yml`, not in the overlay, so that they apply even
when the stack is brought up without the production overlay.

| Container | `cpus` | `mem_limit` |
|---|---|---|
| `api` | 1.0 | 1280 MB |
| `web` | 0.5 | 640 MB |
| **total** | **1.5 cores** | **1920 MB** |

Checking the limits actually applied:

```bash
docker inspect grai-origin-api grai-origin-web \
  --format '{{.Name}} NanoCpus={{.HostConfig.NanoCpus}} Memory={{.HostConfig.Memory}}'
```

## Deployment and updates

```bash
cd /var/www/grai-origin
git pull
export CADDY_NETWORK=my-proxy-net    # required, no default
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
```

The first run is `git clone --branch <branch> https://github.com/PiotrZapolski/grai-origin.git grai-origin`
in `/var/www`, and then the same compose command.

## Caddy

The entry sits in the **shared** `/var/www/caddy/Caddyfile`, at the end of it.
The content of the block is also in a comment at the bottom of
`docker-compose.prod.yml`, so that it does not have to be reconstructed from
memory.

Rule order matters: Caddy takes the **first matching** `handle`, so the stream
block must come before the general `/api/*`.

After every change: backup, validate, only then reload.

```bash
cp /var/www/caddy/Caddyfile /var/www/caddy/Caddyfile.bak.$(date +%s)
docker compose -f /var/www/caddy/docker-compose.yml exec caddy caddy validate --config /etc/caddy/Caddyfile
docker compose -f /var/www/caddy/docker-compose.yml exec caddy caddy reload --config /etc/caddy/Caddyfile
```

## SSE - the one place where it is easy to fall over

The live analysis screen rests on the `GET /api/jobs/{id}/stream` stream. Two
things can kill it along the way, both on the proxy side:

1. **Missing `flush_interval -1`** - Caddy buffers the response and the entire
   run arrives in one piece at the end.
2. **`encode` on the stream path** - compression collects the body into blocks,
   which cancels out point 1 even when that one is set correctly.

That is why the Caddy block has an `@notstream` matcher disabling compression on
the stream path and a separate `handle` with `flush_interval -1`.

The backend, for its part, sets `Cache-Control: no-cache` and
`X-Accel-Buffering: no`.

**Verification after every proxy change** - through the public address, not on
the container:

```bash
ID=$(curl -sS -X POST https://grai-origin.agentshub.pl/api/analyze \
  -H 'Content-Type: application/json' \
  -d '{"url":"https://www.youtube.com/watch?v=demo","candidate_set":"demo_01"}' \
  | sed -E 's/.*"job_id":"([^"]+)".*/\1/')

curl -sN -H 'Accept: text/event-stream' \
  "https://grai-origin.agentshub.pl/api/jobs/$ID/stream" \
  | perl -MTime::HiRes=time -ne 'BEGIN{$|=1; $t0=time} next if /^\s*$/; printf("+%05.2fs %s", time-$t0, $_)'
```

A good result is frames roughly every `ORIGIN_MOCK_DELAY` seconds. A bad result
is all the frames with almost identical timestamps, at the end - that means
something along the way is buffering.

Also check the headers: `content-type: text/event-stream` and **no**
`content-encoding`.

## Backup

The project **has no database**, so `lib/discover.sh` rightly returns nothing
for it. The `/var/www/grai-origin` directory is picked up automatically by
`lib/files.sh`, because the file-system coverage includes every top-level
directory in `/var/www`.

The application state lives exclusively in process memory (jobs die together
with the server), and all the code comes from the repository, so a file snapshot
is the only safeguard needed and it works with no configuration at all.

Check:

```bash
cd /opt/backup && source config.env
./lib/discover.sh | grep grai      # empty - that is the correct result, there is no database
./lib/files.sh | grep grai         # must be /var/www/grai-origin
```
