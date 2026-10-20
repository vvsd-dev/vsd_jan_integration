<script setup lang="ts">
import { computed } from "vue";
import { useRouter } from "vue-router";
import { Sidebar } from "frappe-ui";
import UserDropdown from "./UserDropdown.vue";
import LucideLayoutDashboard from "~icons/lucide/layout-dashboard";
import LucideCar from "~icons/lucide/car";
import LucideFileStack from "~icons/lucide/file-stack";
import LucideFileSpreadsheet from "~icons/lucide/file-spreadsheet";
import LucideReceipt from "~icons/lucide/receipt";
import LucideShoppingCart from "~icons/lucide/shopping-cart";
import LucideArrowLeftRight from "~icons/lucide/arrow-left-right";
import LucideBookOpen from "~icons/lucide/book-open";
import LucideClipboardList from "~icons/lucide/clipboard-list";
import LucideUsers from "~icons/lucide/users";
import LucideTruck from "~icons/lucide/truck";
import LucideMapPin from "~icons/lucide/map-pin";
import LucideBarChart3 from "~icons/lucide/bar-chart-3";
import LucideUpload from "~icons/lucide/upload";
import LucideNetwork from "~icons/lucide/network";
import LucideList from "~icons/lucide/list";
import LucideCalculator from "~icons/lucide/calculator";
import LucideSettings from "~icons/lucide/settings";
import LucideTags from "~icons/lucide/tags";

const router = useRouter();

const sections = computed(() => [
	{
		label: "Operations",
		items: [
			{
				label: "Dashboard",
				icon: LucideLayoutDashboard,
				onClick: () => router.push("/dashboard"),
			},
			{
				label: "Vehicles",
				icon: LucideCar,
				onClick: () => router.push("/vehicles"),
			},
			{
				label: "Import Files",
				icon: LucideFileStack,
				onClick: () => router.push("/import-files"),
			},
			{
				label: "Excel Importer",
				icon: LucideUpload,
				onClick: () => router.push("/excel-importer"),
			},
		],
	},
	{
		label: "Costing",
		items: [
			{
				label: "Import Files",
				icon: LucideFileStack,
				onClick: () => router.push("/docs/import-files"),
			},
			{
				label: "Import File Cost Voucher",
				icon: LucideClipboardList,
				onClick: () => router.push("/docs/ifcvs"),
			},
			{
				label: "Car Costings",
				icon: LucideCalculator,
				onClick: () => router.push("/docs/car-costings"),
			},
			{
				label: "Costing",
				icon: LucideTags,
				onClick: () => router.push("/docs/costings"),
			},
			{
				label: "Costing Settings",
				icon: LucideSettings,
				onClick: () => router.push("/docs/costing-settings/Costing%20Settings"),
			},
			{
				label: "BL Costing Report",
				icon: LucideFileSpreadsheet,
				onClick: () => router.push("/reports/jan-bl-costing"),
			},
			{
				label: "Sale Report",
				icon: LucideReceipt,
				onClick: () => router.push("/reports/jan-sale-report"),
			},
		],
	},
	{
		label: "Accounting",
		items: [
			{
				label: "Chart of Accounts",
				icon: LucideNetwork,
				onClick: () => router.push("/accounting/accounts-tree"),
			},
			{
				label: "Accounts List",
				icon: LucideList,
				onClick: () => router.push("/docs/accounts"),
			},
			{
				label: "Purchase Invoices",
				icon: LucideShoppingCart,
				onClick: () => router.push("/docs/purchase-invoices"),
			},
			{
				label: "Sales Invoices",
				icon: LucideReceipt,
				onClick: () => router.push("/docs/sales-invoices"),
			},
			{
				label: "Stock Transfers",
				icon: LucideArrowLeftRight,
				onClick: () => router.push("/docs/stock-entries"),
			},
			{
				label: "Journal Entries",
				icon: LucideBookOpen,
				onClick: () => router.push("/docs/journal-entries"),
			},
		],
	},
	{
		label: "Masters",
		items: [
			{
				label: "Customers",
				icon: LucideUsers,
				onClick: () => router.push("/docs/customers"),
			},
			{
				label: "Suppliers",
				icon: LucideTruck,
				onClick: () => router.push("/docs/suppliers"),
			},
			{
				label: "Addresses",
				icon: LucideMapPin,
				onClick: () => router.push("/docs/addresses"),
			},
		],
	},
	{
		label: "Reports",
		items: [
			{
				label: "All Reports",
				icon: LucideBarChart3,
				onClick: () => router.push("/reports"),
			},
			{
				label: "BL Costing",
				icon: LucideFileSpreadsheet,
				onClick: () => router.push("/reports/jan-bl-costing"),
			},
			{
				label: "Sale Report",
				icon: LucideReceipt,
				onClick: () => router.push("/reports/jan-sale-report"),
			},
		],
	},
]);
</script>

<template>
	<Sidebar class="h-screen jan-app-sidebar" :sections="sections">
		<template #header>
			<UserDropdown />
		</template>
	</Sidebar>
</template>
