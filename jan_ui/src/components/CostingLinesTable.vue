<template>
	<div class="overflow-hidden rounded-lg border border-outline-gray-2">
		<table class="w-full text-left text-xs">
			<thead class="bg-surface-gray-2 text-ink-gray-5">
				<tr>
					<th class="px-3 py-2 font-medium">Code</th>
					<th class="px-3 py-2 font-medium">Head</th>
					<th class="px-3 py-2 font-medium text-right">Expected</th>
					<th class="px-3 py-2 font-medium text-right">Actual</th>
				</tr>
			</thead>
			<tbody class="divide-y divide-outline-gray-2">
				<tr v-if="!rows.length">
					<td colspan="4" class="px-3 py-4 text-center text-ink-gray-5">No lines</td>
				</tr>
				<tr v-for="(r, i) in rows" :key="i">
					<td class="px-3 py-2 text-ink-gray-6">{{ r.costing_code || "—" }}</td>
					<td class="px-3 py-2 text-ink-gray-8">{{ r.costing_head || r.costing || "—" }}</td>
					<td class="px-3 py-2 text-right tabular-nums">{{ fmt(r.expected_amount) }}</td>
					<td class="px-3 py-2 text-right tabular-nums">{{ fmt(r.actual_amount) }}</td>
				</tr>
			</tbody>
		</table>
	</div>
</template>

<script setup lang="ts">
import { formatNumber } from "../utils/format";

defineProps<{ rows: Array<Record<string, unknown>> }>();

function fmt(n: unknown) {
	if (n == null || n === "") return "—";
	return formatNumber(n, "Currency");
}
</script>
