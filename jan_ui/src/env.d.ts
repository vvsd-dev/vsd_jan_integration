/// <reference types="vite/client" />

declare module "~icons/*" {
	import type { DefineComponent } from "vue";
	const component: DefineComponent;
	export default component;
}

declare module "*.vue" {
	import type { DefineComponent } from "vue";
	const component: DefineComponent;
	export default component;
}

interface Window {
	csrf_token?: string;
	user?: {
		name: string;
		full_name: string;
		user_image?: string;
		roles: string[];
	} | null;
}
