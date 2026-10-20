<template>
	<div class="p-6">
		<div class="mb-6 flex flex-wrap items-end justify-between gap-4">
			<div>
				<h1 class="text-2xl font-semibold text-ink-gray-8">{{ meta?.title || slug }}</h1>
				<p class="mt-1 text-sm text-ink-gray-5">{{ meta?.doctype }}</p>
			</div>
			<div class="flex flex-wrap items-center gap-3">
				<div class="w-full max-w-sm sm:w-64">
					<FormControl v-model="search" type="text" placeholder="Search…" @update:model-value="onSearch" />
				</div>
				<button
					v-if="meta?.permissions?.create && !meta?.is_single"
					type="button"
					class="rounded-lg bg-ink-gray-9 px-4 py-2 text-sm font-medium text-white hover:opacity-90"
					@click="$router.push(`/docs/${slug}/new`)"
				>
					New
				</button>
			</div>
		</div>

		<!-- Standard / top filters (Desk List View) -->
		<section
			v-if="standardFilters.length"
			class="mb-4 flex flex-wrap items-end gap-3 rounded-xl border border-outline-gray-2 p-3"
		>
			<div v-for="f in standardFilters" :key="f.fieldname" class="min-w-[140px]">
				<label class="mb-1 block text-xs font-medium text-ink-gray-5">{{ f.label }}</label>
				<select
					v-if="f.fieldtype === 'Select' || f.fieldtype === 'Check'"
					v-model="filterValues[f.fieldname]"
					class="w-full rounded-lg border border-outline-gray-2 px-3 py-2 text-sm"
					@change="onFilterChange"
				>
					<option value="">—</option>
					<template v-if="f.fieldtype === 'Check'">
						<option value="1">Yes</option>
						<option value="0">No</option>
					</template>
					<option v-for="opt in selectOptions(f)" :key="opt" :value="opt">{{ opt }}</option>
				</select>
				<LinkSelect
					v-else-if="f.fieldtype === 'Link'"
					v-model="filterValues[f.fieldname]"
					:doctype="String(f.options || '')"
					:reference-doctype="meta?.doctype"
					@update:model-value="onFilterChange"
				/>
				<input
					v-else
					v-model="filterValues[f.fieldname]"
					:type="f.fieldtype === 'Date' ? 'date' : 'text'"
					class="w-full rounded-lg border border-outline-gray-2 px-3 py-2 text-sm"
					@change="onFilterChange"
				/>
			</div>
			<button type="button" class="text-sm text-ink-gray-6 hover:text-ink-gray-8" @click="clearFilters">
				Clear filters
			</button>
		</section>

		<div v-if="error" class="mb-4 rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-800">
			{{ error }}
		</div>

		<div class="overflow-x-auto rounded-xl border border-outline-gray-2">
			<table class="w-full min-w-[640px] text-left text-sm">
				<thead class="bg-surface-gray-2 text-xs uppercase tracking-wide text-ink-gray-5">
					<tr>
						<th
							v-for="f in displayFields"
							:key="f"
							class="cursor-pointer px-4 py-3 font-medium select-none hover:text-ink-gray-8"
							@click="toggleSort(f)"
						>
							{{ labelFor(f) }}
							<span v-if="orderField === f" class="ml-1">{{ orderDir === "asc" ? "↑" : "↓" }}</span>
						</th>
					</tr>
				</thead>
				<tbody class="divide-y divide-outline-gray-2">
					<tr v-if="loading && !rows.length">
						<td :colspan="displayFields.length" class="px-4 py-8 text-center text-ink-gray-5">Loading…</td>
					</tr>
					<tr v-else-if="!rows.length">
						<td :colspan="displayFields.length" class="px-4 py-8 text-center text-ink-gray-5">No records</td>
					</tr>
					<tr
						v-for="row in rows"
						:key="String(row.name)"
						class="cursor-pointer hover:bg-surface-gray-2"
						@click="openRow(row)"
					>
						<td v-for="f in displayFields" :key="f" class="px-4 py-3 text-ink-gray-7">
							<span v-if="f === 'docstatus'">{{ docstatusLabel(row.docstatus) }}</span>
							<span v-else class="tabular-nums">{{ formatCell(row[f], f) }}</span>
						</td>
					</tr>
				</tbody>
			</table>
		</div>

		<div class="mt-4 flex flex-wrap items-center justify-between gap-3">
			<p class="text-xs text-ink-gray-5">
				{{ rangeLabel }} · {{ total }} record(s)
			</p>
			<div class="flex flex-wrap items-center gap-2">
				<label class="text-xs text-ink-gray-5">Page size</label>
				<select
					v-model.number="pageSize"
					class="rounded-lg border border-outline-gray-2 px-2 py-1.5 text-sm"
					@change="onPageSizeChange"
				>
					<option v-for="n in pageSizeOptions" :key="n" :value="n">{{ n }}</option>
					<option :value="-1">Load more</option>
				</select>
				<template v-if="pageSize !== -1">
					<button
						type="button"
						class="rounded-lg border border-outline-gray-2 px-3 py-1.5 text-sm disabled:opacity-40"
						:disabled="start <= 0 || loading"
						@click="prevPage"
					>
						Prev
					</button>
					<span class="text-xs text-ink-gray-5">Page {{ currentPage }}</span>
					<button
						type="button"
						class="rounded-lg border border-outline-gray-2 px-3 py-1.5 text-sm disabled:opacity-40"
						:disabled="!hasNext || loading"
						@click="nextPage"
					>
						Next
					</button>
				</template>
				<button
					v-else
					type="button"
					class="rounded-lg border border-outline-gray-2 px-3 py-1.5 text-sm disabled:opacity-40"
					:disabled="!hasNext || loading"
					@click="loadMore"
				>
					{{ loading ? "Loading…" : "Load more" }}
				</button>
			</div>
		</div>
	</div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from "vue";
import { useRouter } from "vue-router";
import { FormControl } from "frappe-ui";
import LinkSelect from "../components/LinkSelect.vue";
import { formatCellValue } from "../utils/format";
import {
	apiGetDocMeta,
	apiListDocs,
	type DocMeta,
	type StandardFilter,
	useJanCall,
} from "../utils/janApi";

const props = defineProps<{ slug: string }>();
const call = useJanCall();
const router = useRouter();

const meta = ref<DocMeta | null>(null);
const rows = ref<Array<Record<string, unknown>>>([]);
const total = ref(0);
const search = ref("");
const loading = ref(true);
const error = ref("");
const start = ref(0);
const pageSize = ref(20);
const pageSizeOptions = ref([20, 100, 500, 2500]);
const orderField = ref("modified");
const orderDir = ref<"asc" | "desc">("desc");
const filterValues = reactive<Record<string, string>>({});
const loadMoreChunk = 100;
let timer: ReturnType<typeof setTimeout> | null = null;

const displayFields = computed(() => {
	const fields = meta.value?.list_fields?.length ? meta.value.list_fields : ["name"];
	return fields.slice(0, 12);
});

const standardFilters = computed<StandardFilter[]>(() => meta.value?.standard_filters || []);

const currentPage = computed(() => Math.floor(start.value / Math.max(pageSize.value === -1 ? loadMoreChunk : pageSize.value, 1)) + 1);
const hasNext = computed(() => {
	if (pageSize.value === -1) return rows.value.length < total.value;
	return start.value + rows.value.length < total.value;
});
const rangeLabel = computed(() => {
	if (!rows.value.length) return "0–0";
	if (pageSize.value === -1) return `1–${rows.value.length}`;
	const from = start.value + 1;
	const to = start.value + rows.value.length;
	return `${from}–${to}`;
});

function labelFor(f: string) {
	const df = meta.value?.fields?.find((x) => x.fieldname === f);
	return (df?.label as string) || f.replace(/_/g, " ");
}

function selectOptions(f: StandardFilter) {
	return String(f.options || "")
		.split("\n")
		.map((s) => s.trim())
		.filter(Boolean);
}

function fieldtypeFor(f: string) {
	return String(meta.value?.fields?.find((x) => x.fieldname === f)?.fieldtype || "");
}

function formatCell(v: unknown, fieldname?: string) {
	return formatCellValue(v, fieldname ? fieldtypeFor(fieldname) : undefined);
}

function docstatusLabel(ds: unknown) {
	const n = Number(ds);
	if (n === 1) return "Submitted";
	if (n === 2) return "Cancelled";
	return "Draft";
}

function openRow(row: Record<string, unknown>) {
	const name = String(row.name || "");
	if (props.slug === "import-files") {
		router.push(`/import-files/${encodeURIComponent(name)}`);
		return;
	}
	if (props.slug === "ifcvs") {
		router.push(`/ifcv/${encodeURIComponent(name)}`);
		return;
	}
	if (props.slug === "excel-importer") {
		router.push(`/excel-importer/${encodeURIComponent(name)}`);
		return;
	}
	if (props.slug === "costing-settings") {
		router.push(`/docs/costing-settings/${encodeURIComponent(name)}`);
		return;
	}
	router.push(`/docs/${props.slug}/${encodeURIComponent(name)}`);
}

function buildFilters(): unknown[] {
	const out: unknown[] = [];
	const doctype = meta.value?.doctype || "";
	for (const f of standardFilters.value) {
		const raw = (filterValues[f.fieldname] || "").trim();
		if (!raw) continue;
		const cond = f.condition || "=";
		const value = cond === "like" && !raw.includes("%") ? `%${raw}%` : raw;
		out.push([doctype, f.fieldname, cond, value]);
	}
	return out;
}

async function loadMeta() {
	meta.value = await apiGetDocMeta(call, props.slug);
	if (meta.value.page_size_options?.length) {
		pageSizeOptions.value = meta.value.page_size_options;
	}
	for (const f of meta.value.standard_filters || []) {
		if (filterValues[f.fieldname] == null) filterValues[f.fieldname] = "";
	}
	if (meta.value.is_single) {
		// jump to the single form
		const res = await apiListDocs(call, props.slug, { limit: 1, start: 0 });
		const name = res.rows?.[0]?.name || meta.value.doctype;
		await router.replace(`/docs/${props.slug}/${encodeURIComponent(String(name))}`);
	}
}

async function load(append = false) {
	loading.value = true;
	error.value = "";
	try {
		const limit = pageSize.value === -1 ? loadMoreChunk : pageSize.value;
		const res = await apiListDocs(call, props.slug, {
			search: search.value,
			limit,
			start: start.value,
			filters: buildFilters(),
			order_field: orderField.value,
			order_dir: orderDir.value,
		});
		if (append) {
			rows.value = [...rows.value, ...(res.rows || [])];
		} else {
			rows.value = res.rows || [];
		}
		total.value = res.total || 0;
	} catch (e: unknown) {
		error.value = e instanceof Error ? e.message : String(e);
	} finally {
		loading.value = false;
	}
}

function onSearch() {
	if (timer) clearTimeout(timer);
	timer = setTimeout(() => {
		start.value = 0;
		void load();
	}, 300);
}

function onFilterChange() {
	start.value = 0;
	void load();
}

function clearFilters() {
	for (const k of Object.keys(filterValues)) filterValues[k] = "";
	start.value = 0;
	void load();
}

function toggleSort(f: string) {
	if (orderField.value === f) {
		orderDir.value = orderDir.value === "asc" ? "desc" : "asc";
	} else {
		orderField.value = f;
		orderDir.value = "asc";
	}
	start.value = 0;
	void load();
}

function onPageSizeChange() {
	start.value = 0;
	void load();
}

function prevPage() {
	const size = pageSize.value === -1 ? loadMoreChunk : pageSize.value;
	start.value = Math.max(0, start.value - size);
	void load();
}

function nextPage() {
	const size = pageSize.value === -1 ? loadMoreChunk : pageSize.value;
	start.value = start.value + size;
	void load();
}

function loadMore() {
	start.value = rows.value.length;
	void load(true);
}

watch(
	() => props.slug,
	async () => {
		search.value = "";
		start.value = 0;
		orderField.value = "modified";
		orderDir.value = "desc";
		Object.keys(filterValues).forEach((k) => delete filterValues[k]);
		await loadMeta();
		if (!meta.value?.is_single) await load();
	},
);

onMounted(async () => {
	try {
		await loadMeta();
		if (!meta.value?.is_single) await load();
	} catch (e: unknown) {
		error.value = e instanceof Error ? e.message : String(e);
		loading.value = false;
	}
});
</script>
