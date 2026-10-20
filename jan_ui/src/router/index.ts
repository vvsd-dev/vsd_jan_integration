import { createRouter, createWebHistory } from "vue-router";
import { JAN_UI_BASE } from "../constants";
import { getBootUser } from "../utils/session";

const router = createRouter({
	history: createWebHistory(JAN_UI_BASE),
	routes: [
		{
			path: "/login",
			name: "Login",
			component: () => import("../views/Login.vue"),
			meta: { public: true },
		},
		{ path: "/", redirect: "/dashboard" },
		{
			path: "/dashboard",
			name: "Dashboard",
			component: () => import("../views/Dashboard.vue"),
		},
		{
			path: "/vehicles",
			name: "Vehicles",
			component: () => import("../views/Vehicles.vue"),
		},
		{
			path: "/vehicles/:item",
			name: "VehicleDetail",
			component: () => import("../views/VehicleDetail.vue"),
			props: true,
		},
		{
			path: "/vehicles/:item/costing",
			name: "CarCosting",
			component: () => import("../views/CarCosting.vue"),
			props: true,
		},
		{
			path: "/import-files",
			name: "ImportFiles",
			component: () => import("../views/ImportFiles.vue"),
		},
		{
			path: "/import-files/:name",
			name: "ImportFileDetail",
			component: () => import("../views/ImportFileDetail.vue"),
			props: true,
		},
		{
			path: "/ifcv/:name",
			name: "IfcvDetail",
			component: () => import("../views/IfcvDetail.vue"),
			props: true,
		},
		{
			path: "/docs/:slug",
			name: "DocList",
			component: () => import("../views/DocList.vue"),
			props: true,
		},
		{
			path: "/docs/:slug/:name",
			name: "DocForm",
			component: () => import("../views/DocForm.vue"),
			props: true,
		},
		{
			path: "/accounting/accounts-tree",
			name: "AccountTree",
			component: () => import("../views/AccountTree.vue"),
		},
		{
			path: "/reports",
			name: "Reports",
			component: () => import("../views/Reports.vue"),
		},
		{
			path: "/reports/jan-bl-costing",
			name: "JanBlCosting",
			component: () => import("../views/ReportRunner.vue"),
			props: { reportName: "jan-bl-costing" },
		},
		{
			path: "/reports/jan-sale-report",
			name: "JanSaleReport",
			component: () => import("../views/ReportRunner.vue"),
			props: { reportName: "jan-sale-report" },
		},
		{
			path: "/reports/run/:reportName",
			name: "ReportRunner",
			component: () => import("../views/ReportRunner.vue"),
			props: true,
		},
		{
			path: "/excel-importer",
			name: "ExcelImporterList",
			component: () => import("../views/ExcelImporterList.vue"),
		},
		{
			path: "/excel-importer/:name",
			name: "ExcelImporterDetail",
			component: () => import("../views/ExcelImporterDetail.vue"),
			props: true,
		},
	],
});

router.beforeEach((to) => {
	if (to.meta.public) return true;
	if (!getBootUser()) {
		return { name: "Login", query: { redirect: to.fullPath } };
	}
	return true;
});

export default router;
