import { createApp } from "vue";
import { FrappeUI } from "frappe-ui";
import "frappe-ui/style.css";
import "./tailwind.css";
import App from "./App.vue";
import router from "./router";
import call, { janCallKey } from "./utils/call";
import { hydrateSessionUserFromApi } from "./utils/auth";
import { getBootUser } from "./utils/session";
import { initTheme } from "./utils/useTheme";

initTheme();

const app = createApp(App);
app.use(router);
app.use(FrappeUI, {
	resources: false,
	call: false,
	socketio: false,
});
app.provide("$call", call);
app.provide(janCallKey, call);

async function start() {
	if (!getBootUser()) {
		await hydrateSessionUserFromApi();
	}
	app.mount("#app");
}

void start();
