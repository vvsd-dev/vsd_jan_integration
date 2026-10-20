<template>
	<div class="p-6">
		<div class="mb-6 flex flex-wrap items-end justify-between gap-4">
			<div>
				<h1 class="text-2xl font-semibold text-ink-gray-8">Import Files</h1>
				<p class="mt-1 text-sm text-ink-gray-5">BL / supplier invoice files and linked Import File Cost Vouchers</p>
			</div>
			<div class="w-full max-w-sm">
				<FormControl v-model="search" type="text" placeholder="Search…" @update:model-value="onSearch" />
			</div>
		</div>

		<div v-if="error" class="mb-4 rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-800">{{ error }}</div>

		<div class="overflow-hidden rounded-xl border border-outline-gray-2">
			<table class="w-full text-left text-sm">
				<thead class="bg-surface-gray-2 text-xs uppercase tracking-wide text-ink-gray-5">
					<tr>
						<th class="px-4 py-3 font-medium">Name</th>
						<th class="px-4 py-3 font-medium">BL</th>
						<th class="px-4 py-3 font-medium">Supplier Invoice</th>
						<th class="px-4 py-3 font-medium">Status</th>
					</tr>
				</thead>
				<tbody class="divide-y divide-outline-gray-2">
					<tr v-if="loading">
						<td colspan="4" class="px-4 py-8 text-center text-ink-gray-5">Loading…</td>
					</tr>
					<tr v-else-if="!rows.length">
						<td colspan="4" class="px-4 py-8 text-center text-ink-gray-5">No import files</td>
					</tr>
					<tr
						v-for="row in rows"
						:key="String(row.name)"
						class="cursor-pointer hover:bg-surface-gray-2"
						@click="$router.push(`/import-files/${encodeURIComponent(String(row.name))}`)"
					>
						<td class="px-4 py-3 font-medium text-ink-gray-8">{{ row.name }}</td>
						<td class="px-4 py-3 text-ink-gray-6">{{ row.bl_number || "—" }}</td>
						<td class="px-4 py-3 text-ink-gray-6">{{ row.supplier_invoice_no || "—" }}</td>
						<td class="px-4 py-3 text-ink-gray-6">{{ statusLabel(row) }}</td>
					</tr>
				</tbody>
			</table>
		</div>
		<p class="mt-3 text-xs text-ink-gray-5">{{ total }} file(s)</p>
	</div>
</template>

<script setup lang="ts">
import { onMounted, ref } from "vue";
import { FormControl } from "frappe-ui";
import { apiListImportFiles, useJanCall } from "../utils/janApi";

const call = useJanCall();
const search = ref("");
const rows = ref<Record<string, unknown>[]>([]);
const total = ref(0);
const loading = ref(true);
const error = ref("");
let timer: ReturnType<typeof setTimeout> | null = null;

function statusLabel(row: Record<string, unknown>) {
	const ds = Number(row.docstatus);
	if (ds === 1) return "Submitted";
	if (ds === 2) return "Cancelled";
	return "Draft";
}

async function load() {
	loading.value = true;
	error.value = "";
	try {
		const res = await apiListImportFiles(call, { search: search.value, limit: 50, start: 0 });
		rows.value = res.import_files || [];
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
