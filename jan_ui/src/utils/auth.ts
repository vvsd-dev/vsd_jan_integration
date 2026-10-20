import type { Router } from "vue-router";
import { JAN_UI_BASE } from "../constants";
import type { BootUser } from "./session";
import { getBootUser } from "./session";

function csrfHeaders(extra: Record<string, string> = {}): Record<string, string> {
	const t = (window as unknown as { csrf_token?: string }).csrf_token;
	const h: Record<string, string> = { Accept: "application/json", ...extra };
	if (t) h["X-Frappe-CSRF-Token"] = t;
	return h;
}

function cleanFrappeErrorMessage(message: string): string {
	return message
		.replace(/^frappe\.exceptions\.[A-Za-z]+Error:\s*/i, "")
		.replace(/^[A-Za-z]+Error:\s*/i, "")
		.trim();
}

function parseFrappeError(data: Record<string, unknown>): string {
	const msg = data.message;
	if (typeof msg === "string" && msg.trim()) return cleanFrappeErrorMessage(msg);
	const exc = data.exception;
	if (typeof exc === "string" && exc.trim()) return cleanFrappeErrorMessage(exc);
	const sm = data._server_messages;
	if (typeof sm === "string") {
		try {
			const arr = JSON.parse(sm) as Array<{ message?: string }>;
			const first = arr[0];
			if (first?.message) return cleanFrappeErrorMessage(String(first.message));
		} catch {
			/* ignore */
		}
	}
	return "Login failed";
}

export async function loginWithPassword(usr: string, pwd: string): Promise<void> {
	const body = new URLSearchParams({ usr: usr.trim(), pwd });
	const r = await fetch("/api/method/login", {
		method: "POST",
		headers: csrfHeaders({ "Content-Type": "application/x-www-form-urlencoded" }),
		credentials: "include",
		body,
	});
	let data: Record<string, unknown> = {};
	try {
		data = (await r.json()) as Record<string, unknown>;
	} catch {
		if (!r.ok) throw new Error("Login failed");
	}
	if (!r.ok) {
		throw new Error(parseFrappeError(data));
	}
}

export async function hydrateSessionUserFromApi(): Promise<BootUser | null> {
	const r = await fetch("/api/method/vsd_jan_integration.www.jan_ui.get_session_user", {
		method: "GET",
		headers: csrfHeaders(),
		credentials: "include",
	});
	const data = (await r.json()) as { message?: unknown };
	const raw = data.message;
	if (!raw || typeof raw !== "object") return null;
	const o = raw as Record<string, unknown>;
	const name = o.name;
	if (typeof name !== "string" || !name.trim()) return null;
	const full_name =
		typeof o.full_name === "string" && o.full_name.trim() ? o.full_name : name;
	const user_image =
		typeof o.user_image === "string" && o.user_image.trim() ? o.user_image : "";
	const roles = Array.isArray(o.roles) ? (o.roles as string[]) : [];
	const u: BootUser = { name, full_name, user_image, roles };
	(window as unknown as { user?: BootUser }).user = u;
	return u;
}

export async function logoutSession(): Promise<void> {
	await fetch("/api/method/logout", {
		method: "POST",
		headers: csrfHeaders({ "Content-Type": "application/x-www-form-urlencoded" }),
		credentials: "include",
		body: new URLSearchParams(),
	});
	(window as unknown as { user?: BootUser | null }).user = undefined;
}

export function loginPageHref(): string {
	return `${JAN_UI_BASE}/login`;
}

export function normalizeSpaRouterPath(redirectTo: string | undefined): string {
	if (!redirectTo?.trim()) return "/dashboard";
	const t = redirectTo.trim();
	if (t === JAN_UI_BASE || t === `${JAN_UI_BASE}/`) return "/dashboard";
	if (t.startsWith(`${JAN_UI_BASE}/`)) return t.slice(JAN_UI_BASE.length) || "/dashboard";
	if (t.startsWith("/")) return t;
	return "/dashboard";
}

export async function completeLoginNavigation(
	router: Router,
	redirectTo: string | undefined,
): Promise<void> {
	const target = normalizeSpaRouterPath(redirectTo);
	await hydrateSessionUserFromApi();
	if (getBootUser()) {
		await router.replace(target);
		return;
	}
	window.location.assign(`${JAN_UI_BASE}${target}`);
}
