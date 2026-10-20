<template>
	<div class="p-6">
		<div class="mb-6 flex flex-wrap items-end justify-between gap-4">
			<div>
				<h1 class="text-2xl font-semibold text-ink-gray-8">Reports</h1>
				<p class="mt-1 text-sm text-ink-gray-5">
					Stock Ledger Entry &amp; GL Entry reports, plus Jan BL Costing / Sale Report
				</p>
			</div>
			<div class="w-full max-w-sm">
				<FormControl v-model="search" type="text" placeholder="Search reports…" @update:model-value="onSearch" />
			</div>
		</div>

		<div v-if="error" class="mb-4 rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-800">
			{{ error }}
		</div>

		<div class="overflow-hidden rounded-xl border border-outline-gray-2">
			<table class="w-full text-left text-sm">
				<thead class="bg-surface-gray-2 text-xs uppercase tracking-wide text-ink-gray-5">
					<tr>
						<th class="px-4 py-3 font-medium">Report</th>
						<th class="px-4 py-3 font-medium">Ref DocType</th>
						<th class="px-4 py-3 font-medium">Type</th>
					</tr>
				</thead>
				<tbody class="divide-y divide-outline-gray-2">
					<tr v-if="loading">
						<td colspan="3" class="px-4 py-8 text-center text-ink-gray-5">Loading…</td>
					</tr>
					<tr v-else-if="!rows.length">
						<td colspan="3" class="px-4 py-8 text-center text-ink-gray-5">No reports</td>
					</tr>
					<tr
						v-for="row in rows"
						:key="String(row.name)"
						class="cursor-pointer hover:bg-surface-gray-2"
						@click="openReport(row)"
					>
						<td class="px-4 py-3 font-medium text-ink-gray-8">
							{{ row.report_name || row.name }}
						</td>
						<td class="px-4 py-3 text-ink-gray-6">{{ row.ref_doctype || "—" }}</td>
						<td class="px-4 py-3 text-ink-gray-6">{{ row.report_type || "—" }}</td>
					</tr>
				</tbody>
			</table>
		</div>
		<p class="mt-3 text-xs text-ink-gray-5">{{ total }} report(s)</p>
	</div>
</template>

<script setup lang="ts">
import { onMounted, ref } from "vue";
import { useRouter } from "vue-router";
import { FormControl } from "frappe-ui";
import { apiListReports, useJanCall } from "../utils/janApi";

const call = useJanCall();
const router = useRouter();
const search = ref("");
const rows = ref<Array<Record<string, unknown>>>([]);
const total = ref(0);
const loading = ref(true);
const error = ref("");
let timer: ReturnType<typeof setTimeout> | null = null;

function openReport(row: Record<string, unknown>) {
	const name = String(row.name || "");
	if (name === "Jan BL Costing") {
		router.push("/reports/jan-bl-costing");
		return;
	}
	if (name === "Jan Sale Report") {
		router.push("/reports/jan-sale-report");
		return;
	}
	if (row.jan_custom && row.route) {
		router.push(String(row.route));
		return;
	}
	router.push(`/reports/run/${encodeURIComponent(name)}`);
}

async function load() {
	loading.value = true;
	error.value = "";
	try {
		const res = await apiListReports(call, { search: search.value, limit: 100, start: 0 });
		rows.value = res.reports || [];
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
