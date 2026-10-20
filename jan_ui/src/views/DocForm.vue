<template>
	<div class="p-6">
		<div class="mb-6 flex flex-wrap items-start justify-between gap-4">
			<div>
				<button type="button" class="mb-2 text-sm text-ink-gray-5 hover:text-ink-gray-8" @click="goBack">
					← {{ meta?.title || "Back" }}
				</button>
				<div class="flex flex-wrap items-center gap-2">
					<h1 class="text-2xl font-semibold text-ink-gray-8">
						{{ isNew ? `New ${meta?.doctype || ""}` : name }}
					</h1>
					<span
						v-if="isDirty"
						class="inline-flex items-center rounded-full bg-orange-100 px-2.5 py-0.5 text-xs font-semibold text-orange-800"
						title="Local changes differ from the saved database version"
					>
						Not Saved
					</span>
					<span
						v-else-if="!isNew && !loading"
						class="inline-flex items-center rounded-full bg-emerald-50 px-2.5 py-0.5 text-xs font-medium text-emerald-700"
					>
						Saved
					</span>
				</div>
				<p v-if="!isNew" class="mt-1 text-sm text-ink-gray-5">
					{{ docstatusLabel(doc.docstatus) }}
					<span v-if="isDirty" class="text-orange-700"> · Unsaved edits — Refresh reloads from DB</span>
				</p>
			</div>
			<div class="flex flex-wrap gap-2">
				<button
					v-if="!isNew"
					type="button"
					class="rounded-lg border border-outline-gray-2 px-4 py-2 text-sm font-medium text-ink-gray-8 disabled:opacity-50"
					:disabled="loading || refreshing"
					:title="isDirty ? 'Discard local changes and reload from database' : 'Reload from database'"
					@click="refreshFromDb"
				>
					{{ refreshing ? "Refreshing…" : "Refresh" }}
				</button>
				<button
					v-if="canSave"
					type="button"
					class="rounded-lg bg-ink-gray-9 px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
					:disabled="saving || (!isDirty && !isNew)"
					@click="save"
				>
					{{ saving ? "Saving…" : Number(doc.docstatus) === 1 ? "Update" : "Save" }}
				</button>
				<button
					v-if="meta?.is_submittable && meta?.permissions?.submit && Number(doc.docstatus) === 0 && !isNew"
					type="button"
					class="rounded-lg border border-outline-gray-2 px-4 py-2 text-sm font-medium text-ink-gray-8"
					:disabled="isDirty"
					title="Save changes before Submit"
					@click="submit"
				>
					Submit
				</button>
				<button
					v-if="meta?.is_submittable && meta?.permissions?.cancel && Number(doc.docstatus) === 1"
					type="button"
					class="rounded-lg border border-red-200 px-4 py-2 text-sm font-medium text-red-700"
					@click="cancel"
				>
					Cancel
				</button>
				<button
					v-if="meta?.is_submittable && meta?.permissions?.amend && Number(doc.docstatus) === 2"
					type="button"
					class="rounded-lg border border-outline-gray-2 px-4 py-2 text-sm font-medium text-ink-gray-8"
					@click="amend"
				>
					Amend
				</button>
			</div>
		</div>

		<div v-if="error" class="mb-4 rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-800">
			{{ error }}
		</div>
		<div v-if="loading" class="py-12 text-center text-ink-gray-5">Loading…</div>

		<template v-else-if="meta">
			<section class="mb-8 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
				<div
					v-for="f in parentFields"
					:key="String(f.fieldname)"
					class="min-w-0"
					:class="{ 'sm:col-span-2 lg:col-span-3': f.fieldtype === 'Check' && f.description }"
				>
					<label
						v-if="f.fieldtype !== 'Check'"
						class="mb-1 block text-xs font-medium text-ink-gray-5"
					>
						{{ f.label }}
						<span v-if="Number(f.reqd)" class="text-red-600">*</span>
					</label>
					<template v-if="f.fieldtype === 'Link'">
						<LinkSelect
							v-model="doc[String(f.fieldname)] as string"
							:doctype="String(f.options || '')"
							:disabled="isFieldReadOnly(f)"
							:reference-doctype="meta.doctype"
						/>
					</template>
					<template v-else-if="f.fieldtype === 'Select'">
						<select
							v-model="doc[String(f.fieldname)]"
							class="w-full rounded-lg border border-outline-gray-2 bg-surface-white px-3 py-2 text-sm"
							:disabled="isFieldReadOnly(f)"
						>
							<option value=""></option>
							<option v-for="opt in selectOptions(f)" :key="opt" :value="opt">{{ opt }}</option>
						</select>
					</template>
					<template v-else-if="f.fieldtype === 'Check'">
						<label class="flex items-start gap-2 text-sm text-ink-gray-7">
							<input
								v-model="doc[String(f.fieldname)]"
								type="checkbox"
								:true-value="1"
								:false-value="0"
								class="mt-0.5 h-4 w-4 shrink-0"
								:disabled="isFieldReadOnly(f)"
							/>
							<span class="min-w-0">
								<span class="font-medium">{{ f.label }}</span>
								<span v-if="Number(f.reqd)" class="text-red-600">*</span>
								<p v-if="f.description" class="mt-1 text-xs font-normal text-ink-gray-5">
									{{ f.description }}
								</p>
							</span>
						</label>
					</template>
					<template
						v-else-if="
							f.fieldtype === 'Text' ||
							f.fieldtype === 'Small Text' ||
							f.fieldtype === 'Long Text' ||
							f.fieldtype === 'Code'
						"
					>
						<textarea
							v-model="doc[String(f.fieldname)] as string"
							rows="3"
							class="w-full rounded-lg border border-outline-gray-2 bg-surface-white px-3 py-2 text-sm"
							:disabled="isFieldReadOnly(f)"
						/>
					</template>
					<template v-else-if="isNumericFieldtype(String(f.fieldtype))">
						<FormattedNumberInput
							v-model="doc[String(f.fieldname)] as string | number | null"
							:fieldtype="String(f.fieldtype)"
							:disabled="isFieldReadOnly(f)"
						/>
					</template>
					<template v-else>
						<input
							v-model="doc[String(f.fieldname)] as string | number"
							:type="inputType(f)"
							class="w-full rounded-lg border border-outline-gray-2 bg-surface-white px-3 py-2 text-sm"
							:disabled="isFieldReadOnly(f)"
						/>
					</template>
				</div>
			</section>

			<section v-for="table in tableFields" :key="String(table.fieldname)" class="mb-8">
				<div class="mb-2 flex flex-wrap items-center justify-between gap-2">
					<h2 class="text-sm font-semibold text-ink-gray-8">
						{{ table.label }}
						<span class="ml-2 font-normal text-ink-gray-5">
							({{ filteredChildRows(String(table.fieldname)).length }} row(s))
						</span>
					</h2>
					<div class="flex flex-wrap items-center gap-2">
						<input
							v-model="childFilters[String(table.fieldname)]"
							type="text"
							placeholder="Filter rows…"
							class="w-40 rounded-lg border border-outline-gray-2 px-2 py-1 text-sm"
							@input="resetChildPage(String(table.fieldname))"
						/>
						<button
							v-if="!isTableReadOnly(table)"
							type="button"
							class="text-sm text-ink-gray-6 hover:text-ink-gray-8"
							@click="addRow(String(table.fieldname))"
						>
							+ Add row
						</button>
					</div>
				</div>
				<div class="overflow-x-auto rounded-xl border border-outline-gray-2">
					<table class="w-full min-w-[480px] text-left text-sm">
						<thead class="bg-surface-gray-2 text-xs uppercase text-ink-gray-5">
							<tr>
								<th class="w-10 px-2 py-2 font-medium">#</th>
								<th
									v-for="cf in childCols(String(table.fieldname))"
									:key="String(cf.fieldname)"
									class="px-3 py-2 font-medium"
								>
									{{ cf.label }}
								</th>
								<th class="px-3 py-2 font-medium">Actions</th>
							</tr>
						</thead>
						<tbody class="divide-y divide-outline-gray-2">
							<tr
								v-for="rowWrap in pagedChildRows(String(table.fieldname))"
								:key="rowWrap.idx"
								class="hover:bg-surface-gray-2"
							>
								<td class="px-2 py-2 text-center text-xs text-ink-gray-5">{{ rowWrap.idx + 1 }}</td>
								<td
									v-for="cf in childCols(String(table.fieldname))"
									:key="String(cf.fieldname)"
									class="px-3 py-2"
								>
									<template v-if="cf.fieldtype === 'Link'">
										<LinkSelect
											v-model="rowWrap.row[String(cf.fieldname)]"
											:doctype="String(cf.options || '')"
											:disabled="isTableReadOnly(table) || Number(cf.read_only) === 1"
											:reference-doctype="meta.doctype"
										/>
									</template>
									<template v-else-if="isNumericFieldtype(String(cf.fieldtype))">
										<FormattedNumberInput
											v-model="rowWrap.row[String(cf.fieldname)] as string | number | null"
											:fieldtype="String(cf.fieldtype)"
											:disabled="isTableReadOnly(table) || Number(cf.read_only) === 1"
											input-class="!rounded border px-2 py-1"
										/>
									</template>
									<input
										v-else
										v-model="rowWrap.row[String(cf.fieldname)]"
										class="w-full rounded border border-outline-gray-2 px-2 py-1 text-sm"
										:disabled="isTableReadOnly(table) || Number(cf.read_only) === 1"
									/>
								</td>
								<td class="whitespace-nowrap px-3 py-2">
									<button
										type="button"
										class="mr-2 text-xs text-ink-gray-6 hover:text-ink-gray-8"
										@click="openChildDialog(String(table.fieldname), rowWrap.idx)"
									>
										Edit
									</button>
									<button
										v-if="!isTableReadOnly(table)"
										type="button"
										class="text-xs text-red-600"
										@click="removeRow(String(table.fieldname), rowWrap.idx)"
									>
										Remove
									</button>
								</td>
							</tr>
							<tr v-if="!filteredChildRows(String(table.fieldname)).length">
								<td
									:colspan="childCols(String(table.fieldname)).length + 2"
									class="px-3 py-6 text-center text-ink-gray-5"
								>
									No rows
								</td>
							</tr>
						</tbody>
					</table>
				</div>
				<div
					v-if="filteredChildRows(String(table.fieldname)).length > CHILD_PAGE_SIZE"
					class="mt-2 flex flex-wrap items-center justify-between gap-2 text-xs text-ink-gray-5"
				>
					<span>
						{{ childPageRangeLabel(String(table.fieldname)) }} of
						{{ filteredChildRows(String(table.fieldname)).length }}
					</span>
					<div class="flex items-center gap-2">
						<button
							type="button"
							class="rounded-lg border border-outline-gray-2 px-3 py-1 text-sm disabled:opacity-40"
							:disabled="(childPages[String(table.fieldname)] || 1) <= 1"
							@click="prevChildPage(String(table.fieldname))"
						>
							Prev
						</button>
						<span>Page {{ childPages[String(table.fieldname)] || 1 }}</span>
						<button
							type="button"
							class="rounded-lg border border-outline-gray-2 px-3 py-1 text-sm disabled:opacity-40"
							:disabled="!hasNextChildPage(String(table.fieldname))"
							@click="nextChildPage(String(table.fieldname))"
						>
							Next
						</button>
					</div>
				</div>
			</section>
		</template>

		<ChildRowDialog
			v-model="childDialog.open"
			:row="childDialog.row"
			:fields="childDialog.fields"
			:title="childDialog.title"
			:disabled="childDialog.disabled"
			:reference-doctype="meta?.doctype"
			@apply="applyChildRow"
		/>
	</div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from "vue";
import { useRouter } from "vue-router";
import ChildRowDialog from "../components/ChildRowDialog.vue";
import FormattedNumberInput from "../components/FormattedNumberInput.vue";
import LinkSelect from "../components/LinkSelect.vue";
import { isNumericFieldtype } from "../utils/format";
import {
	apiAmendDoc,
	apiCancelDoc,
	apiGetDoc,
	apiGetDocMeta,
	apiSaveDoc,
	apiSubmitDoc,
	type DocMeta,
	useJanCall,
} from "../utils/janApi";

const props = defineProps<{ slug: string; name: string }>();
const call = useJanCall();
const router = useRouter();

const CHILD_PAGE_SIZE = 50;

const meta = ref<DocMeta | null>(null);
const doc = reactive<Record<string, unknown>>({});
const loading = ref(true);
const saving = ref(false);
const refreshing = ref(false);
const error = ref("");
const childFilters = reactive<Record<string, string>>({});
const childPages = reactive<Record<string, number>>({});
const savedSnapshot = ref("");

const childDialog = reactive<{
	open: boolean;
	tableField: string;
	idx: number;
	row: Record<string, unknown> | null;
	fields: Array<Record<string, unknown>>;
	title: string;
	disabled: boolean;
}>({
	open: false,
	tableField: "",
	idx: -1,
	row: null,
	fields: [],
	title: "",
	disabled: false,
});

const isNew = computed(() => props.name === "new");

const SKIP_TYPES = new Set([
	"Table",
	"Table MultiSelect",
	"HTML",
	"Button",
	"Heading",
	"Image",
	"Attach",
	"Attach Image",
	"Signature",
	"Geolocation",
	"Color",
	"Barcode",
	"Icon",
	"Section Break",
	"Column Break",
	"Tab Break",
	"Fold",
]);

const canSave = computed(() => {
	if (!meta.value?.permissions?.write && !meta.value?.permissions?.create) return false;
	const ds = Number(doc.docstatus);
	if (ds === 0) return true;
	if (ds === 1) {
		return (meta.value.fields || []).some((f) => Number(f.allow_on_submit) === 1);
	}
	return false;
});

const isDirty = computed(() => {
	if (loading.value || !savedSnapshot.value) return false;
	return stableStringify(doc) !== savedSnapshot.value;
});

function isRenderableParentField(f: Record<string, unknown>) {
	if (SKIP_TYPES.has(String(f.fieldtype))) return false;
	if (Number(f.hidden) === 1) return false;
	if (Number(f.is_layout)) return false;
	return true;
}

/** Keep SPA forms usable on huge ERPNext doctypes; singles / Checks always show. */
const PARENT_FIELD_ALLOWLIST = new Set([
	"company",
	"posting_date",
	"supplier",
	"customer",
	"currency",
	"warehouse",
	"set_warehouse",
	"from_warehouse",
	"to_warehouse",
	"purpose",
	"stock_entry_type",
	"voucher_type",
	"cheque_no",
	"user_remark",
	"bill_no",
	"bill_date",
	"naming_series",
	"import_file",
	"address_title",
	"address_type",
	"address_line1",
	"city",
	"country",
	"customer_name",
	"supplier_name",
	"customer_group",
	"supplier_group",
	"territory",
	"bl_number",
	"supplier_invoice_no",
	"import_type",
	"import_file_number_format",
	"auto_submit_purchase_invoice",
	"auto_submit_journal_entry",
	"create_ifcv",
	"create_landed_cost_voucher",
	"account_name",
	"account_number",
	"parent_account",
	"is_group",
	"root_type",
	"account_type",
	"account_currency",
	"costing_code",
	"costing_name",
	"region",
	"item",
	"chassis_no",
	"costing_date",
	"disabled",
	"total_cost_usd",
	"cost",
]);

const parentFields = computed(() => {
	if (!meta.value) return [];
	const candidates = meta.value.fields.filter(isRenderableParentField);
	// Singles (Costing Settings) and compact Jan doctypes: show every editable field like Desk.
	// Huge ERPNext forms (PI/SI/…) stay on allowlist so the SPA is usable.
	if (meta.value.is_single || candidates.length <= 40) return candidates;
	return candidates.filter((f) => {
		const fn = String(f.fieldname);
		if (String(f.fieldtype) === "Check") return true;
		if (Number(f.reqd) || Number(f.in_list_view) || Number(f.in_standard_filter) || Number(f.allow_on_submit)) {
			return true;
		}
		return PARENT_FIELD_ALLOWLIST.has(fn);
	});
});

const tableFields = computed(() => {
	if (!meta.value) return [];
	return meta.value.fields.filter((f) => f.fieldtype === "Table" && Number(f.hidden) !== 1);
});

function stableStringify(value: unknown): string {
	return JSON.stringify(value, (_k, v) => {
		if (v && typeof v === "object" && !Array.isArray(v)) {
			const sorted: Record<string, unknown> = {};
			for (const key of Object.keys(v as Record<string, unknown>).sort()) {
				sorted[key] = (v as Record<string, unknown>)[key];
			}
			return sorted;
		}
		return v;
	});
}

function markClean() {
	savedSnapshot.value = stableStringify(doc);
}

function childCols(fieldname: string) {
	const child = meta.value?.child_tables?.[fieldname];
	if (!child) return [];
	return child.fields
		.filter((f) => Number(f.hidden) !== 1 && !SKIP_TYPES.has(String(f.fieldtype)) && !Number(f.is_layout))
		.filter(
			(f) =>
				Number(f.in_list_view) ||
				Number(f.reqd) ||
				[
					"item_code",
					"qty",
					"rate",
					"warehouse",
					"account",
					"debit_in_account_currency",
					"credit_in_account_currency",
					"cost_center",
					"party",
				].includes(String(f.fieldname)),
		)
		.slice(0, 8);
}

function allChildFields(fieldname: string) {
	return meta.value?.child_tables?.[fieldname]?.fields || [];
}

function filteredChildRows(fieldname: string) {
	const rows = ((doc[fieldname] as Array<Record<string, unknown>>) || []).map((row, idx) => ({ row, idx }));
	const q = (childFilters[fieldname] || "").trim().toLowerCase();
	if (!q) return rows;
	return rows.filter(({ row }) =>
		Object.values(row).some((v) => v != null && String(v).toLowerCase().includes(q)),
	);
}

function pagedChildRows(fieldname: string) {
	const all = filteredChildRows(fieldname);
	const page = childPages[fieldname] || 1;
	const start = (page - 1) * CHILD_PAGE_SIZE;
	return all.slice(start, start + CHILD_PAGE_SIZE);
}

function hasNextChildPage(fieldname: string) {
	const total = filteredChildRows(fieldname).length;
	const page = childPages[fieldname] || 1;
	return page * CHILD_PAGE_SIZE < total;
}

function childPageRangeLabel(fieldname: string) {
	const total = filteredChildRows(fieldname).length;
	const page = childPages[fieldname] || 1;
	const from = (page - 1) * CHILD_PAGE_SIZE + 1;
	const to = Math.min(page * CHILD_PAGE_SIZE, total);
	return `${from}–${to}`;
}

function resetChildPage(fieldname: string) {
	childPages[fieldname] = 1;
}

function prevChildPage(fieldname: string) {
	const page = childPages[fieldname] || 1;
	if (page > 1) childPages[fieldname] = page - 1;
}

function nextChildPage(fieldname: string) {
	if (hasNextChildPage(fieldname)) {
		childPages[fieldname] = (childPages[fieldname] || 1) + 1;
	}
}

function isFieldReadOnly(f: Record<string, unknown>) {
	const ds = Number(doc.docstatus);
	if (ds === 2) return true;
	if (ds === 1) {
		return Number(f.allow_on_submit) !== 1 || Number(f.read_only) === 1;
	}
	return Number(f.read_only) === 1;
}

function isTableReadOnly(f: Record<string, unknown>) {
	const ds = Number(doc.docstatus);
	if (ds === 2) return true;
	if (ds === 1) return Number(f.allow_on_submit) !== 1;
	return Number(f.read_only) === 1;
}

function selectOptions(f: Record<string, unknown>) {
	return String(f.options || "")
		.split("\n")
		.map((s) => s.trim())
		.filter(Boolean);
}

function inputType(f: Record<string, unknown>) {
	const t = String(f.fieldtype);
	if (t === "Date") return "date";
	if (t === "Datetime") return "datetime-local";
	return "text";
}

function docstatusLabel(ds: unknown) {
	const n = Number(ds);
	if (n === 1) return "Submitted";
	if (n === 2) return "Cancelled";
	return "Draft";
}

function goBack() {
	if (isDirty.value && !confirm("You have unsaved changes. Leave this form?")) return;
	router.push(`/docs/${props.slug}`);
}

function addRow(fieldname: string) {
	const rows = (doc[fieldname] as Array<Record<string, unknown>>) || [];
	rows.push({});
	doc[fieldname] = rows;
	const page = Math.ceil(rows.length / CHILD_PAGE_SIZE) || 1;
	childPages[fieldname] = page;
	openChildDialog(fieldname, rows.length - 1);
}

function removeRow(fieldname: string, idx: number) {
	const rows = [...((doc[fieldname] as Array<Record<string, unknown>>) || [])];
	rows.splice(idx, 1);
	doc[fieldname] = rows;
	const maxPage = Math.max(1, Math.ceil(filteredChildRows(fieldname).length / CHILD_PAGE_SIZE) || 1);
	if ((childPages[fieldname] || 1) > maxPage) childPages[fieldname] = maxPage;
}

function openChildDialog(fieldname: string, idx: number) {
	const rows = (doc[fieldname] as Array<Record<string, unknown>>) || [];
	const tableDf = tableFields.value.find((t) => String(t.fieldname) === fieldname);
	childDialog.tableField = fieldname;
	childDialog.idx = idx;
	childDialog.row = { ...(rows[idx] || {}) };
	childDialog.fields = allChildFields(fieldname);
	childDialog.title = `${tableDf?.label || fieldname} · Row ${idx + 1}`;
	childDialog.disabled = tableDf ? isTableReadOnly(tableDf) : true;
	childDialog.open = true;
}

function applyChildRow(updated: Record<string, unknown>) {
	const fieldname = childDialog.tableField;
	const rows = [...((doc[fieldname] as Array<Record<string, unknown>>) || [])];
	if (childDialog.idx >= 0 && childDialog.idx < rows.length) {
		rows[childDialog.idx] = { ...rows[childDialog.idx], ...updated };
		doc[fieldname] = rows;
	}
}

async function load() {
	loading.value = true;
	error.value = "";
	try {
		meta.value = await apiGetDocMeta(call, props.slug);
		Object.keys(doc).forEach((k) => delete doc[k]);
		Object.keys(childPages).forEach((k) => delete childPages[k]);
		Object.keys(childFilters).forEach((k) => delete childFilters[k]);
		if (isNew.value) {
			doc.docstatus = 0;
			for (const tf of tableFields.value) {
				doc[String(tf.fieldname)] = [];
			}
			if (props.slug === "stock-entries") {
				doc.purpose = "Material Transfer";
			}
		} else {
			const data = await apiGetDoc(call, props.slug, props.name);
			Object.assign(doc, data);
		}
		markClean();
	} catch (e: unknown) {
		error.value = e instanceof Error ? e.message : String(e);
		savedSnapshot.value = "";
	} finally {
		loading.value = false;
	}
}

async function refreshFromDb() {
	if (isNew.value) return;
	if (isDirty.value && !confirm("Discard unsaved changes and reload from the database?")) return;
	refreshing.value = true;
	error.value = "";
	try {
		const data = await apiGetDoc(call, props.slug, props.name);
		Object.keys(doc).forEach((k) => delete doc[k]);
		Object.assign(doc, data);
		Object.keys(childPages).forEach((k) => delete childPages[k]);
		markClean();
	} catch (e: unknown) {
		error.value = e instanceof Error ? e.message : String(e);
	} finally {
		refreshing.value = false;
	}
}

async function save() {
	saving.value = true;
	error.value = "";
	try {
		const saved = await apiSaveDoc(call, props.slug, { ...doc });
		Object.keys(doc).forEach((k) => delete doc[k]);
		Object.assign(doc, saved);
		markClean();
		if (isNew.value && saved.name) {
			await router.replace(`/docs/${props.slug}/${encodeURIComponent(String(saved.name))}`);
		}
	} catch (e: unknown) {
		error.value = e instanceof Error ? e.message : String(e);
	} finally {
		saving.value = false;
	}
}

async function submit() {
	error.value = "";
	try {
		const saved = await apiSubmitDoc(call, props.slug, String(doc.name));
		Object.keys(doc).forEach((k) => delete doc[k]);
		Object.assign(doc, saved);
		markClean();
	} catch (e: unknown) {
		error.value = e instanceof Error ? e.message : String(e);
	}
}

async function cancel() {
	error.value = "";
	try {
		const saved = await apiCancelDoc(call, props.slug, String(doc.name));
		Object.keys(doc).forEach((k) => delete doc[k]);
		Object.assign(doc, saved);
		markClean();
	} catch (e: unknown) {
		error.value = e instanceof Error ? e.message : String(e);
	}
}

async function amend() {
	error.value = "";
	try {
		const saved = await apiAmendDoc(call, props.slug, String(doc.name));
		await router.push(`/docs/${props.slug}/${encodeURIComponent(String(saved.name))}`);
	} catch (e: unknown) {
		error.value = e instanceof Error ? e.message : String(e);
	}
}

watch(() => [props.slug, props.name], () => void load());
onMounted(() => void load());
</script>
