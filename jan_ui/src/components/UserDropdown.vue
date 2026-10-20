<template>
	<Dropdown :options="dropdownItems">
		<template v-slot="{ open }">
			<button
				type="button"
				aria-label="Open account menu"
				class="flex h-14 w-full items-center gap-2 rounded-md py-2 duration-300 ease-in-out text-left"
				:class="
					isCollapsed
						? 'w-auto px-0'
						: open
							? 'bg-surface-selected shadow-sm px-2'
							: 'px-2 hover:bg-surface-gray-3'
				"
			>
				<div
					class="flex shrink-0 items-center justify-center overflow-visible"
					:class="isCollapsed ? 'h-10 w-10' : 'h-11 w-11'"
				>
					<img
						:src="headerImageSrc"
						alt=""
						:class="
							userImageSrc
								? 'h-10 w-10 rounded-full object-cover ring-1 ring-outline-gray-2'
								: 'h-10 max-h-10 w-auto max-w-full object-contain object-left'
						"
						height="40"
					/>
				</div>
				<div
					class="flex min-w-0 flex-1 flex-col duration-300 ease-in-out"
					:class="isCollapsed ? 'ml-0 w-0 overflow-hidden opacity-0' : 'ml-0 w-auto opacity-100'"
				>
					<span class="truncate text-sm font-semibold leading-tight text-ink-gray-8">
						Jan UI
					</span>
					<span class="mt-0.5 truncate text-xs leading-tight text-ink-gray-6">
						{{ displayName }}
					</span>
				</div>
			</button>
		</template>
	</Dropdown>
</template>

<script setup lang="ts">
import { computed, inject, markRaw } from "vue";
import { Dropdown } from "frappe-ui";
import { loginPageHref, logoutSession } from "../utils/auth";
import { getBootUser } from "../utils/session";
import { setTheme, getStoredThemePreference } from "../utils/useTheme";
import LucideLogOut from "~icons/lucide/log-out";
import LucideMoon from "~icons/lucide/moon";
import LucideSun from "~icons/lucide/sun";

const isCollapsed = inject("isSidebarCollapsed", false);
const brandLogoSrc = `${import.meta.env.BASE_URL}vvsdtz_logo.png`.replace(/\/{2,}/g, "/");

const displayName = computed(() => {
	const u = getBootUser();
	if (!u) return "Signed in";
	return u.full_name?.trim() || u.name;
});

const userImageSrc = computed(() => getBootUser()?.user_image?.trim() || "");
const headerImageSrc = computed(() => userImageSrc.value || brandLogoSrc);

const dropdownItems = computed(() => [
	{
		label: "Toggle theme",
		icon: markRaw(getStoredThemePreference() === "dark" ? LucideSun : LucideMoon),
		onClick: () => {
			const cur = getStoredThemePreference();
			setTheme(cur === "dark" ? "light" : "dark");
		},
	},
	{
		label: "Log out",
		icon: markRaw(LucideLogOut),
		onClick: async () => {
			await logoutSession();
			window.location.assign(loginPageHref());
		},
	},
]);
</script>
