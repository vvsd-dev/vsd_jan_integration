<template>
	<div class="p-6">
		<div class="mb-6 flex flex-wrap items-start justify-between gap-4">
			<div>
				<button
					v-if="doc.import_file"
					type="button"
					class="mb-2 text-sm text-ink-gray-5 hover:text-ink-gray-8"
					@click="$router.push(`/import-files/${encodeURIComponent(String(doc.import_file))}`)"
				>
					← Import File
				</button>
				<h1 class="text-2xl font-semibold text-ink-gray-8">{{ name }}</h1>
				<p class="mt-1 text-sm text-ink-gray-5">
					{{ doc.import_file || "—" }} ·
					{{ doc.docstatus === 1 ? "Submitted" : doc.docstatus === 2 ? "Cancelled" : "Draft" }}
				</p>
			</div>
			<Button v-if="doc.docstatus === 0" variant="subtle" :loading="busy" @click="reload">
				Reload from Import File
			</Button>
		</div>

		<div v-if="error" class="mb-4 rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-800">{{ error }}</div>
		<div v-if="loading" class="py-12 text-center text-ink-gray-5">Loading…</div>

		<template v-else>
			<section class="mb-6 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
				<div class="rounded-xl border border-outline-gray-2 p-4">
					<div class="text-xs text-ink-gray-5">Vehicles</div>
					<div class="mt-1 text-2xl font-semibold">{{ (doc.vehicles as any[])?.length || 0 }}</div>
				</div>
				<div class="rounded-xl border border-outline-gray-2 p-4">
					<div class="text-xs text-ink-gray-5">Expenses</div>
					<div class="mt-1 text-2xl font-semibold">{{ (doc.expenses as any[])?.length || 0 }}</div>
				</div>
				<div class="rounded-xl border border-outline-gray-2 p-4">
					<div class="text-xs text-ink-gray-5">Total expense</div>
					<div class="mt-1 text-lg font-semibold tabular-nums">{{ fmt(doc.total_expense_amount) }}</div>
				</div>
				<div class="rounded-xl border border-outline-gray-2 p-4">
					<div class="text-xs text-ink-gray-5">Total allocated</div>
					<div class="mt-1 text-lg font-semibold tabular-nums">{{ fmt(doc.total_allocated_amount) }}</div>
				</div>
			</section>

			<section class="mb-6 rounded-xl border border-outline-gray-2 p-4">
				<h2 class="mb-3 text-sm font-semibold uppercase text-ink-gray-5">Expenses</h2>
				<div class="overflow-auto">
					<table class="w-full text-left text-xs">
						<thead class="bg-surface-gray-2 text-ink-gray-5">
							<tr>
								<th class="px-3 py-2">Head</th>
								<th class="px-3 py-2">Account</th>
								<th class="px-3 py-2">Currency</th>
								<th class="px-3 py-2 text-right">Amount</th>
								<th class="px-3 py-2">Method</th>
							</tr>
						</thead>
						<tbody class="divide-y divide-outline-gray-2">
							<tr v-for="(e, i) in (doc.expenses as any[]) || []" :key="i">
								<td class="px-3 py-2">{{ e.costing_head || e.costing_code || "—" }}</td>
								<td class="px-3 py-2 text-ink-gray-6">{{ e.expense_account || "—" }}</td>
								<td class="px-3 py-2">{{ e.currency || "—" }}</td>
								<td class="px-3 py-2 text-right tabular-nums">{{ fmt(e.amount) }}</td>
								<td class="px-3 py-2 text-ink-gray-6">{{ e.distribution_method || "—" }}</td>
							</tr>
						</tbody>
					</table>
				</div>
			</section>

			<ViewByVehiclePanel
				:ifcv-name="name"
				:vehicles="(doc.vehicles as any[]) || []"
			/>
		</template>
	</div>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from "vue";
import { Button, toast } from "frappe-ui";
import { apiGetIfcv, apiReloadIfcv, useJanCall } from "../utils/janApi";
import ViewByVehiclePanel from "../components/ViewByVehiclePanel.vue";
import { formatNumber } from "../utils/format";
const props = defineProps<{ name: string }>();
const call = useJanCall();
const loading = ref(true);
const busy = ref(false);
const error = ref("");
const doc = reactive<Record<string, unknown>>({});

function fmt(n: unknown) {
	if (n == null || n === "") return "—";
	return formatNumber(n, "Currency");
}

async function load() {
	loading.value = true;
	error.value = "";
	try {
		const data = await apiGetIfcv(call, props.name);
		Object.keys(doc).forEach((k) => delete doc[k]);
		Object.assign(doc, data);
	} catch (e: unknown) {
		error.value = e instanceof Error ? e.message : String(e);
	} finally {
		loading.value = false;
	}
}

async function reload() {
	busy.value = true;
	try {
		await apiReloadIfcv(call, props.name);
		await load();
		toast.success("Reloaded from Import File");
	} catch (e: unknown) {
		error.value = e instanceof Error ? e.message : String(e);
	} finally {
		busy.value = false;
	}
}

onMounted(() => void load());
</script>
