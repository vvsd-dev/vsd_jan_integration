<template>
	<div class="login-page-shell flex min-h-screen w-full flex-col items-center justify-center px-4 py-12">
		<div
			class="w-full max-w-[420px] overflow-hidden rounded-2xl border border-outline-gray-2 bg-surface-white shadow-[0_1px_2px_rgba(15,23,42,0.04),0_12px_40px_-12px_rgba(15,23,42,0.12)] ring-1 ring-black/[0.03] dark:border-zinc-700/80"
		>
			<div class="h-1 bg-gradient-to-r from-ink-gray-8 via-ink-gray-6 to-ink-gray-8" aria-hidden="true" />
			<div class="px-8 pb-9 pt-8 sm:px-10 sm:pb-10 sm:pt-9">
				<div class="text-center">
					<h1 class="text-[1.35rem] font-semibold tracking-tight text-ink-gray-8">Jan UI</h1>
					<p class="mt-1 text-sm text-ink-gray-5">Vehicles · Costing · Import Files</p>
				</div>

				<form class="mt-9 space-y-5" @submit.prevent="submit">
					<FormControl v-model="usr" label="Email / username" type="text" autocomplete="username" />
					<FormControl
						v-model="pwd"
						label="Password"
						type="password"
						autocomplete="current-password"
					/>
					<div
						v-if="error"
						class="rounded-lg border border-red-200/90 bg-red-50 px-3 py-2.5 text-sm text-red-800 dark:border-red-500/35 dark:bg-red-950/40 dark:text-red-200"
					>
						{{ error }}
					</div>
					<Button type="submit" variant="solid" class="w-full !bg-black !text-white" :loading="loading">
						Sign in
					</Button>
				</form>
			</div>
		</div>
	</div>
</template>

<script setup lang="ts">
import { ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import { Button, FormControl } from "frappe-ui";
import { completeLoginNavigation, loginWithPassword } from "../utils/auth";

const route = useRoute();
const router = useRouter();
const usr = ref("");
const pwd = ref("");
const loading = ref(false);
const error = ref("");

function redirectParam(): string | undefined {
	const r = route.query.redirect;
	if (typeof r === "string") return r;
	if (Array.isArray(r) && typeof r[0] === "string") return r[0];
	return undefined;
}

async function submit() {
	error.value = "";
	if (!usr.value.trim() || !pwd.value) {
		error.value = "Enter username and password.";
		return;
	}
	loading.value = true;
	try {
		await loginWithPassword(usr.value, pwd.value);
		pwd.value = "";
		await completeLoginNavigation(router, redirectParam());
	} catch (e: unknown) {
		error.value = e instanceof Error ? e.message : String(e);
	} finally {
		loading.value = false;
	}
}
</script>
