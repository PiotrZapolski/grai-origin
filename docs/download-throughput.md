# Audio downloading - throughput test

Date: 2026-08-21
Machine: Hetzner <server-ip> (SSH alias `<ssh-host>`), quota 4 cores
Tool: `scripts/fetch_audio.py`, library `yt_dlp` 2026.08.19
Excerpt: 60 s, concurrency 4

## The conclusion in one sentence

**From this machine nothing can be downloaded from YouTube today.** Twenty
addresses, zero successful downloads, nineteen rejected by bot control. An IDF
corpus of 3,000 works is unachievable in this arrangement, and that is not a
question of run time but of access.

## The sample

Twenty addresses drawn at random from the July SecondHandSongs dump
(`export_20260701.csv.zip`, column `youtube_url`). Reservoir sampling across the
whole file, seed 20260821, without unpacking the archive to disk:

```bash
unzip -p export_20260701.csv.zip | awk -v seed=20260821 -v k=20 '
BEGIN{srand(seed)}
{ if (match($0, /https:\/\/youtube\.com\/watch\?v=[A-Za-z0-9_-]+/)) {
    u = substr($0, RSTART, RLENGTH); n++;
    if (n <= k) res[n] = u; else { r = int(rand()*n)+1; if (r <= k) res[r] = u } } }
END{ for(i=1;i<=k;i++) print res[i] }'
```

The dump has 1,232,495 rows, of which 1,232,494 carry a YouTube address.

## The result

| Quantity | Value |
|---|---|
| Attempted | 20 |
| Successful | **0** |
| Failed | **20 (100%)** |
| Throttling ("Sign in to confirm you're not a bot") | **19** |
| Dead link ("Video unavailable") | 1 |
| Average time per entry | 1.04 s (min 0.90 s, max 1.48 s) |
| Time for the whole run, concurrency 4 | 5.69 s |

The run was repeated twice, at 21:43 and 21:52, with the same result item for
item (5.59 s and 5.69 s). This is not a momentary stumble, it is a steady state.

The average time of 1.04 s is **the time to be rejected, not to download**. Not a
single byte of audio was pulled: YouTube rejects the request already at the stage
of querying for the streams.

Full per-entry log: `data/cache/fetch_errors.jsonl` on the remote machine
(outside git), machine-readable report: `data/cache/przepustowosc2.json`.

## Is this throttling

Yes, unambiguously. The message reads literally:

```
Sign in to confirm you're not a bot. Use --cookies-from-browser or --cookies
for the authentication.
```

We saw no HTTP 429 and no gradual slowdown, because for that you first have to
download something. The block is **there from the first request**, not after
crossing a threshold. That points to a block by data-center IP address rather than
a rate limit.

Workarounds checked on the `yt_dlp` side itself, all rejected with the same
message: the default client, `tv_simply`, `web_safari`, `mweb`, `android_vr`,
`ios`, `web_embedded`. Changing the player client does not help.

## Extrapolation to 3,000 entries, concurrency 4

**The factual state today:** 3,160 attempts end after about 15 minutes with zero
files. The run is fast and useless.

**If access were unblocked** (cookies, proxy, a different connection), the
arithmetic looks like this. With 25% overage the pool is 3,750 entries, and with
the 5% dead-link rate measured on the sample about **3,160 attempts** are needed to
collect 3,000 files:

| Time per entry | Total time on 4 threads |
|---|---|
| 6 s | 1 h 19 min |
| 10 s | **2 h 12 min** |
| 15 s | 3 h 17 min |
| 10 s + 3 s anti-throttling pause | 2 h 51 min |

The 10 s variant is the most likely one and it is the one to use for planning.

**A note on the reliability of these numbers.** The time per entry is **an
assumption, not a measurement** - we have not a single successful YouTube download,
so there is nothing to measure. The only reference point is a control run on an
ordinary audio file over HTTPS: 1.15 MB plus conversion to wav took 3.21 s
including process startup. Downloading 60 s from YouTube adds the extractor query
and signature decryption, hence the estimate of 6-15 s.

The 5% dead-link rate comes from one hit out of twenty and has a confidence
interval of roughly 0.1-25%. The 25% overage from section 5.7 fits inside that
interval, but does not confirm it. Measurement will only be possible once access is
unblocked.

## RESERVATION

The failure rate is **100%**, that is four times above the 25% threshold in the
task, and **throttling occurred**. Per the agreed rule this means a change to the
project plan. To be settled before the corpus wave:

1. **Where to download from.** Ordered from most reliable:
   - downloading from a connection that is not a data center (a home or office
     machine) and sending the finished wav files to the server over rsync;
   - a residential or mobile proxy for the `yt_dlp` traffic;
   - cookies from a logged-in account (`--cookies`). The weakest option: an
     account used from a data-center address tends to get flagged after a few
     dozen requests, so it is suitable as a throwaway account, not as a main one.
2. **Whether the IDF corpus has to hold 3,000 entries.** If downloading ends up
   single-threaded through a proxy, 3,000 works is a different order of cost from
   500-800. The decision about corpus size is now a decision about the schedule.
3. **The demo candidate files are to sit locally before the show** (section 5.7).
   In the present state of access they have to be prepared ahead of time and over
   a different connection, rather than counting on downloading them on the day.

## Side finding: the static ffmpeg crashes on network input

During the control run on an ordinary audio file over HTTPS, `yt_dlp` ended with
the error `ffmpeg exited with code -11`, that is SIGSEGV.

Source: the static `ffmpeg` 7.0.2 from the `imageio-ffmpeg` package, the same one
that `scripts/rt` substitutes in. It processes local files correctly, but **every
network input ends in a memory access violation**, both `https://` and plain
`http://`. Checked by direct invocation, without `yt_dlp` involved.

What it means: `--download-sections` for non-fragmented formats reaches for the
external ffmpeg downloader and on this machine will always fall over. Fragmented
formats, that is all of YouTube, are handled by the native `yt_dlp` downloader and
that path is free of the problem, but we cannot check it while the block lasts.

The workaround is already in the code: after such a failure `_pobierz_jeden`
repeats the download without `download_ranges`, pulls the whole stream natively and
cuts out the 60 s only in postprocessing, on a file already sitting on disk.
Verified end to end on an address that had previously crashed ffmpeg: 1/1
successful in 3.21 s.

## How to repeat the measurement

```bash
# on the remote machine, after syncing the repo
cd /opt/grai-origin
export ORIGIN_CPU_QUOTA=4
export ORIGIN_FFMPEG="$(.venv/bin/python -c 'import imageio_ffmpeg; print(imageio_ffmpeg.get_ffmpeg_exe())')"
export PATH="/opt/grai-origin/.venv/ffmpeg-shim:$PATH"
nice -n 19 taskset -c 0-3 .venv/bin/python scripts/fetch_audio.py \
  --urls-file data/cache/urls20.txt \
  --docelowo 20 --wycinek 60 --wspolbieznosc 4 \
  --out-dir data/audio --report data/cache/throughput.json
```

`nice` and `taskset` are mandatory: without them `os.sched_getaffinity` sees twelve
CPUs on this machine instead of the four assigned, and `nproc --all` reports
thirty-two.

Repeating the same command downloads nothing a second time - a finished wav file in
the target directory counts as a success with no network traffic (measured: the
second run 0.0 s).
