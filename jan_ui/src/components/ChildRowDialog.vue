<template>
	<Dialog v-model="open" :options="{ title: title || 'Edit row', size: '3xl' }">
		<template #body-content>
			<div class="max-h-[70vh] space-y-4 overflow-y-auto pr-1">
				<template v-for="(f, idx) in visibleFields" :key="String(f.fieldname) + idx">
					<div
						v-if="f.fieldtype === 'Section Break'"
						class="border-t border-outline-gray-2 pt-3 text-sm font-semibold text-ink-gray-8"
					>
						{{ f.label || "" }}
					</div>
					<div v-else-if="f.fieldtype === 'Column Break'" class="hidden" />
					<div v-else class="min-w-0">
						<label class="mb-1 block text-xs font-medium text-ink-gray-5">
							{{ f.label }}
							<span v-if="Number(f.reqd)" class="text-red-600">*</span>
						</label>
						<template v-if="f.fieldtype === 'Link'">
							<LinkSelect
								v-model="local[String(f.fieldname)] as string"
								:doctype="String(f.options || '')"
								:disabled="disabled || Number(f.read_only) === 1"
								:reference-doctype="referenceDoctype"
							/>
						</template>
						<template v-else-if="f.fieldtype === 'Select'">
							<select
								v-model="local[String(f.fieldname)]"
								class="w-full rounded-lg border border-outline-gray-2 bg-surface-white px-3 py-2 text-sm"
								:disabled="disabled || Number(f.read_only) === 1"
							>
								<option value=""></option>
								<option v-for="opt in selectOptions(f)" :key="opt" :value="opt">{{ opt }}</option>
							</select>
						</template>
						<template v-else-if="f.fieldtype === 'Check'">
							<input
								v-model="local[String(f.fieldname)]"
								type="checkbox"
								:true-value="1"
								:false-value="0"
								class="h-4 w-4"
								:disabled="disabled || Number(f.read_only) === 1"
							/>
						</template>
						<template
							v-else-if="
								f.fieldtype === 'Text' ||
								f.fieldtype === 'Small Text' ||
								f.fieldtype === 'Long Text' ||
								f.fieldtype === 'Code' ||
								f.fieldtype === 'Text Editor'
							"
						>
							<textarea
								v-model="local[String(f.fieldname)] as string"
								rows="3"
								class="w-full rounded-lg border border-outline-gray-2 bg-surface-white px-3 py-2 text-sm"
								:disabled="disabled || Number(f.read_only) === 1"
							/>
						</template>
						<template v-else-if="isNumericFieldtype(String(f.fieldtype))">
							<FormattedNumberInput
								v-model="local[String(f.fieldname)] as string | number | null"
								:fieldtype="String(f.fieldtype)"
								:disabled="disabled || Number(f.read_only) === 1"
							/>
						</template>
						<template v-else>
							<input
								v-model="local[String(f.fieldname)] as string | number"
								:type="inputType(f)"
								class="w-full rounded-lg border border-outline-gray-2 bg-surface-white px-3 py-2 text-sm"
								:disabled="disabled || Number(f.read_only) === 1"
							/>
						</template>
					</div>
				</template>
			</div>
			<div class="mt-6 flex justify-end gap-2">
				<button
					type="button"
					class="rounded-lg border border-outline-gray-2 px-4 py-2 text-sm"
					@click="open = false"
				>
					Cancel
				</button>
				<button
					v-if="!disabled"
					type="button"
					class="rounded-lg bg-ink-gray-9 px-4 py-2 text-sm font-medium text-white"
					@click="apply"
				>
					Apply
				</button>
			</div>
		</template>
	</Dialog>
</template>

<script setup lang="ts">
import { computed, reactive, watch } from "vue";
import { Dialog } from "frappe-ui";
import FormattedNumberInput from "./FormattedNumberInput.vue";
import LinkSelect from "./LinkSelect.vue";
import { isNumericFieldtype } from "../utils/format";

const props = defineProps<{
	modelValue: boolean;
	row: Record<string, unknown> | null;
	fields: Array<Record<string, unknown>>;
	title?: string;
	disabled?: boolean;
	referenceDoctype?: string;
}>();

const emit = defineEmits<{
	"update:modelValue": [boolean];
	apply: [Record<string, unknown>];
}>();

const open = computed({
	get: () => props.modelValue,
	set: (v: boolean) => emit("update:modelValue", v),
});

const local = reactive<Record<string, unknown>>({});

const SKIP = new Set(["Table", "Table MultiSelect", "HTML", "Button", "Heading", "Image", "Fold", "Tab Break"]);

const visibleFields = computed(() =>
	(props.fields || []).filter((f) => {
		if (Number(f.hidden) === 1) return false;
		const ft = String(f.fieldtype);
		if (SKIP.has(ft)) return false;
		return true;
	}),
);

watch(
	() => [props.modelValue, props.row],
	() => {
		Object.keys(local).forEach((k) => delete local[k]);
		if (props.row) Object.assign(local, JSON.parse(JSON.stringify(props.row)));
	},
	{ immediate: true, deep: true },
);

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
	if (t === "Time") return "time";
	return "text";
}

function apply() {
	emit("apply", { ...local });
	open.value = false;
}
</script>
