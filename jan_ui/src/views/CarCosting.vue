<template>
	<div class="p-6">
		<div class="mb-6 flex flex-wrap items-start justify-between gap-4">
			<div>
				<button
					type="button"
					class="mb-2 text-sm text-ink-gray-5 hover:text-ink-gray-8"
					@click="$router.push(`/vehicles/${encodeURIComponent(item)}`)"
				>
					← Vehicle
				</button>
				<div class="flex flex-wrap items-center gap-2">
					<h1 class="text-2xl font-semibold text-ink-gray-8">Car Costing</h1>
					<span
						v-if="isDirty"
						class="inline-flex items-center rounded-full bg-orange-100 px-2.5 py-0.5 text-xs font-semibold text-orange-800"
					>
						Not Saved
					</span>
				</div>
				<p class="mt-1 text-sm text-ink-gray-5">
					{{ doc.name || "…" }} · {{ doc.chassis_no || item }}
					<span v-if="isDirty" class="text-orange-700"> · Unsaved edits</span>
				</p>
			</div>
			<div class="flex flex-wrap gap-2">
				<Button variant="subtle" :loading="busy" @click="refreshFromDb">Refresh</Button>
				<Button variant="subtle" :loading="busy" @click="fetchFx">Fetch FX</Button>
				<Button variant="subtle" :loading="busy" @click="reloadFromItem">Load from Item</Button>
				<Button variant="subtle" :loading="busy" @click="doRecalc">Recalculate</Button>
				<Button variant="solid" :loading="busy" :disabled="!isDirty" @click="save">Save</Button>
			</div>
		</div>

		<div v-if="error" class="mb-4 rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-800">{{ error }}</div>
		<div v-if="loading" class="py-12 text-center text-ink-gray-5">Loading…</div>

		<template v-else-if="!error">
			<section class="mb-6 grid gap-3 rounded-xl border border-outline-gray-2 p-4 sm:grid-cols-2 lg:grid-cols-4">
				<FormControl v-model="doc.costing_date" label="Costing Date" type="date" />
				<FormControl v-model="doc.exchange_rate" label="TZS / USD" type="number" />
				<FormControl v-model="doc.yen_exchange_rate" label="JPY / USD" type="number" />
				<FormControl v-model="doc.m3" label="M3" type="number" />
				<FormControl v-model="doc.yen" label="Yen (purchase)" type="number" />
				<FormControl
					v-model="doc.expected_selling_price"
					label="Expected Selling Price (TZS)"
					type="number"
				/>
				<FormControl v-model="doc.import_file" label="Import File" />
				<div class="rounded-lg bg-surface-gray-2 p-3">
					<div class="text-xs text-ink-gray-5">Cost (TSH)</div>
					<div class="text-lg font-semibold tabular-nums">{{ fmt(doc.cost) }}</div>
				</div>
				<div class="rounded-lg bg-surface-gray-2 p-3">
					<div class="text-xs text-ink-gray-5">Total USD</div>
					<div class="text-lg font-semibold tabular-nums">{{ fmt(doc.total_cost_usd) }}</div>
				</div>
			</section>

			<section class="mb-6 rounded-xl border border-outline-gray-2 p-4">
				<h2 class="mb-3 text-sm font-semibold uppercase text-ink-gray-5">Tanzania expected lines</h2>
				<EditableLinesTable v-model="tzLines" />
			</section>

			<section class="rounded-xl border border-outline-gray-2 p-4">
				<h2 class="mb-3 text-sm font-semibold uppercase text-ink-gray-5">Japan expected lines</h2>
				<EditableLinesTable v-model="jpLines" />
			</section>
		</template>
	</div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from "vue";
import { Button, FormControl, toast } from "frappe-ui";
import {
	apiFetchFx,
	apiGetOrCreateCarCosting,
	apiLoadFromItem,
	apiRecalculateCarCosting,
	apiSaveCarCosting,
	useJanCall,
} from "../utils/janApi";
import EditableLinesTable from "../components/EditableLinesTable.vue";
import { formatNumber } from "../utils/format";

const props = defineProps<{ item: string }>();
const call = useJanCall();
const loading = ref(true);
const busy = ref(false);
const error = ref("");
const doc = reactive<Record<string, any>>({});
const tzLines = ref<Record<string, any>[]>([]);
const jpLines = ref<Record<string, any>[]>([]);
const savedSnapshot = ref("");

function fmt(n: unknown) {
	if (n == null || n === "") return "—";
	return formatNumber(n, "Currency");
}

function currentPayload() {
	return { ...doc, tz_costing_lines: tzLines.value, japan_costing_lines: jpLines.value };
}

function markClean() {
	savedSnapshot.value = JSON.stringify(currentPayload());
}

const isDirty = computed(() => {
	if (loading.value || !savedSnapshot.value) return false;
	return JSON.stringify(currentPayload()) !== savedSnapshot.value;
});

function applyDoc(d: Record<string, any>) {
	Object.keys(doc).forEach((k) => delete doc[k]);
	Object.assign(doc, d);
	tzLines.value = [...(d.tz_costing_lines || [])];
	jpLines.value = [...(d.japan_costing_lines || [])];
	markClean();
}

async function load() {
	loading.value = true;
	error.value = "";
	try {
		const res = await apiGetOrCreateCarCosting(call, props.item);
		applyDoc(res.doc);
	} catch (e: unknown) {
		error.value = e instanceof Error ? e.message : String(e);
	} finally {
		loading.value = false;
	}
}

async function refreshFromDb() {
	if (isDirty.value && !confirm("Discard unsaved changes and reload from the database?")) return;
	await load();
}

async function save() {
	busy.value = true;
	error.value = "";
	try {
		const saved = await apiSaveCarCosting(call, currentPayload());
		applyDoc(saved);
		toast.success("Car Costing saved");
	} catch (e: unknown) {
		error.value = e instanceof Error ? e.message : String(e);
	} finally {
		busy.value = false;
	}
}

async function fetchFx() {
	busy.value = true;
	try {
		const rates = await apiFetchFx(call, String(doc.name), String(doc.costing_date || ""));
		doc.exchange_rate = rates.exchange_rate;
		doc.yen_exchange_rate = rates.yen_exchange_rate;
		toast.success("Exchange rates updated");
	} catch (e: unknown) {
		error.value = e instanceof Error ? e.message : String(e);
	} finally {
		busy.value = false;
	}
}

async function doRecalc() {
	busy.value = true;
	try {
		await save();
		await apiRecalculateCarCosting(call, String(doc.name));
		const refreshed = await apiGetOrCreateCarCosting(call, props.item);
		applyDoc(refreshed.doc);
		toast.success("Recalculated");
	} catch (e: unknown) {
		error.value = e instanceof Error ? e.message : String(e);
	} finally {
		busy.value = false;
	}
}

async function reloadFromItem() {
	busy.value = true;
	try {
		await apiLoadFromItem(call, String(doc.name), props.item);
		await load();
		toast.success("Loaded from Item");
	} catch (e: unknown) {
		error.value = e instanceof Error ? e.message : String(e);
	} finally {
		busy.value = false;
	}
}

onMounted(() => void load());
</script>
