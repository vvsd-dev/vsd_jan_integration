import path from "node:path";
import vue from "@vitejs/plugin-vue";
import frappeui from "frappe-ui/vite";
import autoprefixer from "autoprefixer";
import tailwindcss from "tailwindcss";
import { defineConfig } from "vite";

const FRAPPE_ASSET_BASE = "/assets/vsd_jan_integration/jan_ui/";
const FRAPPE_PUBLIC_DIR = path.resolve(__dirname, "../vsd_jan_integration/public/jan_ui");
const FRAPPE_WWW_ENTRY = path.resolve(__dirname, "../vsd_jan_integration/www/jan_ui.html");

export default defineConfig(({ command }) => {
	const isProdBuild = command === "build";

	return {
		base: isProdBuild ? FRAPPE_ASSET_BASE : "/",
		plugins: [
			frappeui({
				frappeProxy: true,
				jinjaBootData: true,
				lucideIcons: true,
				buildConfig: {
					outDir: FRAPPE_PUBLIC_DIR,
					indexHtmlPath: FRAPPE_WWW_ENTRY,
					emptyOutDir: true,
				},
			}),
			vue(),
		],
		css: {
			postcss: {
				plugins: [tailwindcss(), autoprefixer()],
			},
		},
		server: {
			port: 8081,
			host: "0.0.0.0",
		},
		resolve: {
			alias: {
				"@": path.resolve(__dirname, "src"),
				"tailwind.config.js": path.resolve(__dirname, "tailwind.config.js"),
				"feather-icons": path.resolve(__dirname, "src/shims/feather-icons.js"),
			},
		},
		build: {
			outDir: FRAPPE_PUBLIC_DIR,
			chunkSizeWarningLimit: 1500,
			emptyOutDir: true,
			target: "es2020",
			sourcemap: false,
		},
	};
});
