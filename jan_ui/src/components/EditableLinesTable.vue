<template>
	<div class="overflow-hidden rounded-lg border border-outline-gray-2">
		<table class="w-full text-left text-xs">
			<thead class="bg-surface-gray-2 text-ink-gray-5">
				<tr>
					<th class="px-3 py-2 font-medium">Code</th>
					<th class="px-3 py-2 font-medium">Head</th>
					<th class="px-3 py-2 font-medium text-right">Expected</th>
				</tr>
			</thead>
			<tbody class="divide-y divide-outline-gray-2">
				<tr v-if="!modelValue.length">
					<td colspan="3" class="px-3 py-4 text-center text-ink-gray-5">No lines</td>
				</tr>
				<tr v-for="(r, i) in modelValue" :key="i">
					<td class="px-3 py-2 text-ink-gray-6">{{ r.costing_code || "—" }}</td>
					<td class="px-3 py-2">{{ r.costing_head || "—" }}</td>
					<td class="px-3 py-2 text-right">
						<input
							v-model.number="r.expected_amount"
							type="number"
							step="any"
							class="w-28 rounded border border-outline-gray-2 bg-transparent px-2 py-1 text-right tabular-nums"
						/>
					</td>
				</tr>
			</tbody>
		</table>
	</div>
</template>

<script setup lang="ts">
defineProps<{ modelValue: Record<string, any>[] }>();
defineEmits<{ "update:modelValue": [Record<string, any>[]] }>();
</script>
