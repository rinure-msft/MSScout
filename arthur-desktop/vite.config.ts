import { resolve } from "node:path";
import { defineConfig, type UserConfig } from "vite";

const projectRoot = __dirname;

export default defineConfig(({ mode }): UserConfig => {
  const shared = {
    sourcemap: false,
    minify: "esbuild" as const,
    emptyOutDir: false,
  };

  if (mode === "main") {
    return {
      build: {
        ...shared,
        lib: {
          entry: resolve(projectRoot, "src/main/index.ts"),
          formats: ["cjs"],
          fileName: () => "index.js",
        },
        outDir: resolve(projectRoot, "dist/main"),
        rollupOptions: { external: ["electron", /^node:/] },
      },
    };
  }

  if (mode === "preload") {
    return {
      build: {
        ...shared,
        lib: {
          entry: resolve(projectRoot, "src/preload/index.ts"),
          formats: ["cjs"],
          fileName: () => "index.cjs",
        },
        outDir: resolve(projectRoot, "dist/preload"),
        rollupOptions: { external: ["electron", /^node:/] },
      },
    };
  }

  return {
    root: resolve(projectRoot, "src/renderer"),
    base: "./",
    build: {
      ...shared,
      assetsInlineLimit: 0,
      outDir: resolve(projectRoot, "dist/renderer"),
      rollupOptions: {
        input: {
          index: resolve(projectRoot, "src/renderer/index.html"),
          popover: resolve(projectRoot, "src/renderer/popover.html"),
          halo: resolve(projectRoot, "src/renderer/halo.html"),
          widget: resolve(projectRoot, "src/renderer/widget.html"),
        },
      },
    },
  };
});
