import { createContext } from "react";
import type { Preferences } from "../lib/preferences";

export interface PreferencesContextValue {
  preferences: Preferences;
  profileId: string;
  save: (preferences: Preferences) => Promise<void>;
  reset: () => Promise<void>;
}

export const PreferencesContext = createContext<PreferencesContextValue | null>(null);
