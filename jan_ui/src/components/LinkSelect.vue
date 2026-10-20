<template>
	<div class="relative">
		<input
			v-model="query"
			type="text"
			class="w-full rounded-lg border border-outline-gray-2 bg-surface-white px-3 py-2 text-sm text-ink-gray-8 outline-none focus:border-outline-gray-4"
			:placeholder="placeholder || `Search ${doctype}…`"
			:disabled="disabled"
			@focus="open = true"
			@input="onInput"
		/>
		<ul
			v-if="open && (options.length || loading)"
			class="absolute z-20 mt-1 max-h-56 w-full overflow-auto rounded-lg border border-outline-gray-2 bg-surface-white shadow-lg"
		>
			<li v-if="loading" class="px-3 py-2 text-sm text-ink-gray-5">Searching…</li>
			<li
				v-for="opt in options"
				:key="opt.value"
				class="cursor-pointer px-3 py-2 text-sm hover:bg-surface-gray-2"
				@mousedown.prevent="select(opt)"
			>
				<div class="font-medium text-ink-gray-8">{{ opt.value }}</div>
				<div v-if="opt.description" class="text-xs text-ink-gray-5">{{ opt.description }}</div>
			</li>
			<li v-if="!loading && !options.length" class="px-3 py-2 text-sm text-ink-gray-5">No matches</li>
		</ul>
	</div>
</template>

<script setup lang="ts">
import { onMounted, onUnmounted, ref, watch } from "vue";
import { apiLinkSearch, useJanCall } from "../utils/janApi";

const props = defineProps<{
	modelValue?: string | null;
	doctype: string;
	placeholder?: string;
	disabled?: boolean;
	referenceDoctype?: string;
	filters?: unknown;
}>();

const emit = defineEmits<{ "update:modelValue": [string] }>();

const call = useJanCall();
const query = ref(props.modelValue || "");
const open = ref(false);
const loading = ref(false);
const options = ref<Array<{ value: string; description?: string }>>([]);
let timer: ReturnType<typeof setTimeout> | null = null;

watch(
	() => props.modelValue,
	(v) => {
		if (v !== query.value) query.value = v || "";
	},
);

function onInput() {
	emit("update:modelValue", query.value);
	if (timer) clearTimeout(timer);
	timer = setTimeout(() => void search(), 250);
}

async function search() {
	if (!props.doctype) return;
	loading.value = true;
	open.value = true;
	try {
		const res = await apiLinkSearch(
			call,
			props.doctype,
			query.value || "",
			props.filters,
			props.referenceDoctype,
		);
		options.value = (res || []).map((r) => ({
			value: r.value,
			description: r.description || r.label,
		}));
	} catch {
		options.value = [];
	} finally {
		loading.value = false;
	}
}

function select(opt: { value: string; description?: string }) {
	query.value = opt.value;
	emit("update:modelValue", opt.value);
	open.value = false;
}

function onDocClick(e: MouseEvent) {
	const t = e.target as HTMLElement;
	if (!t.closest?.(".relative")) open.value = false;
}

onMounted(() => document.addEventListener("click", onDocClick));
onUnmounted(() => document.removeEventListener("click", onDocClick));
</script>
