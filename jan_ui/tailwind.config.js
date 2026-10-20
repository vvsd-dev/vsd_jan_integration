import frappeUIPreset from "frappe-ui/tailwind";

export default {
	darkMode: ["class", '[data-theme="dark"]'],
	presets: [frappeUIPreset],
	content: [
		"./index.html",
		"./src/**/*.{vue,js,ts,jsx,tsx}",
		"./node_modules/frappe-ui/src/components/**/*.{vue,js,ts,jsx,tsx}",
	],
	theme: {
		extend: {},
	},
	plugins: [],
};
