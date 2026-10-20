<template>
	<div class="p-6">
		<div class="mb-6">
			<button type="button" class="mb-2 text-sm text-ink-gray-5 hover:text-ink-gray-8" @click="$router.push('/import-files')">
				← Import Files
			</button>
			<h1 class="text-2xl font-semibold text-ink-gray-8">{{ name }}</h1>
			<p class="mt-1 text-sm text-ink-gray-5">
				BL {{ doc.bl_number || "—" }} · Invoice {{ doc.supplier_invoice_no || "—" }}
			</p>
		</div>

		<div v-if="error" class="mb-4 rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-800">{{ error }}</div>
		<div v-if="loading" class="py-12 text-center text-ink-gray-5">Loading…</div>

		<template v-else>
			<section class="mb-6 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
				<div class="rounded-xl border border-outline-gray-2 p-4">
					<div class="text-xs text-ink-gray-5">Vehicles</div>
					<div class="mt-1 text-2xl font-semibold">{{ doc.vehicle_count || 0 }}</div>
				</div>
				<div class="rounded-xl border border-outline-gray-2 p-4">
					<div class="text-xs text-ink-gray-5">Invoice</div>
					<div class="mt-1 text-sm font-medium">{{ doc.supplier_invoice_no || "—" }}</div>
				</div>
				<div class="rounded-xl border border-outline-gray-2 p-4 sm:col-span-2">
					<div class="text-xs text-ink-gray-5">Supplier</div>
					<div class="mt-1 text-sm font-medium">{{ doc.supplier_name || doc.supplier || "—" }}</div>
				</div>
			</section>

			<section class="rounded-xl border border-outline-gray-2">
				<div class="border-b border-outline-gray-2 px-4 py-3">
					<h2 class="text-sm font-semibold text-ink-gray-8">Import File Cost Vouchers</h2>
				</div>
				<ul v-if="(doc.ifcvs as any[])?.length" class="divide-y divide-outline-gray-2">
					<li v-for="ifcv in (doc.ifcvs as any[])" :key="ifcv.name">
						<router-link
							:to="`/ifcv/${encodeURIComponent(ifcv.name)}`"
							class="flex items-center justify-between px-4 py-3 hover:bg-surface-gray-2"
						>
							<span class="font-medium text-ink-gray-8">{{ ifcv.name }}</span>
							<span class="text-xs text-ink-gray-5">
								{{ ifcv.docstatus === 1 ? "Submitted" : ifcv.docstatus === 2 ? "Cancelled" : "Draft" }}
								· {{ ifcv.posting_date || "" }}
							</span>
						</router-link>
					</li>
				</ul>
				<div v-else class="px-4 py-8 text-center text-sm text-ink-gray-5">No Import File Cost Vouchers linked</div>
			</section>
		</template>
	</div>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from "vue";
import { apiGetImportFile, useJanCall } from "../utils/janApi";

const props = defineProps<{ name: string }>();
const call = useJanCall();
const loading = ref(true);
const error = ref("");
const doc = reactive<Record<string, unknown>>({});

onMounted(async () => {
	try {
		const data = await apiGetImportFile(call, props.name);
		Object.assign(doc, data);
	} catch (e: unknown) {
		error.value = e instanceof Error ? e.message : String(e);
	} finally {
		loading.value = false;
	}
});
</script>
