<template>
	<div class="p-6">
		<div class="mb-6 flex flex-wrap items-end justify-between gap-4">
			<div>
				<h1 class="text-2xl font-semibold text-ink-gray-8">Excel Importer</h1>
				<p class="mt-1 text-sm text-ink-gray-5">MKT Statement / Mukechi imports with live progress</p>
			</div>
			<button
				type="button"
				class="rounded-lg bg-ink-gray-9 px-4 py-2 text-sm font-medium text-white"
				@click="$router.push('/excel-importer/new')"
			>
				New Import
			</button>
		</div>

		<div v-if="error" class="mb-4 rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-800">
			{{ error }}
		</div>

		<div class="overflow-hidden rounded-xl border border-outline-gray-2">
			<table class="w-full text-left text-sm">
				<thead class="bg-surface-gray-2 text-xs uppercase tracking-wide text-ink-gray-5">
					<tr>
						<th class="px-4 py-3 font-medium">Name</th>
						<th class="px-4 py-3 font-medium">Type</th>
						<th class="px-4 py-3 font-medium">Warehouse</th>
						<th class="px-4 py-3 font-medium">Status</th>
						<th class="px-4 py-3 font-medium">Progress</th>
					</tr>
				</thead>
				<tbody class="divide-y divide-outline-gray-2">
					<tr v-if="loading">
						<td colspan="5" class="px-4 py-8 text-center text-ink-gray-5">Loading…</td>
					</tr>
					<tr v-else-if="!rows.length">
						<td colspan="5" class="px-4 py-8 text-center text-ink-gray-5">No importers</td>
					</tr>
					<tr
						v-for="row in rows"
						:key="String(row.name)"
						class="cursor-pointer hover:bg-surface-gray-2"
						@click="$router.push(`/excel-importer/${encodeURIComponent(String(row.name))}`)"
					>
						<td class="px-4 py-3 font-medium text-ink-gray-8">{{ row.name }}</td>
						<td class="px-4 py-3 text-ink-gray-6">{{ row.import_type || "—" }}</td>
						<td class="px-4 py-3 text-ink-gray-6">{{ row.warehouse || "—" }}</td>
						<td class="px-4 py-3 text-ink-gray-6">{{ row.import_status || "—" }}</td>
						<td class="px-4 py-3 text-ink-gray-6">
							{{ row.processed_invoices || 0 }}/{{ row.total_invoices || 0 }} inv ·
							{{ row.processed_cars || 0 }}/{{ row.total_cars || 0 }} cars
						</td>
					</tr>
				</tbody>
			</table>
		</div>
	</div>
</template>

<script setup lang="ts">
import { onMounted, ref } from "vue";
import { apiListImporters, useJanCall } from "../utils/janApi";

const call = useJanCall();
const rows = ref<Array<Record<string, unknown>>>([]);
const loading = ref(true);
const error = ref("");

onMounted(async () => {
	try {
		const res = await apiListImporters(call, { limit: 50 });
		rows.value = res.importers || [];
	} catch (e: unknown) {
		error.value = e instanceof Error ? e.message : String(e);
	} finally {
		loading.value = false;
	}
});
</script>
