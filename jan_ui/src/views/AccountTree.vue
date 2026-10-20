<template>
	<div class="p-6">
		<div class="mb-6 flex flex-wrap items-end justify-between gap-4">
			<div>
				<h1 class="text-2xl font-semibold text-ink-gray-8">Chart of Accounts</h1>
				<p class="mt-1 text-sm text-ink-gray-5">Tree view · Company filter · Add child · Rebuild</p>
			</div>
			<div class="flex flex-wrap items-center gap-2">
				<button
					type="button"
					class="rounded-lg border border-outline-gray-2 px-3 py-2 text-sm"
					@click="$router.push('/docs/accounts')"
				>
					List view
				</button>
				<button
					type="button"
					class="rounded-lg border border-outline-gray-2 px-3 py-2 text-sm"
					:disabled="rebuilding"
					@click="rebuild"
				>
					{{ rebuilding ? "Rebuilding…" : "Rebuild tree" }}
				</button>
				<button
					type="button"
					class="rounded-lg border border-outline-gray-2 px-3 py-2 text-sm"
					@click="expandAll"
				>
					Expand all
				</button>
				<button
					type="button"
					class="rounded-lg border border-outline-gray-2 px-3 py-2 text-sm"
					@click="collapseAll"
				>
					Collapse
				</button>
			</div>
		</div>

		<div class="mb-4 flex flex-wrap items-end gap-3">
			<div class="min-w-[200px]">
				<label class="mb-1 block text-xs font-medium text-ink-gray-5">Company</label>
				<select
					v-model="company"
					class="w-full rounded-lg border border-outline-gray-2 px-3 py-2 text-sm"
					@change="onCompanyChange"
				>
					<option v-for="c in companies" :key="c" :value="c">{{ c }}</option>
				</select>
			</div>
		</div>

		<div v-if="error" class="mb-4 rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-800">
			{{ error }}
		</div>
		<div v-if="message" class="mb-4 rounded-lg border border-green-200 bg-green-50 p-3 text-sm text-green-800">
			{{ message }}
		</div>

		<div class="rounded-xl border border-outline-gray-2 p-3">
			<div v-if="loading" class="py-8 text-center text-ink-gray-5">Loading…</div>
			<ul v-else class="space-y-0.5">
				<li v-for="node in rootNodes" :key="String(node.value)">
					<AccountTreeNode
						:node="node"
						:company="company"
						:depth="0"
						:expanded="expanded"
						@toggle="toggle"
						@add-child="openAdd"
						@edit="editAccount"
						@loaded="onChildrenLoaded"
					/>
				</li>
				<li v-if="!rootNodes.length" class="py-8 text-center text-sm text-ink-gray-5">
					No accounts for this company
				</li>
			</ul>
		</div>

		<!-- Add child dialog -->
		<div
			v-if="addOpen"
			class="fixed inset-0 z-40 flex items-center justify-center bg-black/40 p-4"
			@click.self="addOpen = false"
		>
			<div class="w-full max-w-md rounded-xl bg-surface-white p-5 shadow-xl">
				<h3 class="mb-4 text-lg font-semibold text-ink-gray-8">Add child under {{ addParent }}</h3>
				<div class="space-y-3">
					<div>
						<label class="mb-1 block text-xs font-medium text-ink-gray-5">Account Name</label>
						<input v-model="addForm.account_name" class="w-full rounded-lg border border-outline-gray-2 px-3 py-2 text-sm" />
					</div>
					<div>
						<label class="mb-1 block text-xs font-medium text-ink-gray-5">Account Number</label>
						<input v-model="addForm.account_number" class="w-full rounded-lg border border-outline-gray-2 px-3 py-2 text-sm" />
					</div>
					<label class="flex items-center gap-2 text-sm">
						<input v-model="addForm.is_group" type="checkbox" :true-value="1" :false-value="0" />
						Is Group
					</label>
					<div>
						<label class="mb-1 block text-xs font-medium text-ink-gray-5">Account Type</label>
						<input v-model="addForm.account_type" class="w-full rounded-lg border border-outline-gray-2 px-3 py-2 text-sm" />
					</div>
				</div>
				<div class="mt-5 flex justify-end gap-2">
					<button type="button" class="rounded-lg border border-outline-gray-2 px-3 py-2 text-sm" @click="addOpen = false">
						Cancel
					</button>
					<button
						type="button"
						class="rounded-lg bg-ink-gray-9 px-3 py-2 text-sm font-medium text-white"
						:disabled="adding"
						@click="submitAdd"
					>
						{{ adding ? "Saving…" : "Create" }}
					</button>
				</div>
			</div>
		</div>
	</div>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from "vue";
import { useRouter } from "vue-router";
import AccountTreeNode from "../components/AccountTreeNode.vue";
import {
	apiAddAccount,
	apiGetAccountChildren,
	apiListCompanies,
	apiRebuildAccountTree,
	useJanCall,
} from "../utils/janApi";

const call = useJanCall();
const router = useRouter();

const companies = ref<string[]>([]);
const company = ref("");
const rootNodes = ref<Array<Record<string, unknown>>>([]);
const expanded = reactive<Record<string, boolean>>({});
const childrenCache = reactive<Record<string, Array<Record<string, unknown>>>>({});
const loading = ref(true);
const rebuilding = ref(false);
const error = ref("");
const message = ref("");

const addOpen = ref(false);
const addParent = ref("");
const adding = ref(false);
const addForm = reactive({
	account_name: "",
	account_number: "",
	is_group: 0,
	account_type: "",
});

async function loadCompanies() {
	const res = await apiListCompanies(call);
	companies.value = res.companies || [];
	company.value = res.default || companies.value[0] || "";
}

async function loadRoots() {
	if (!company.value) return;
	loading.value = true;
	error.value = "";
	try {
		const res = await apiGetAccountChildren(call, company.value, "", true);
		rootNodes.value = res.nodes || [];
		for (const n of rootNodes.value) {
			const v = String(n.value);
			if (n.expandable && expanded[v] == null) expanded[v] = true;
		}
	} catch (e: unknown) {
		error.value = e instanceof Error ? e.message : String(e);
	} finally {
		loading.value = false;
	}
}

function onCompanyChange() {
	Object.keys(expanded).forEach((k) => delete expanded[k]);
	Object.keys(childrenCache).forEach((k) => delete childrenCache[k]);
	void loadRoots();
}

function toggle(value: string) {
	expanded[value] = !expanded[value];
}

function onChildrenLoaded(parent: string, nodes: Array<Record<string, unknown>>) {
	childrenCache[parent] = nodes;
}

function expandAll() {
	for (const n of rootNodes.value) {
		expanded[String(n.value)] = true;
	}
	for (const k of Object.keys(childrenCache)) {
		expanded[k] = true;
		for (const n of childrenCache[k] || []) {
			if (n.expandable) expanded[String(n.value)] = true;
		}
	}
}

function collapseAll() {
	Object.keys(expanded).forEach((k) => {
		expanded[k] = false;
	});
}

function openAdd(parent: string) {
	addParent.value = parent;
	addForm.account_name = "";
	addForm.account_number = "";
	addForm.is_group = 0;
	addForm.account_type = "";
	addOpen.value = true;
}

async function submitAdd() {
	if (!addForm.account_name.trim()) {
		error.value = "Account Name is required";
		return;
	}
	adding.value = true;
	error.value = "";
	try {
		await apiAddAccount(call, {
			company: company.value,
			parent_account: addParent.value,
			account_name: addForm.account_name.trim(),
			account_number: addForm.account_number || undefined,
			is_group: addForm.is_group,
			account_type: addForm.account_type || undefined,
		});
		addOpen.value = false;
		message.value = "Account created";
		Object.keys(childrenCache).forEach((k) => delete childrenCache[k]);
		await loadRoots();
	} catch (e: unknown) {
		error.value = e instanceof Error ? e.message : String(e);
	} finally {
		adding.value = false;
	}
}

function editAccount(name: string) {
	router.push(`/docs/accounts/${encodeURIComponent(name)}`);
}

async function rebuild() {
	rebuilding.value = true;
	error.value = "";
	message.value = "";
	try {
		await apiRebuildAccountTree(call, company.value);
		message.value = "Account tree rebuilt";
		Object.keys(childrenCache).forEach((k) => delete childrenCache[k]);
		await loadRoots();
	} catch (e: unknown) {
		error.value = e instanceof Error ? e.message : String(e);
	} finally {
		rebuilding.value = false;
	}
}

onMounted(async () => {
	try {
		await loadCompanies();
		await loadRoots();
	} catch (e: unknown) {
		error.value = e instanceof Error ? e.message : String(e);
		loading.value = false;
	}
});
</script>
