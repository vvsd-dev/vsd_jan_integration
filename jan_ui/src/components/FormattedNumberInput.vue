<template>
	<input
		:value="display"
		type="text"
		inputmode="decimal"
		class="w-full rounded-lg border border-outline-gray-2 bg-surface-white px-3 py-2 text-sm tabular-nums text-ink-gray-8 outline-none focus:border-outline-gray-4 disabled:opacity-60"
		:class="inputClass"
		:disabled="disabled"
		:readonly="readonly"
		@focus="onFocus"
		@blur="onBlur"
		@input="onInput"
	/>
</template>

<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { formatNumber, parseLooseNumber } from "../utils/format";

const props = withDefaults(
	defineProps<{
		modelValue?: string | number | null;
		fieldtype?: string;
		disabled?: boolean;
		readonly?: boolean;
		inputClass?: string;
	}>(),
	{
		fieldtype: "Float",
		disabled: false,
		readonly: false,
		inputClass: "",
	},
);

const emit = defineEmits<{ "update:modelValue": [number | string | null] }>();

const focused = ref(false);
const draft = ref("");

const display = computed(() => {
	if (focused.value) return draft.value;
	if (props.modelValue == null || props.modelValue === "") return "";
	return formatNumber(props.modelValue, props.fieldtype);
});

watch(
	() => props.modelValue,
	(v) => {
		if (!focused.value) {
			draft.value = v == null || v === "" ? "" : String(v);
		}
	},
	{ immediate: true },
);

function onFocus() {
	focused.value = true;
	draft.value = props.modelValue == null || props.modelValue === "" ? "" : String(props.modelValue);
}

function onInput(e: Event) {
	const raw = (e.target as HTMLInputElement).value;
	draft.value = raw;
	const n = parseLooseNumber(raw);
	if (raw.trim() === "" || raw === "-" || raw.endsWith(".")) {
		emit("update:modelValue", raw.trim() === "" ? null : raw);
		return;
	}
	if (n != null) {
		emit("update:modelValue", props.fieldtype === "Int" ? Math.trunc(n) : n);
	}
}

function onBlur() {
	focused.value = false;
	const n = parseLooseNumber(draft.value);
	if (draft.value.trim() === "") {
		emit("update:modelValue", null);
		return;
	}
	if (n != null) {
		emit("update:modelValue", props.fieldtype === "Int" ? Math.trunc(n) : n);
	}
}
</script>
