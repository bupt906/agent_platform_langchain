export type ThemePreference = "light" | "dark" | "system";

export interface Preferences {
  theme: ThemePreference;
  defaultModel: string;
  apiBaseUrl: string;
}

export const DEFAULT_PREFERENCES: Preferences = {
  theme: "light",
  defaultModel: "",
  apiBaseUrl: "",
};

const STORAGE_KEY = "agent-studio-preferences";
const PROFILE_ID_KEY = "agent-studio-profile-id";

export function getPreferences(): Preferences {
  if (typeof window === "undefined") return DEFAULT_PREFERENCES;
  try {
    const stored = JSON.parse(window.localStorage.getItem(STORAGE_KEY) || "{}") as Partial<Preferences>;
    return { ...DEFAULT_PREFERENCES, ...stored };
  } catch {
    return DEFAULT_PREFERENCES;
  }
}

export function savePreferences(preferences: Preferences) {
  window.localStorage.setItem(STORAGE_KEY, JSON.stringify(preferences));
}

export function clearPreferences() {
  window.localStorage.removeItem(STORAGE_KEY);
}

export function getProfileId() {
  const existing = window.localStorage.getItem(PROFILE_ID_KEY);
  if (existing) return existing;
  const profileId = crypto.randomUUID();
  window.localStorage.setItem(PROFILE_ID_KEY, profileId);
  return profileId;
}
