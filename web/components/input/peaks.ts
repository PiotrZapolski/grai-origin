/**
 * Waveform samples computed **in the browser**, before the analysis starts.
 *
 * Screen E1 has no right to show an empty loading screen (section 13.2), so the
 * shape of the wave has to appear the moment the material is chosen, not after
 * the backend answers. We compute it locally from the file or from an asset on
 * the same origin - nothing here goes out to the public network.
 *
 * Every function returns `null` instead of throwing. Missing Web Audio (SSR,
 * jsdom in tests), blocked CORS or an address that is not audio are normal
 * states of the entry screen, not failures: the waveform then falls back to a
 * placeholder state that **does not pretend to be a measurement**.
 */

/** How many bars the waveform draws. More does not improve legibility on a projector. */
export const DEFAULT_BUCKETS = 120;

type AudioContextConstructor = new () => AudioContext;

function audioContextConstructor(): AudioContextConstructor | null {
  if (typeof window === "undefined") return null;
  const scope = window as unknown as {
    AudioContext?: AudioContextConstructor;
    webkitAudioContext?: AudioContextConstructor;
  };
  return scope.AudioContext ?? scope.webkitAudioContext ?? null;
}

/**
 * Whether it is worth trying at all. Checked **before** reaching for any data,
 * so that in an environment without Web Audio not a single network request goes
 * out.
 */
export function canComputePeaks(): boolean {
  return audioContextConstructor() !== null;
}

/** The peak value in each bucket, normalized to the 0-1 range. */
export function peaksFromBuffer(buffer: AudioBuffer, buckets = DEFAULT_BUCKETS): number[] {
  const channel = buffer.getChannelData(0);
  const perBucket = Math.max(1, Math.floor(channel.length / buckets));
  const result: number[] = [];
  let maximum = 0;

  for (let i = 0; i < buckets; i += 1) {
    const start = i * perBucket;
    let peak = 0;
    for (let j = start; j < start + perBucket && j < channel.length; j += 1) {
      const value = Math.abs(channel[j]);
      if (value > peak) peak = value;
    }
    if (peak > maximum) maximum = peak;
    result.push(peak);
  }

  // Silence stays silence. Dividing by zero would lift the noise to full scale.
  if (maximum <= 0) return result;
  return result.map((value) => value / maximum);
}

async function fromData(data: ArrayBuffer, buckets: number): Promise<number[] | null> {
  const Context = audioContextConstructor();
  if (!Context) return null;
  const context = new Context();
  try {
    const buffer = await context.decodeAudioData(data);
    return peaksFromBuffer(buffer, buckets);
  } catch {
    return null;
  } finally {
    // Every context occupies an audio thread of the browser. Three examples in a
    // row without closing means three threads hanging until the end of the show.
    void context.close?.();
  }
}

/** Samples from a file dropped onto the screen. Nothing leaves the browser. */
export async function peaksFromFile(
  file: File,
  buckets = DEFAULT_BUCKETS,
): Promise<number[] | null> {
  if (!canComputePeaks()) return null;
  try {
    return await fromData(await file.arrayBuffer(), buckets);
  } catch {
    return null;
  }
}

/**
 * Samples from an address. Works for assets on the same origin - that is, for
 * the three prepared examples that live in `web/public/examples/`. A YouTube
 * address will return `null` (CORS) and that is a correct result, not an error
 * to report.
 */
export async function peaksFromUrl(
  url: string,
  buckets = DEFAULT_BUCKETS,
  signal?: AbortSignal,
): Promise<number[] | null> {
  if (!canComputePeaks()) return null;
  try {
    const response = await fetch(url, { signal });
    if (!response.ok) return null;
    return await fromData(await response.arrayBuffer(), buckets);
  } catch {
    return null;
  }
}
