<template>
	<div class="p-6">
		<div class="mb-6 flex items-start justify-between gap-4">
			<div>
				<h1 class="text-2xl font-semibold text-ink-gray-8">Dashboard</h1>
				<p class="mt-1 text-sm text-ink-gray-5">Vehicle and costing overview</p>
			</div>
		</div>

		<div v-if="error" class="mb-4 rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-800">
			{{ error }}
		</div>

		<div class="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
			<div
				v-for="card in cards"
				:key="card.label"
				class="rounded-xl border border-outline-gray-2 bg-surface-white p-4"
			>
				<div class="text-xs uppercase tracking-wide text-ink-gray-5">{{ card.label }}</div>
				<div class="mt-2 text-2xl font-semibold tabular-nums text-ink-gray-8">
					{{ loading ? "…" : card.value }}
				</div>
			</div>
		</div>

		<div class="mt-8 rounded-xl border border-outline-gray-2">
			<div class="border-b border-outline-gray-2 px-4 py-3">
				<h2 class="text-sm font-semibold text-ink-gray-8">Recent Import Files</h2>
			</div>
			<ul v-if="stats?.recent_import_files?.length" class="divide-y divide-outline-gray-2">
				<li v-for="row in stats.recent_import_files" :key="String(row.name)">
					<router-link
						:to="`/import-files/${encodeURIComponent(String(row.name))}`"
						class="flex items-center justify-between px-4 py-3 hover:bg-surface-gray-2"
					>
						<span class="font-medium text-ink-gray-8">{{ row.name }}</span>
						<span class="text-xs text-ink-gray-5">{{ row.bl_number || "—" }}</span>
					</router-link>
				</li>
			</ul>
			<div v-else class="px-4 py-8 text-center text-sm text-ink-gray-5">
				{{ loading ? "Loading…" : "No import files yet" }}
			</div>
		</div>
	</div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { apiDashboard, type DashboardStats, useJanCall } from "../utils/janApi";

const call = useJanCall();
const loading = ref(true);
const error = ref("");
const stats = ref<DashboardStats | null>(null);

const cards = computed(() => [
	{ label: "Vehicles", value: stats.value?.vehicles ?? 0 },
	{ label: "Import Files", value: stats.value?.import_files ?? 0 },
	{ label: "Open Import File Cost Vouchers", value: stats.value?.open_ifcvs ?? 0 },
	{ label: "Submitted Import File Cost Vouchers", value: stats.value?.submitted_ifcvs ?? 0 },
]);

onMounted(async () => {
	try {
		stats.value = await apiDashboard(call);
	} catch (e: unknown) {
		error.value = e instanceof Error ? e.message : String(e);
	} finally {
		loading.value = false;
	}
});
</script>
