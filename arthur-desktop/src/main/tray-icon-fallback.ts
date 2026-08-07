import type { TrayVisualState } from "./tray-state";

/** Default fallback icon size in pixels; Windows scales tray icons as needed. */
export const FALLBACK_ICON_SIZE = 32;

export type TrayIconVariant = TrayVisualState | "pulse";

const FALLBACK_COLORS: Record<TrayIconVariant, readonly [number, number, number]> = {
  stopped: [138, 138, 138],
  listening: [0, 120, 212],
  active: [177, 31, 75],
  error: [245, 158, 11],
  pulse: [77, 166, 255],
};

export function fallbackTrayColor(state: TrayIconVariant): readonly [number, number, number] {
  return FALLBACK_COLORS[state];
}

/**
 * Builds a raw BGRA bitmap buffer (Electron's `nativeImage.createFromBitmap`
 * input format) depicting a filled circle in the state colour. This is used
 * only when rendering the real Arthur ribbon mark fails, so the tray never
 * silently ends up with an empty icon. No image codec or extra dependency is
 * required: BGRA bitmaps are consumed directly by Electron.
 */
export function buildFallbackTrayBitmap(
  state: TrayIconVariant,
  size: number = FALLBACK_ICON_SIZE,
): Buffer {
  const [red, green, blue] = fallbackTrayColor(state);
  const buffer = Buffer.alloc(size * size * 4);
  const center = (size - 1) / 2;
  const radius = size / 2 - 1;
  for (let y = 0; y < size; y += 1) {
    for (let x = 0; x < size; x += 1) {
      const distance = Math.hypot(x - center, y - center);
      const inside = distance <= radius;
      const offset = (y * size + x) * 4;
      // Electron bitmap buffers are BGRA.
      buffer[offset] = blue;
      buffer[offset + 1] = green;
      buffer[offset + 2] = red;
      buffer[offset + 3] = inside ? 255 : 0;
    }
  }
  return buffer;
}
