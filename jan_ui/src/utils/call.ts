import type { InjectionKey } from "vue";
import { inject } from "vue";
import router from "@/router";

export type JanCall = (method: string, args?: Record<string, unknown>) => Promise<unknown>;

export const janCallKey: InjectionKey<JanCall> = Symbol("janCall");

export default async function call(
	this: { state?: string | null; errorMessage?: string | null } | undefined,
	method: string,
	args?: Record<string, unknown>,
) {
	if (!args) args = {};

	const headers: Record<string, string> = {
		Accept: "application/json",
		"Content-Type": "application/json; charset=utf-8",
		"X-Frappe-Site-Name": window.location.hostname,
	};

	const csrf = (window as unknown as { csrf_token?: string }).csrf_token;
	if (csrf && csrf !== "{{ csrf_token }}") {
		headers["X-Frappe-CSRF-Token"] = csrf;
	}

	if (this?.state !== undefined) this.state = "RequestStarted";

	const res = await fetch(`/api/method/${method}`, {
		method: "POST",
		headers,
		credentials: "include",
		body: JSON.stringify(args),
	});

	if (res.ok) {
		if (this?.state !== undefined) this.state = null;
		if (this?.errorMessage !== undefined) this.errorMessage = null;
		const data = await res.json();
		if (data.docs || method === "login") return data;
		return data.message;
	}

	let response = await res.text();
	let error: Record<string, unknown> = {};
	let exception: string | undefined;
	try {
		error = JSON.parse(response);
	} catch {
		/* ignore */
	}
	if (error.exc) {
		exception = String(error.exc);
		try {
			exception = JSON.parse(exception)[0];
		} catch {
			/* ignore */
		}
	}
	const e = new Error("") as Error & {
		exc_type?: unknown;
		exc?: string;
		messages?: string[];
	};
	e.exc_type = error.exc_type;
	e.exc = exception;
	e.messages = error._server_messages ? JSON.parse(String(error._server_messages)) : [];
	e.messages = e.messages.concat(error.message as string);
	e.messages = e.messages.map((m) => {
		try {
			return JSON.parse(m).message;
		} catch {
			return m;
		}
	});
	e.messages = e.messages.filter(Boolean);
	if (!e.messages.length) {
		// Prefer a short last line from the traceback over dumping the whole stack
		const shortExc = exception
			? String(exception)
					.split("\n")
					.map((l) => l.trim())
					.filter(Boolean)
					.slice(-1)[0]
			: "";
		e.messages = error._error_message
			? [String(error._error_message)]
			: shortExc
				? [shortExc]
				: ["Internal Server Error"];
	}
	e.message = e.messages.join("\n");
	if (this?.state !== undefined) this.state = null;
	if (this?.errorMessage !== undefined) this.errorMessage = e.messages.join("\n");

	if ([401, 403].includes(res.status) && router.currentRoute.value.name !== "Login") {
		router.push("/login");
	}
	throw e;
}

export function useJanCall(): JanCall {
	const c = inject(janCallKey);
	if (!c) throw new Error("janCall not provided");
	return c;
}
