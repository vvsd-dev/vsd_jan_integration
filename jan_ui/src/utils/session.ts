export type BootUser = {
	name: string;
	full_name: string;
	user_image?: string;
	roles: string[];
};

function normalizeBootUser(raw: unknown): BootUser | null {
	if (!raw || typeof raw !== "object") return null;
	const o = raw as Record<string, unknown>;
	const name = o.name;
	if (typeof name !== "string" || !name.trim()) return null;
	const full_name =
		typeof o.full_name === "string" && o.full_name.trim() ? o.full_name : name;
	const user_image =
		typeof o.user_image === "string" && o.user_image.trim() ? o.user_image : "";
	const roles = Array.isArray(o.roles) ? (o.roles as string[]) : [];
	return { name, full_name, user_image, roles };
}

export function getBootUser(): BootUser | null {
	const u = (window as unknown as { user?: unknown }).user;
	return normalizeBootUser(u);
}
