export type ThemePreference = "system" | "light" | "dark";

export function nextTheme(current: string | undefined): ThemePreference {
  return current === "system" || !current ? "light" : current === "light" ? "dark" : "system";
}

export function resolvedTheme(preference: ThemePreference, systemDark: boolean): "light" | "dark" {
  return preference === "system" ? (systemDark ? "dark" : "light") : preference;
}
