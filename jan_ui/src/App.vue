<template>
	<FrappeUIProvider>
		<div
			v-if="isLoginRoute"
			class="min-h-screen w-full overflow-y-auto bg-gradient-to-b from-surface-gray-2 via-surface-gray-2 to-surface-gray-3 dark:from-zinc-950 dark:via-zinc-900 dark:to-zinc-950"
		>
			<router-view />
		</div>
		<div v-else class="flex h-screen w-full">
			<AppSidebar class="flex-shrink-0" />
			<div class="min-w-0 flex-1 overflow-y-auto bg-surface-white">
				<router-view />
			</div>
		</div>
	</FrappeUIProvider>
</template>

<script setup lang="ts">
import { computed, onMounted } from "vue";
import { useRoute } from "vue-router";
import { FrappeUIProvider } from "frappe-ui";
import AppSidebar from "./components/AppSidebar.vue";
import { useTheme } from "./utils/useTheme";

const route = useRoute();
const isLoginRoute = computed(() => route.name === "Login");
const { initTheme } = useTheme();

onMounted(() => {
	initTheme();
});
</script>
