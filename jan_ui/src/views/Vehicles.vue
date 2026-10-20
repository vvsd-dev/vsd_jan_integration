<template>
	<div class="p-6">
		<div class="mb-6 flex flex-wrap items-end justify-between gap-4">
			<div>
				<h1 class="text-2xl font-semibold text-ink-gray-8">Vehicles</h1>
				<p class="mt-1 text-sm text-ink-gray-5">Search by chassis, stock ID, maker, or BL</p>
			</div>
			<div class="w-full max-w-sm">
				<FormControl v-model="search" type="text" placeholder="Search…" @update:model-value="onSearch" />
			</div>
		</div>

		<div v-if="error" class="mb-4 rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-800">
			{{ error }}
		</div>

		<div class="overflow-hidden rounded-xl border border-outline-gray-2">
			<table class="w-full text-left text-sm">
				<thead class="bg-surface-gray-2 text-xs uppercase tracking-wide text-ink-gray-5">
					<tr>
						<th class="px-4 py-3 font-medium">Chassis</th>
						<th class="px-4 py-3 font-medium">Maker / Model</th>
						<th class="px-4 py-3 font-medium">Stock ID</th>
						<th class="px-4 py-3 font-medium">BL</th>
						<th class="px-4 py-3 font-medium text-right">Cost (TSH)</th>
					</tr>
				</thead>
				<tbody class="divide-y divide-outline-gray-2">
					<tr v-if="loading">
						<td colspan="5" class="px-4 py-8 text-center text-ink-gray-5">Loading…</td>
					</tr>
					<tr v-else-if="!rows.length">
						<td colspan="5" class="px-4 py-8 text-center text-ink-gray-5">No vehicles found</td>
					</tr>
					<tr
						v-for="row in rows"
						:key="row.name"
						class="cursor-pointer hover:bg-surface-gray-2"
						@click="$router.push(`/vehicles/${encodeURIComponent(row.name)}`)"
					>
						<td class="px-4 py-3 font-medium text-ink-gray-8">{{ row.custom_chassis_no || row.name }}</td>
						<td class="px-4 py-3 text-ink-gray-7">
							{{ [row.custom_maker, row.custom_model].filter(Boolean).join(" · ") || "—" }}
						</td>
						<td class="px-4 py-3 text-ink-gray-6">{{ row.custom_new_stock_id || "—" }}</td>
						<td class="px-4 py-3 text-ink-gray-6">{{ row.custom_bl || "—" }}</td>
						<td class="px-4 py-3 text-right tabular-nums text-ink-gray-8">
							{{ formatNum(row.custom_cost) }}
						</td>
					</tr>
				</tbody>
			</table>
		</div>
		<p class="mt-3 text-xs text-ink-gray-5">{{ total }} vehicle(s)</p>
	</div>
</template>

<script setup lang="ts">
import { onMounted, ref } from "vue";
import { FormControl } from "frappe-ui";
import { apiListVehicles, type VehicleRow, useJanCall } from "../utils/janApi";
import { formatNumber } from "../utils/format";

const call = useJanCall();
const search = ref("");
const rows = ref<VehicleRow[]>([]);
const total = ref(0);
const loading = ref(true);
const error = ref("");
let timer: ReturnType<typeof setTimeout> | null = null;

function formatNum(n?: number) {
	if (n == null || Number.isNaN(Number(n))) return "—";
	return formatNumber(n, "Currency");
}

async function load() {
	loading.value = true;
	error.value = "";
	try {
		const res = await apiListVehicles(call, { search: search.value, limit: 50, start: 0 });
		rows.value = res.vehicles || [];
		total.value = res.total || 0;
	} catch (e: unknown) {
		error.value = e instanceof Error ? e.message : String(e);
	} finally {
		loading.value = false;
	}
}

function onSearch() {
	if (timer) clearTimeout(timer);
	timer = setTimeout(() => void load(), 300);
}

onMounted(() => void load());
</script>
