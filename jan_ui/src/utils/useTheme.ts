import { onMounted } from "vue";

export type ThemePreference = "light" | "dark" | "system";

const STORAGE_KEY = "jan_ui:theme";

let mediaQuery: MediaQueryList | null = null;

function applyResolvedTheme(resolved: Exclude<ThemePreference, "system">) {
	document.documentElement.setAttribute("data-theme", resolved);
	document.documentElement.classList.toggle("dark", resolved === "dark");
}

function resolveTheme(preference: ThemePreference): Exclude<ThemePreference, "system"> {
	if (preference === "system") {
		const prefersDark = window.matchMedia?.("(prefers-color-scheme: dark)")?.matches;
		return prefersDark ? "dark" : "light";
	}
	return preference;
}

function applyTheme(preference: ThemePreference) {
	applyResolvedTheme(resolveTheme(preference));
}

export function getStoredThemePreference(): ThemePreference {
	try {
		const saved = localStorage.getItem(STORAGE_KEY);
		if (saved === "light" || saved === "dark" || saved === "system") return saved;
	} catch {
		/* ignore */
	}
	return "system";
}

export function setTheme(preference: ThemePreference) {
	try {
		localStorage.setItem(STORAGE_KEY, preference);
	} catch {
		/* ignore */
	}
	applyTheme(preference);

	if (mediaQuery) {
		mediaQuery.onchange = null;
		mediaQuery = null;
	}
	if (preference === "system" && typeof window !== "undefined" && window.matchMedia) {
		mediaQuery = window.matchMedia("(prefers-color-scheme: dark)");
		mediaQuery.onchange = () => applyTheme("system");
	}
}

export function initTheme(): ThemePreference {
	const saved = getStoredThemePreference();
	setTheme(saved);
	return saved;
}

export function useTheme() {
	onMounted(() => initTheme());
	return { setTheme, initTheme };
}
