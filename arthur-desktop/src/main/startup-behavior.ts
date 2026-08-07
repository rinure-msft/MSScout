import type { DesktopPreferences } from "../shared/schemas";

export const HIDDEN_START_ARGUMENT = "--hidden";

export function loginItemArguments(
  preferences: DesktopPreferences,
): string[] {
  return preferences.startMinimized ? [HIDDEN_START_ARGUMENT] : [];
}

export function shouldStartHidden(arguments_: string[]): boolean {
  return arguments_.includes(HIDDEN_START_ARGUMENT);
}
