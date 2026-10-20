<template>
	<div>
		<div
			class="group flex items-center gap-1 rounded-md px-1 py-1 hover:bg-surface-gray-2"
			:style="{ paddingLeft: `${8 + depth * 16}px` }"
		>
			<button
				v-if="node.expandable"
				type="button"
				class="flex h-5 w-5 items-center justify-center text-ink-gray-5"
				@click="onToggle"
			>
				{{ isOpen ? "▾" : "▸" }}
			</button>
			<span v-else class="inline-block w-5" />
			<button
				type="button"
				class="min-w-0 flex-1 truncate text-left text-sm text-ink-gray-8"
				@click="emit('edit', String(node.value))"
			>
				{{ node.title || node.value }}
				<span v-if="node.root_type" class="ml-2 text-xs text-ink-gray-5">{{ node.root_type }}</span>
			</button>
			<button
				type="button"
				class="hidden text-xs text-ink-gray-5 group-hover:inline hover:text-ink-gray-8"
				@click="emit('add-child', String(node.value))"
			>
				+ Child
			</button>
		</div>
		<ul v-if="isOpen && node.expandable">
			<li
				v-if="loadingChildren"
				class="px-4 py-1 text-xs text-ink-gray-5"
				:style="{ paddingLeft: `${24 + depth * 16}px` }"
			>
				Loading…
			</li>
			<li v-for="child in children" :key="String(child.value)">
				<AccountTreeNode
					:node="child"
					:company="company"
					:depth="depth + 1"
					:expanded="expanded"
					@toggle="emit('toggle', $event)"
					@add-child="emit('add-child', $event)"
					@edit="emit('edit', $event)"
					@loaded="(p, n) => emit('loaded', p, n)"
				/>
			</li>
		</ul>
	</div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { apiGetAccountChildren, useJanCall } from "../utils/janApi";

const props = defineProps<{
	node: Record<string, unknown>;
	company: string;
	depth: number;
	expanded: Record<string, boolean>;
}>();

const emit = defineEmits<{
	toggle: [string];
	"add-child": [string];
	edit: [string];
	loaded: [string, Array<Record<string, unknown>>];
}>();

const call = useJanCall();
const children = ref<Array<Record<string, unknown>>>([]);
const loadingChildren = ref(false);
const fetched = ref(false);

const value = computed(() => String(props.node.value));
const isOpen = computed(() => !!props.expanded[value.value]);

async function fetchChildren() {
	if (fetched.value || !props.node.expandable) return;
	loadingChildren.value = true;
	try {
		const res = await apiGetAccountChildren(call, props.company, value.value, false);
		children.value = res.nodes || [];
		fetched.value = true;
		emit("loaded", value.value, children.value);
	} finally {
		loadingChildren.value = false;
	}
}

function onToggle() {
	emit("toggle", value.value);
}

watch(
	isOpen,
	(open) => {
		if (open) void fetchChildren();
	},
	{ immediate: true },
);
</script>
