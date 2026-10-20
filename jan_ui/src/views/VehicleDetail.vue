<template>
	<div class="p-6">
		<div class="mb-6 flex flex-wrap items-start justify-between gap-4">
			<div>
				<button type="button" class="mb-2 text-sm text-ink-gray-5 hover:text-ink-gray-8" @click="$router.push('/vehicles')">
					← Vehicles
				</button>
				<h1 class="text-2xl font-semibold text-ink-gray-8">
					{{ String(doc.custom_chassis_no || item) }}
				</h1>
				<p class="mt-1 text-sm text-ink-gray-5">
					{{ [doc.custom_maker, doc.custom_model, doc.name].filter(Boolean).join(" · ") }}
				</p>
			</div>
			<div class="flex flex-wrap gap-2">
				<Button variant="subtle" :loading="saving" @click="saveSpecs">Save specs</Button>
				<Button variant="solid" @click="$router.push(`/vehicles/${encodeURIComponent(item)}/costing`)">
					Car Costing
				</Button>
			</div>
		</div>

		<div v-if="error" class="mb-4 rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-800">{{ error }}</div>
		<div v-if="loading" class="py-12 text-center text-ink-gray-5">Loading…</div>

		<template v-else-if="!error">
			<section class="mb-6 rounded-xl border border-outline-gray-2 p-4">
				<h2 class="mb-4 text-sm font-semibold uppercase tracking-wide text-ink-gray-5">Identity</h2>
				<div class="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
					<FormControl v-model="doc.item_code" label="Item Code" :disabled="true" />
					<FormControl v-model="doc.custom_chassis_no" label="Chassis No" />
					<FormControl v-model="doc.custom_new_stock_id" label="Stock ID" />
					<FormControl v-model="doc.custom_maker" label="Maker" />
					<FormControl v-model="doc.custom_model" label="Model" />
					<FormControl v-model="doc.custom_model_code" label="Model Code" />
					<FormControl v-model="doc.custom_bl" label="BL / SW" />
					<FormControl v-model="doc.custom_container_no" label="Container No" />
					<FormControl v-model="doc.custom_price" label="Purchase Price (Yen)" type="number" />
					<FormControl v-model="doc.custom_m3" label="M3" type="number" />
					<FormControl v-model="doc.custom_purchase_date" label="Purchase Date" type="date" />
					<FormControl v-model="doc.custom_purchase_company" label="Purchase Company" />
				</div>
			</section>

			<section class="mb-6 rounded-xl border border-outline-gray-2 p-4">
				<h2 class="mb-4 text-sm font-semibold uppercase tracking-wide text-ink-gray-5">Vehicle specification</h2>
				<div class="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
					<FormControl v-model="doc.custom_exhibition_no" label="Exhibition No" />
					<FormControl v-model="doc.custom_engine_code" label="Engine Code" />
					<FormControl v-model="doc.custom_engine_cc" label="Engine CC" />
					<FormControl v-model="doc.custom_drive_type" label="Drive Type" />
					<FormControl v-model="doc.custom_doors" label="Doors" type="number" />
					<FormControl v-model="doc.custom_seats" label="Seats" type="number" />
					<FormControl v-model="doc.custom_transmission" label="Transmission" />
					<FormControl v-model="doc.custom_fuel_type" label="Fuel Type" />
					<FormControl v-model="doc.custom_steering" label="Steering" />
					<FormControl v-model="doc.custom_mileage" label="Mileage" />
					<FormControl v-model="doc.custom_manufactured_year" label="Manufactured Year" />
					<FormControl v-model="doc.custom_gradeclass" label="Grade / Class" />
					<FormControl v-model="doc.custom_color" label="Color" />
					<FormControl v-model="doc.custom_interior_color" label="Interior Color" />
					<FormControl v-model="doc.custom_auction_company" label="Auction Company" />
					<FormControl v-model="doc.custom_auction_no" label="Auction No" />
					<FormControl v-model="doc.custom_mukechi" label="Mukechi" />
					<FormControl v-model="doc.custom_bid_by" label="Bid By" />
					<FormControl v-model="doc.custom_territory" label="Territory" />
					<FormControl v-model="doc.custom_loaded_docs_status" label="Loaded Docs Status" />
				</div>
			</section>

			<section class="mb-6 rounded-xl border border-outline-gray-2 p-4">
				<h2 class="mb-4 text-sm font-semibold uppercase tracking-wide text-ink-gray-5">Features</h2>
				<div class="grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
					<label
						v-for="f in featureFields"
						:key="f"
						class="flex items-center gap-2 text-sm text-ink-gray-7"
					>
						<input v-model="doc[f]" type="checkbox" class="rounded border-outline-gray-3" :true-value="1" :false-value="0" />
						{{ featureLabel(f) }}
					</label>
				</div>
			</section>

			<section class="rounded-xl border border-outline-gray-2 p-4">
				<div class="mb-4 flex items-center justify-between">
					<h2 class="text-sm font-semibold uppercase tracking-wide text-ink-gray-5">Costing</h2>
					<span v-if="doc.custom_last_car_costing" class="text-xs text-ink-gray-5">
						{{ doc.custom_last_car_costing }}
					</span>
				</div>
				<div class="mb-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
					<div v-for="k in costingSummaryKeys" :key="k" class="rounded-lg bg-surface-gray-2 p-3">
						<div class="text-xs text-ink-gray-5">{{ summaryLabel(k) }}</div>
						<div class="mt-1 text-lg font-semibold tabular-nums text-ink-gray-8">
							{{ formatNum(doc[k] as number) }}
						</div>
					</div>
				</div>
				<div class="grid gap-4 lg:grid-cols-2">
					<div>
						<h3 class="mb-2 text-xs font-semibold uppercase text-ink-gray-5">Tanzania lines</h3>
						<CostingLinesTable :rows="(doc.custom_tz_costing as any[]) || []" />
					</div>
					<div>
						<h3 class="mb-2 text-xs font-semibold uppercase text-ink-gray-5">Japan lines</h3>
						<CostingLinesTable :rows="(doc.custom_japan_costing as any[]) || []" />
					</div>
				</div>
			</section>
		</template>
	</div>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from "vue";
import { Button, FormControl, toast } from "frappe-ui";
import { apiGetVehicle, apiUpdateVehicleSpecs, useJanCall } from "../utils/janApi";
import CostingLinesTable from "../components/CostingLinesTable.vue";
import { formatNumber } from "../utils/format";

const props = defineProps<{ item: string }>();
const call = useJanCall();
const loading = ref(true);
const saving = ref(false);
const error = ref("");
const doc = reactive<Record<string, unknown>>({});

const featureFields = [
	"custom_power_steering",
	"custom_amfm_radio",
	"custom_ac",
	"custom_rear_spoiler",
	"custom_air_bag",
	"custom_fog_light",
	"custom_power_window",
	"custom_navigation",
	"custom_tv",
	"custom_push_start",
	"custom_abs",
	"custom_power_mirror",
	"custom_spare_tyre",
	"custom_key_start",
	"custom_alloy_wheel",
	"custom_sunroof",
];

const costingSummaryKeys = [
	"custom_exchange_rate",
	"custom_total_expected_expense",
	"custom_total_actual_expense",
	"custom_cost",
	"custom_selling_price",
	"custom_profit_usd",
];

function featureLabel(f: string) {
	return f.replace(/^custom_/, "").replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

function summaryLabel(k: string) {
	const map: Record<string, string> = {
		custom_exchange_rate: "FX (TZS/USD)",
		custom_total_expected_expense: "Expected",
		custom_total_actual_expense: "Actual",
		custom_cost: "Cost (TSH)",
		custom_selling_price: "Selling (TSH)",
		custom_profit_usd: "Profit (USD)",
	};
	return map[k] || k;
}

function formatNum(n?: number) {
	if (n == null || Number.isNaN(Number(n))) return "—";
	return formatNumber(n, "Currency");
}

async function load() {
	loading.value = true;
	error.value = "";
	try {
		const data = await apiGetVehicle(call, props.item);
		Object.keys(doc).forEach((k) => delete doc[k]);
		Object.assign(doc, data);
	} catch (e: unknown) {
		error.value = e instanceof Error ? e.message : String(e);
	} finally {
		loading.value = false;
	}
}

async function saveSpecs() {
	saving.value = true;
	error.value = "";
	try {
		const updated = await apiUpdateVehicleSpecs(call, props.item, { ...doc });
		Object.assign(doc, updated);
		toast.success("Vehicle specs saved");
	} catch (e: unknown) {
		error.value = e instanceof Error ? e.message : String(e);
	} finally {
		saving.value = false;
	}
}

onMounted(() => void load());
</script>
