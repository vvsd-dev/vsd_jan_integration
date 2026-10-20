<template>
	<section class="rounded-xl border border-outline-gray-2 p-4">
		<div class="mb-4 flex flex-wrap items-end justify-between gap-3">
			<div>
				<h2 class="text-sm font-semibold uppercase tracking-wide text-ink-gray-5">View by Vehicle</h2>
				<p class="mt-1 text-xs text-ink-gray-5">Per-car allocation ledger (TZS · USD · Yen)</p>
			</div>
			<select
				v-model="selected"
				class="rounded-md border border-outline-gray-2 bg-surface-white px-3 py-2 text-sm"
				@change="loadLedger"
			>
				<option disabled value="">Select vehicle…</option>
				<option v-for="v in vehicles" :key="v.item" :value="v.item">
					{{ label(v) }}
				</option>
			</select>
		</div>

		<div v-if="ledgerError" class="mb-3 text-sm text-red-700">{{ ledgerError }}</div>
		<div v-if="ledgerLoading" class="py-6 text-center text-sm text-ink-gray-5">Loading ledger…</div>

		<template v-else-if="ledger">
			<div class="mb-4 grid gap-3 sm:grid-cols-3">
				<div class="rounded-lg bg-surface-gray-2 p-3">
					<div class="text-xs text-ink-gray-5">{{ ledger.company_currency || "TZS" }}</div>
					<div class="text-lg font-semibold tabular-nums">{{ fmt(ledger.company_total) }}</div>
				</div>
				<div class="rounded-lg bg-surface-gray-2 p-3">
					<div class="text-xs text-ink-gray-5">{{ ledger.usd_currency || "USD" }}</div>
					<div class="text-lg font-semibold tabular-nums">{{ fmt(ledger.usd_total) }}</div>
				</div>
				<div class="rounded-lg bg-surface-gray-2 p-3">
					<div class="text-xs text-ink-gray-5">{{ ledger.jpy_currency || "JPY" }}</div>
					<div class="text-lg font-semibold tabular-nums">{{ fmt(ledger.yen_total) }}</div>
				</div>
			</div>

			<div class="overflow-auto rounded-lg border border-outline-gray-2">
				<table class="w-full text-left text-xs">
					<thead class="bg-surface-gray-2 text-ink-gray-5">
						<tr>
							<th class="px-3 py-2">Costing</th>
							<th class="px-3 py-2">Account</th>
							<th class="px-3 py-2">Method</th>
							<th class="px-3 py-2">Currency</th>
							<th class="px-3 py-2 text-right">Amount</th>
						</tr>
					</thead>
					<tbody class="divide-y divide-outline-gray-2">
						<tr v-for="(r, i) in ledger.rows || []" :key="i">
							<td class="px-3 py-2">{{ r.costing || r.code || "—" }}</td>
							<td class="px-3 py-2 text-ink-gray-6">{{ r.account || "—" }}</td>
							<td class="px-3 py-2">{{ r.method || "—" }}</td>
							<td class="px-3 py-2">{{ r.currency || "—" }}</td>
							<td class="px-3 py-2 text-right tabular-nums">{{ fmt(r.amount) }}</td>
						</tr>
						<tr v-if="!(ledger.rows || []).length">
							<td colspan="5" class="px-3 py-6 text-center text-ink-gray-5">No allocations for this vehicle</td>
						</tr>
					</tbody>
				</table>
			</div>
		</template>
	</section>
</template>

<script setup lang="ts">
import { onMounted, ref, watch } from "vue";
import { apiGetVehicleLedger, useJanCall } from "../utils/janApi";
import { formatNumber } from "../utils/format";

const props = defineProps<{
	ifcvName: string;
	vehicles: Array<Record<string, any>>;
}>();

const call = useJanCall();
const selected = ref("");
const ledger = ref<Record<string, any> | null>(null);
const ledgerLoading = ref(false);
const ledgerError = ref("");

function label(v: Record<string, any>) {
	const chassis = v.chassis_no || "No chassis";
	const maker = v.maker ? ` · ${v.maker}` : "";
	const stock = v.stock_id || v.custom_new_stock_id ? ` · ${v.stock_id || v.custom_new_stock_id}` : "";
	return `${chassis}${maker}${stock}`;
}

function fmt(n: unknown) {
	if (n == null || n === "") return "—";
	return formatNumber(n, "Currency");
}

async function loadLedger() {
	if (!selected.value) return;
	ledgerLoading.value = true;
	ledgerError.value = "";
	try {
		ledger.value = await apiGetVehicleLedger(call, props.ifcvName, selected.value);
	} catch (e: unknown) {
		ledgerError.value = e instanceof Error ? e.message : String(e);
		ledger.value = null;
	} finally {
		ledgerLoading.value = false;
	}
}

onMounted(() => {
	if (props.vehicles?.length) {
		selected.value = props.vehicles[0].item;
		void loadLedger();
	}
});

watch(
	() => props.vehicles,
	(v) => {
		if (v?.length && !selected.value) {
			selected.value = v[0].item;
			void loadLedger();
		}
	},
);
</script>
