import { useEffect, useMemo, useState, type ReactNode } from "react";
import { api } from "../lib/api";
import {
  clearPreferences,
  DEFAULT_PREFERENCES,
  getPreferences,
  getProfileId,
  savePreferences,
  type Preferences,
} from "../lib/preferences";
import { PreferencesContext } from "./preferencesContext";

export function PreferencesProvider({ children }: { children: ReactNode }) {
  const [preferences, setPreferences] = useState<Preferences>(() => getPreferences());
  const [profileId] = useState(() => getProfileId());
  useEffect(() => applyTheme(preferences.theme), [preferences.theme]);
  useEffect(() => {
    api.getPreferences(profileId)
      .then((remote) => {
        const next = {
          theme: remote.theme,
          defaultModel: remote.default_model,
          apiBaseUrl: remote.api_base_url,
        };
        savePreferences(next);
        setPreferences(next);
      })
      .catch(() => {
        // 后端暂不可用时继续使用本地设置
      });
  }, [profileId]);
  const value = useMemo(
    () => ({
      preferences,
      profileId,
      save: async (next: Preferences) => {
        await api.updatePreferences(
          profileId,
          { theme: next.theme, default_model: next.defaultModel, api_base_url: next.apiBaseUrl },
          preferences.apiBaseUrl,
        );
        savePreferences(next);
        setPreferences(next);
      },
      reset: async () => {
        await api.updatePreferences(
          profileId,
          { theme: DEFAULT_PREFERENCES.theme, default_model: "", api_base_url: "" },
          preferences.apiBaseUrl,
        );
        clearPreferences();
        setPreferences(DEFAULT_PREFERENCES);
      },
    }),
    [preferences, profileId],
  );
  return <PreferencesContext.Provider value={value}>{children}</PreferencesContext.Provider>;
}

function applyTheme(theme: Preferences["theme"]) {
  const isDark =
    theme === "dark" ||
    (theme === "system" && window.matchMedia("(prefers-color-scheme: dark)").matches);
  document.documentElement.dataset.theme = isDark ? "dark" : "light";
}
