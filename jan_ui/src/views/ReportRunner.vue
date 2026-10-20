<template>
	<div class="p-6">
		<div class="mb-6 flex flex-wrap items-start justify-between gap-4">
			<div>
				<button type="button" class="mb-2 text-sm text-ink-gray-5 hover:text-ink-gray-8" @click="$router.push('/reports')">
					← Reports
				</button>
				<h1 class="text-2xl font-semibold text-ink-gray-8">{{ title }}</h1>
				<p class="mt-1 text-sm text-ink-gray-5">{{ subtitle }}</p>
			</div>
			<div class="flex flex-wrap gap-2">
				<button
					type="button"
					class="rounded-lg border border-outline-gray-2 px-4 py-2 text-sm font-medium text-ink-gray-8"
					:disabled="running"
					@click="refresh"
				>
					{{ running ? "Refreshing…" : "Refresh" }}
				</button>
				<template v-if="isPrepared">
					<button
						type="button"
						class="rounded-lg bg-ink-gray-9 px-4 py-2 text-sm font-medium text-white"
						:disabled="generating"
						@click="generatePrepared"
					>
						{{ generating ? "Queuing…" : "Generate" }}
					</button>
					<button
						type="button"
						class="rounded-lg border border-outline-gray-2 px-4 py-2 text-sm"
						@click="showPreparedList = !showPreparedList"
					>
						Prepared Reports
					</button>
				</template>
			</div>
		</div>

		<section class="mb-4 flex flex-wrap items-end gap-3 rounded-xl border border-outline-gray-2 p-4">
			<div v-for="f in filterDefs" :key="f.fieldname" class="min-w-[140px]">
				<label class="mb-1 block text-xs font-medium text-ink-gray-5">
					{{ f.label }}
					<span v-if="Number(f.reqd)" class="text-red-600">*</span>
				</label>
				<select
					v-if="f.fieldtype === 'Select' || f.fieldtype === 'Check'"
					v-model="filters[f.fieldname]"
					class="w-full rounded-lg border border-outline-gray-2 px-3 py-2 text-sm"
				>
					<option v-if="f.fieldtype === 'Check'" value="">—</option>
					<option v-if="f.fieldtype === 'Check'" value="1">Yes</option>
					<option v-if="f.fieldtype === 'Check'" value="0">No</option>
					<option
						v-for="opt in String(f.options || '')
							.split('\n')
							.filter(Boolean)"
						:key="opt"
						:value="opt"
					>
						{{ opt }}
					</option>
				</select>
				<LinkSelect
					v-else-if="f.fieldtype === 'Link' || f.fieldtype === 'MultiSelectList'"
					v-model="filters[f.fieldname]"
					:doctype="String(f.options || '')"
				/>
				<input
					v-else-if="f.fieldtype === 'Check'"
					v-model="filters[f.fieldname]"
					type="checkbox"
					:true-value="'1'"
					:false-value="'0'"
					class="h-4 w-4"
				/>
				<input
					v-else
					v-model="filters[f.fieldname]"
					:type="f.fieldtype === 'Date' ? 'date' : f.fieldtype === 'Int' || f.fieldtype === 'Float' ? 'number' : 'text'"
					class="w-full rounded-lg border border-outline-gray-2 px-3 py-2 text-sm"
				/>
			</div>
			<button
				type="button"
				class="rounded-lg bg-ink-gray-9 px-4 py-2 text-sm font-medium text-white"
				:disabled="running"
				@click="run"
			>
				{{ running ? "Running…" : isPrepared ? "Show Report" : "Run" }}
			</button>
		</section>

		<div
			v-if="showPreparedList && isPrepared"
			class="mb-4 rounded-xl border border-outline-gray-2 p-3"
		>
			<div class="mb-2 flex items-center justify-between">
				<h3 class="text-sm font-semibold text-ink-gray-8">Recent Prepared Reports</h3>
				<button type="button" class="text-xs text-ink-gray-5" @click="loadPreparedList">Reload</button>
			</div>
			<ul class="divide-y divide-outline-gray-2 text-sm">
				<li v-if="!preparedList.length" class="py-3 text-ink-gray-5">No prepared reports yet — click Generate.</li>
				<li
					v-for="pr in preparedList"
					:key="String(pr.name)"
					class="flex cursor-pointer items-center justify-between py-2 hover:bg-surface-gray-2"
					@click="openPrepared(String(pr.name))"
				>
					<span class="font-medium text-ink-gray-8">{{ pr.name }}</span>
					<span class="text-xs text-ink-gray-5">{{ pr.status }} · {{ pr.creation }}</span>
				</li>
			</ul>
		</div>

		<div v-if="preparedInfo" class="mb-3 text-xs text-ink-gray-5">
			Showing prepared report {{ preparedInfo.name }} ({{ preparedInfo.status }})
		</div>

		<div v-if="error" class="mb-4 rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-800">
			{{ error }}
		</div>

		<div class="overflow-x-auto rounded-xl border border-outline-gray-2">
			<table class="w-full min-w-[900px] text-left text-sm">
				<thead class="bg-surface-gray-2 text-xs uppercase tracking-wide text-ink-gray-5">
					<tr>
						<th v-for="col in columns" :key="colKey(col)" class="whitespace-nowrap px-3 py-2 font-medium">
							{{ col.label || col.fieldname }}
						</th>
					</tr>
				</thead>
				<tbody class="divide-y divide-outline-gray-2">
					<tr v-if="running">
						<td :colspan="Math.max(columns.length, 1)" class="px-4 py-8 text-center text-ink-gray-5">
							Running…
						</td>
					</tr>
					<tr v-else-if="!result.length">
						<td :colspan="Math.max(columns.length, 1)" class="px-4 py-8 text-center text-ink-gray-5">
							No data — set filters and {{ isPrepared ? "Generate / Show Report" : "Run" }}
						</td>
					</tr>
					<tr v-for="(row, idx) in result" :key="idx" class="hover:bg-surface-gray-2">
						<td v-for="col in columns" :key="colKey(col)" class="whitespace-nowrap px-3 py-2 text-ink-gray-7">
							{{ formatCell(row, col) }}
						</td>
					</tr>
				</tbody>
			</table>
		</div>
		<p class="mt-3 text-xs text-ink-gray-5">{{ result.length }} row(s)</p>
	</div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from "vue";
import LinkSelect from "../components/LinkSelect.vue";
import {
	apiGeneratePreparedReport,
	apiGetReportMeta,
	apiListPreparedReports,
	apiRunCostingReport,
	apiRunSaleReport,
	apiRunReport,
	useJanCall,
} from "../utils/janApi";
import { formatCellValue, resolveCurrencyCode } from "../utils/format";

const props = defineProps<{ reportName: string }>();
const call = useJanCall();

const isCosting = computed(
	() => props.reportName === "jan-bl-costing" || props.reportName === "Jan BL Costing",
);
const isSale = computed(
	() => props.reportName === "jan-sale-report" || props.reportName === "Jan Sale Report",
);
const isJanCustom = computed(() => isCosting.value || isSale.value);
const title = ref(
	isCosting.value ? "Jan BL Costing" : isSale.value ? "Jan Sale Report" : props.reportName,
);
const subtitle = ref(
	isCosting.value
		? "NEW COST FILE columns · Currency TZS / YEN / USD with day-rate FX"
		: isSale.value
			? "Sale Report · submitted SI only · Duty=TRA DUTY · Expense=Total EXP · FX like BL Costing"
			: "Query / Script Report",
);

const filterDefs = ref<Array<Record<string, any>>>([]);
const filters = reactive<Record<string, string>>({});
const columns = ref<Array<Record<string, any>>>([]);
const result = ref<Array<Record<string, unknown> | unknown[]>>([]);
const running = ref(false);
const generating = ref(false);
const error = ref("");
const isPrepared = ref(false);
const showPreparedList = ref(false);
const preparedList = ref<Array<Record<string, unknown>>>([]);
const preparedInfo = ref<Record<string, unknown> | null>(null);
const activePreparedName = ref<string | null>(null);
/** After meta+defaults: non-prepared reports re-run on filter change (Desk-like). */
const filtersReady = ref(false);
let filterDebounce: ReturnType<typeof setTimeout> | null = null;

function colKey(col: Record<string, any>) {
	return String(col.fieldname || col.label || "");
}

function cellCurrency(row: Record<string, unknown> | unknown[], col: Record<string, any>): string | null {
	const fromCol = col.currency || (col.options && col.options !== "currency" ? col.options : null);
	if (fromCol && String(fromCol).indexOf(":") === -1) {
		const code = resolveCurrencyCode(String(fromCol));
		if (code) return code;
	}
	if (!Array.isArray(row) && row && typeof row === "object") {
		const fromRow = (row as Record<string, unknown>).currency;
		if (fromRow) return resolveCurrencyCode(String(fromRow));
	}
	if (filters.currency) return resolveCurrencyCode(filters.currency);
	return null;
}

function formatCell(row: Record<string, unknown> | unknown[], col: Record<string, any>) {
	let v: unknown;
	if (Array.isArray(row)) {
		const idx = columns.value.indexOf(col);
		v = row[idx];
	} else {
		v = row[col.fieldname] ?? row[col.label];
	}
	if (v == null || v === "") return "—";
	if (typeof v === "number" || (typeof v === "string" && /^-?\d+(\.\d+)?$/.test(v))) {
		const ft = String(col.fieldtype || (typeof v === "number" && !Number.isInteger(v) ? "Currency" : "Float"));
		const fieldtype = ft === "Data" ? "Currency" : ft;
		const currency = fieldtype === "Currency" ? cellCurrency(row, col) : null;
		return formatCellValue(v, fieldtype, currency);
	}
	return String(v);
}

async function loadMeta() {
	error.value = "";
	try {
		const name = isCosting.value
			? "Jan BL Costing"
			: isSale.value
				? "Jan Sale Report"
				: props.reportName;
		const meta = await apiGetReportMeta(call, name);
		title.value = String(meta.report_name || meta.name || title.value);
		isPrepared.value = !!meta.prepared_report && !isJanCustom.value;
		subtitle.value = isPrepared.value
			? "Prepared Report — Generate in background, then Show Report"
			: isJanCustom.value
				? subtitle.value
				: String(meta.report_type || "Query / Script Report");
		filterDefs.value = (meta.filters as Array<Record<string, any>>) || [];
		if (isJanCustom.value && !filterDefs.value.length) {
			filterDefs.value = [
				{ fieldname: "currency", label: "Currency", fieldtype: "Select", options: "TZS\nYEN\nUSD", default: "TZS" },
				{ fieldname: "import_file", label: "Import File", fieldtype: "Link", options: "Import File" },
				{ fieldname: "from_date", label: "From Date", fieldtype: "Date" },
				{ fieldname: "to_date", label: "To Date", fieldtype: "Date" },
				{ fieldname: "chassis", label: "Chassis", fieldtype: "Data" },
			];
			if (isSale.value) {
				filterDefs.value.push({
					fieldname: "customer",
					label: "Buyer",
					fieldtype: "Link",
					options: "Customer",
				});
			}
		}
		for (const f of filterDefs.value) {
			if (f.default != null && filters[f.fieldname] == null) {
				filters[f.fieldname] = String(f.default);
			} else if (filters[f.fieldname] == null) {
				filters[f.fieldname] = "";
			}
		}
		if (isJanCustom.value && !filters.currency) filters.currency = "TZS";
		if (Array.isArray(meta.columns) && meta.columns.length) {
			columns.value = meta.columns as Array<Record<string, any>>;
		}
	} catch (e: unknown) {
		error.value = e instanceof Error ? e.message : String(e);
	}
}

async function run() {
	running.value = true;
	error.value = "";
	try {
		const payload = { ...filters };
		const res = isCosting.value
			? await apiRunCostingReport(call, payload)
			: isSale.value
				? await apiRunSaleReport(call, payload)
				: await apiRunReport(call, props.reportName, payload, {
						ignore_prepared_report: !isPrepared.value,
						prepared_report_name: activePreparedName.value || undefined,
					});
		columns.value = (res.columns as Array<Record<string, any>>) || columns.value;
		result.value = (res.result as Array<Record<string, unknown>>) || [];
		if (res.doc) {
			preparedInfo.value = res.doc;
		} else if (!isPrepared.value) {
			preparedInfo.value = null;
		}
	} catch (e: unknown) {
		error.value = e instanceof Error ? e.message : String(e);
	} finally {
		running.value = false;
	}
}

async function refresh() {
	activePreparedName.value = null;
	await run();
}

async function generatePrepared() {
	generating.value = true;
	error.value = "";
	try {
		const res = await apiGeneratePreparedReport(call, props.reportName, { ...filters });
		await loadPreparedList();
		showPreparedList.value = true;
		error.value = "";
		preparedInfo.value = { name: res.name, status: "Queued" };
	} catch (e: unknown) {
		error.value = e instanceof Error ? e.message : String(e);
	} finally {
		generating.value = false;
	}
}

async function loadPreparedList() {
	try {
		const res = await apiListPreparedReports(call, props.reportName, { ...filters });
		preparedList.value = res.prepared_reports || [];
	} catch {
		preparedList.value = [];
	}
}

async function openPrepared(name: string) {
	activePreparedName.value = name;
	await run();
}

function scheduleFilterRerun() {
	if (!filtersReady.value || isPrepared.value) return;
	if (filterDebounce) clearTimeout(filterDebounce);
	filterDebounce = setTimeout(() => {
		filterDebounce = null;
		void run();
	}, 350);
}

watch(
	() => filterDefs.value.map((f) => `${f.fieldname}:${filters[f.fieldname] ?? ""}`).join("|"),
	() => scheduleFilterRerun(),
);

onMounted(async () => {
	await loadMeta();
	filtersReady.value = true;
	if (isJanCustom.value) await run();
	else if (isPrepared.value) await loadPreparedList();
});
</script>
