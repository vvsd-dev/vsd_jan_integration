<template>
	<div class="p-6">
		<div class="mb-6 flex flex-wrap items-start justify-between gap-4">
			<div>
				<button
					type="button"
					class="mb-2 text-sm text-ink-gray-5 hover:text-ink-gray-8"
					@click="$router.push('/excel-importer')"
				>
					← Excel Importer
				</button>
				<h1 class="text-2xl font-semibold text-ink-gray-8">
					{{ isNew ? "New Excel Import" : name }}
				</h1>
				<p class="mt-1 text-sm text-ink-gray-5">{{ doc.import_status || "Pending" }}</p>
			</div>
			<div class="flex flex-wrap gap-2">
				<button
					v-if="Number(doc.docstatus) !== 1"
					type="button"
					class="rounded-lg border border-outline-gray-2 px-4 py-2 text-sm font-medium"
					:disabled="saving"
					@click="save"
				>
					{{ saving ? "Saving…" : "Save" }}
				</button>
				<button
					v-if="!isNew && doc.excel_file && doc.import_status === 'Pending'"
					type="button"
					class="rounded-lg bg-ink-gray-9 px-4 py-2 text-sm font-medium text-white"
					@click="start"
				>
					Start Import
				</button>
				<button
					v-if="!isNew && hasFailed && String(doc.import_status || '').includes('Error')"
					type="button"
					class="rounded-lg border border-red-200 px-4 py-2 text-sm font-medium text-red-700"
					@click="retry"
				>
					Retry Failed
				</button>
			</div>
		</div>

		<div v-if="error" class="mb-4 rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-800">
			{{ error }}
		</div>
		<div v-if="loading" class="py-12 text-center text-ink-gray-5">Loading…</div>

		<template v-else>
			<section class="mb-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
				<div>
					<label class="mb-1 block text-xs font-medium text-ink-gray-5">Excel File URL</label>
					<input
						v-model="doc.excel_file as string"
						type="text"
						class="w-full rounded-lg border border-outline-gray-2 px-3 py-2 text-sm"
						placeholder="/files/…"
						:disabled="!isNew && !!doc.excel_file"
					/>
					<p class="mt-1 text-xs text-ink-gray-5">Attach via Desk File Manager or paste file URL</p>
				</div>
				<div>
					<label class="mb-1 block text-xs font-medium text-ink-gray-5">Import Type</label>
					<input
						:value="String(doc.import_type || 'Auto Detect')"
						type="text"
						class="w-full rounded-lg border border-outline-gray-2 bg-surface-gray-2 px-3 py-2 text-sm"
						readonly
					/>
				</div>
				<div>
					<label class="mb-1 block text-xs font-medium text-ink-gray-5">Warehouse (MKT Statement)</label>
					<LinkSelect v-model="doc.warehouse as string" doctype="Warehouse" placeholder="Select warehouse…" />
				</div>
				<div>
					<label class="mb-1 block text-xs font-medium text-ink-gray-5">Import File Number Format</label>
					<select v-model="doc.import_file_number_format" class="w-full rounded-lg border border-outline-gray-2 px-3 py-2 text-sm">
						<option>Invoice No</option>
						<option>BL Number</option>
						<option>Invoice No - BL Number</option>
					</select>
				</div>
				<label class="flex items-center gap-2 text-sm text-ink-gray-7">
					<input v-model="doc.auto_submit_purchase_invoice" type="checkbox" :true-value="1" :false-value="0" />
					Auto Submit Purchase Invoice
				</label>
				<label class="flex items-center gap-2 text-sm text-ink-gray-7">
					<input v-model="doc.auto_submit_journal_entry" type="checkbox" :true-value="1" :false-value="0" />
					Auto Submit Journal Entry
				</label>
				<label class="flex items-center gap-2 text-sm text-ink-gray-7">
					<input v-model="doc.create_ifcv" type="checkbox" :true-value="1" :false-value="0" />
					Create Import File Cost Voucher
				</label>
			</section>

			<section
				v-if="!isNew"
				class="mb-6 rounded-xl border border-outline-gray-2 p-4"
			>
				<div class="mb-2 flex items-center justify-between text-sm">
					<span class="font-medium text-ink-gray-8">Progress</span>
					<span class="text-ink-gray-5">{{ progressPercent }}%</span>
				</div>
				<div class="h-2 overflow-hidden rounded-full bg-surface-gray-2">
					<div class="h-full bg-ink-gray-8 transition-all" :style="{ width: `${progressPercent}%` }" />
				</div>
				<p class="mt-3 text-sm text-ink-gray-6">
					Invoices {{ doc.processed_invoices || 0 }} / {{ doc.total_invoices || 0 }} · Cars
					{{ doc.processed_cars || 0 }} / {{ doc.total_cars || 0 }}
					<span v-if="doc.estimated_time"> · {{ doc.estimated_time }}</span>
				</p>
				<p v-if="busy" class="mt-1 text-xs text-ink-gray-5">Import running — refreshing…</p>
			</section>

			<section v-if="doc.import_log" class="rounded-xl border border-outline-gray-2">
				<div class="border-b border-outline-gray-2 px-4 py-3 text-sm font-semibold">Import Log</div>
				<pre class="max-h-96 overflow-auto whitespace-pre-wrap p-4 text-xs text-ink-gray-7">{{ doc.import_log }}</pre>
			</section>
		</template>
	</div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, reactive, ref } from "vue";
import { useRouter } from "vue-router";
import LinkSelect from "../components/LinkSelect.vue";
import {
	apiGetImportProgress,
	apiGetImporter,
	apiSaveImporter,
	apiStartImport,
	useJanCall,
} from "../utils/janApi";

const props = defineProps<{ name: string }>();
const call = useJanCall();
const router = useRouter();

const isNew = computed(() => props.name === "new");
const doc = reactive<Record<string, unknown>>({
	import_file_number_format: "Invoice No",
	auto_submit_purchase_invoice: 0,
	auto_submit_journal_entry: 0,
	create_ifcv: 0,
	warehouse: "",
});
const loading = ref(!isNew.value);
const saving = ref(false);
const error = ref("");
const progressPercent = ref(0);
let pollTimer: ReturnType<typeof setInterval> | null = null;

const hasFailed = computed(() => {
	const fr = doc.failed_records;
	return !!fr && fr !== "[]" && fr !== "{}";
});

const busy = computed(() => {
	const s = String(doc.import_status || "");
	return s === "Queued" || s === "In Progress";
});

async function load() {
	loading.value = true;
	error.value = "";
	try {
		const data = await apiGetImporter(call, props.name);
		Object.keys(doc).forEach((k) => delete doc[k]);
		Object.assign(doc, data);
		await refreshProgress();
	} catch (e: unknown) {
		error.value = e instanceof Error ? e.message : String(e);
	} finally {
		loading.value = false;
	}
}

async function refreshProgress() {
	if (isNew.value || !props.name) return;
	try {
		const p = await apiGetImportProgress(call, props.name);
		Object.assign(doc, {
			import_status: p.import_status,
			processed_invoices: p.processed_invoices,
			total_invoices: p.total_invoices,
			processed_cars: p.processed_cars,
			total_cars: p.total_cars,
			estimated_time: p.estimated_time,
			import_log: p.import_log,
			failed_records: p.failed_records,
			warehouse: p.warehouse ?? doc.warehouse,
		});
		progressPercent.value = Number(p.progress_percent) || 0;
	} catch {
		/* ignore poll errors */
	}
}

async function save() {
	saving.value = true;
	error.value = "";
	try {
		const saved = await apiSaveImporter(call, { ...doc, name: isNew.value ? undefined : props.name });
		Object.assign(doc, saved);
		if (isNew.value && saved.name) {
			await router.replace(`/excel-importer/${encodeURIComponent(String(saved.name))}`);
		}
	} catch (e: unknown) {
		error.value = e instanceof Error ? e.message : String(e);
	} finally {
		saving.value = false;
	}
}

async function start() {
	error.value = "";
	try {
		await apiStartImport(call, String(doc.name), false);
		doc.import_status = "Queued";
		await refreshProgress();
	} catch (e: unknown) {
		error.value = e instanceof Error ? e.message : String(e);
	}
}

async function retry() {
	error.value = "";
	try {
		await apiStartImport(call, String(doc.name), true);
		doc.import_status = "Queued";
		await refreshProgress();
	} catch (e: unknown) {
		error.value = e instanceof Error ? e.message : String(e);
	}
}

onMounted(async () => {
	if (!isNew.value) await load();
	pollTimer = setInterval(() => {
		if (busy.value) void refreshProgress();
	}, 2000);
});

onUnmounted(() => {
	if (pollTimer) clearInterval(pollTimer);
});
</script>
