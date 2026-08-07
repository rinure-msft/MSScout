import { app, nativeImage, type NativeImage } from "electron";
import {
  buildFallbackTrayBitmap,
  fallbackTrayColor,
  FALLBACK_ICON_SIZE,
  type TrayIconVariant,
} from "./tray-icon-fallback";

const TRAY_ICON_SIZE = 32;

const TRAY_ICON_VARIANTS: readonly TrayIconVariant[] = [
  "stopped",
  "listening",
  "active",
  "error",
  "pulse",
];

export type TrayIconSet = Record<TrayIconVariant, NativeImage>;

export function tintTrayBitmap(
  source: Buffer,
  variant: Exclude<TrayIconVariant, "active">,
): Buffer {
  const [targetRed, targetGreen, targetBlue] = fallbackTrayColor(variant);
  const output = Buffer.from(source);
  for (let offset = 0; offset < output.length; offset += 4) {
    const alpha = source[offset + 3] ?? 0;
    if (alpha === 0) continue;
    const blue = source[offset] ?? 0;
    const green = source[offset + 1] ?? 0;
    const red = source[offset + 2] ?? 0;
    const luminance = (0.2126 * red + 0.7152 * green + 0.0722 * blue) / 255;
    const intensity = 0.58 + luminance * 0.42;
    output[offset] = Math.round(targetBlue * intensity);
    output[offset + 1] = Math.round(targetGreen * intensity);
    output[offset + 2] = Math.round(targetRed * intensity);
    output[offset + 3] = alpha;
  }
  return output;
}

function fallbackIcon(variant: TrayIconVariant): NativeImage {
  return nativeImage.createFromBitmap(
    buildFallbackTrayBitmap(variant, FALLBACK_ICON_SIZE),
    { width: FALLBACK_ICON_SIZE, height: FALLBACK_ICON_SIZE },
  );
}

function buildFallbackTrayIconSet(): TrayIconSet {
  const icons = {} as TrayIconSet;
  for (const variant of TRAY_ICON_VARIANTS) {
    icons[variant] = fallbackIcon(variant);
  }
  return icons;
}

/**
 * Uses Arthur.exe's embedded icon, generated from the canonical Arthur SVG,
 * as the tray silhouette. State variants tint the bitmap while preserving
 * its alpha, shading and exact geometry. The active state keeps the original
 * product gradient.
 */
export async function buildTrayIconSet(): Promise<TrayIconSet> {
  try {
    const executableIcon = await app.getFileIcon(process.execPath, { size: "large" });
    if (executableIcon.isEmpty()) {
      throw new Error("Arthur's executable icon was empty.");
    }
    const base = executableIcon.resize({
      width: TRAY_ICON_SIZE,
      height: TRAY_ICON_SIZE,
      quality: "best",
    });
    const bitmap = base.toBitmap({ scaleFactor: 1 });
    if (bitmap.length !== TRAY_ICON_SIZE * TRAY_ICON_SIZE * 4) {
      throw new Error(`Arthur's tray bitmap had an unexpected size: ${String(bitmap.length)}.`);
    }

    return {
      stopped: nativeImage.createFromBitmap(tintTrayBitmap(bitmap, "stopped"), {
        width: TRAY_ICON_SIZE,
        height: TRAY_ICON_SIZE,
      }),
      listening: nativeImage.createFromBitmap(tintTrayBitmap(bitmap, "listening"), {
        width: TRAY_ICON_SIZE,
        height: TRAY_ICON_SIZE,
      }),
      active: base,
      error: nativeImage.createFromBitmap(tintTrayBitmap(bitmap, "error"), {
        width: TRAY_ICON_SIZE,
        height: TRAY_ICON_SIZE,
      }),
      pulse: nativeImage.createFromBitmap(tintTrayBitmap(bitmap, "pulse"), {
        width: TRAY_ICON_SIZE,
        height: TRAY_ICON_SIZE,
      }),
    };
  } catch (error) {
    console.error(
      "Arthur could not derive tray icons from its executable icon; using explicit fallback icons.",
      error,
    );
    return buildFallbackTrayIconSet();
  }
}
