const SVG_NAMESPACE = "http://www.w3.org/2000/svg";

const ICON_PATHS = {
  check: "M5 12.5 9.25 17 19 7",
  close: "m7 7 10 10M17 7 7 17",
  file: "M7 3.5h6l4 4v13H7zM13 3.5v4h4",
  folder: "M3.5 7.5h6l2-2h9v13h-17z",
  microphone: "M8 6a4 4 0 0 1 8 0v6a4 4 0 0 1-8 0zM5 11.5v.5a7 7 0 0 0 14 0v-.5M12 19v3M8.5 22h7",
  minus: "M6 12h12",
  play: "m8 5 11 7-11 7z",
  plug: "M8 3v5M16 3v5M6 8h12v2a6 6 0 0 1-6 6v5",
  profile: "M12 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8ZM4.5 21a7.5 7.5 0 0 1 15 0",
  restart: "M19.5 8.5V4l-2 2a8 8 0 1 0 2.1 8M19.5 4h-4.5",
  shield: "M12 3 20 6v5c0 5.25-3.25 8.5-8 10-4.75-1.5-8-4.75-8-10V6zM8.5 12.25 11 14.5l4.5-5",
  stop: "M7 7h10v10H7z",
  system: "M4 6h10M18 6h2M4 12h2M10 12h10M4 18h8M16 18h4M14 4v4M8 10v4M14 16v4",
  terminal: "M4 5h16v14H4zM7 9l3 3-3 3M12 15h5",
  voice: "M4 10v4M8 7v10M12 4v16M16 7v10M20 10v4",
} as const;

export type IconName = keyof typeof ICON_PATHS;
export type Tone = "neutral" | "success" | "warning" | "danger";

export function element<T extends HTMLElement = HTMLElement>(
  id: string,
  guard?: (value: HTMLElement) => value is T,
): T {
  const value = document.getElementById(id);
  if (!value) throw new Error(`Missing renderer element: ${id}`);
  if (guard && !guard(value)) {
    throw new Error(`Renderer element has an unexpected type: ${id}`);
  }
  return value as T;
}

function createIcon(name: IconName): SVGSVGElement {
  const icon = document.createElementNS(SVG_NAMESPACE, "svg");
  icon.setAttribute("aria-hidden", "true");
  icon.setAttribute("focusable", "false");
  icon.setAttribute("viewBox", "0 0 24 24");
  icon.classList.add("ui-icon");

  const path = document.createElementNS(SVG_NAMESPACE, "path");
  path.setAttribute("d", ICON_PATHS[name]);
  icon.append(path);
  return icon;
}

export function setIcon(target: HTMLElement, name: IconName): void {
  target.querySelector(":scope > .ui-icon")?.remove();
  target.prepend(createIcon(name));
  target.dataset.icon = name;
}

export function setIconButton(
  button: HTMLButtonElement,
  name: IconName,
  label: string,
): void {
  setIcon(button, name);
  button.setAttribute("aria-label", label);
  button.dataset.tooltip = label;
}

export function hydrateIcons(root: ParentNode = document): void {
  for (const target of root.querySelectorAll<HTMLElement>("[data-icon]")) {
    const name = target.dataset.icon;
    if (!name || !(name in ICON_PATHS)) {
      throw new Error(`Unknown Arthur icon: ${name ?? "missing"}`);
    }
    setIcon(target, name as IconName);
  }
}

export function setTone(target: HTMLElement, tone: Tone): void {
  target.dataset.tone = tone;
}
