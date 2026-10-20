import type { JanCall } from "./call";
import { useJanCall } from "./call";

export { useJanCall };

const API = "vsd_jan_integration.api";

export type VehicleRow = {
	name: string;
	item_name?: string;
	custom_chassis_no?: string;
	custom_maker?: string;
	custom_model?: string;
	custom_new_stock_id?: string;
	custom_bl?: string;
	custom_price?: number;
	custom_m3?: number;
	custom_cost?: number;
	modified?: string;
};

export type DashboardStats = {
	vehicles: number;
	import_files: number;
	open_ifcvs: number;
	submitted_ifcvs: number;
	recent_import_files: Array<{ name: string; bl_number?: string; modified?: string }>;
};

export type JanSection = {
	doctype: string;
	slug: string;
	title: string;
	section?: string;
	is_tree?: boolean;
	is_single?: boolean;
	can_create: boolean;
	can_write: boolean;
};

export type StandardFilter = {
	fieldname: string;
	label: string;
	fieldtype: string;
	options?: string;
	condition?: string;
};

export type DocMeta = {
	doctype: string;
	slug: string;
	title: string;
	is_submittable: number;
	is_tree?: boolean;
	is_single?: boolean;
	title_field?: string;
	nsm_parent_field?: string;
	fields: Array<Record<string, unknown>>;
	list_fields: string[];
	standard_filters?: StandardFilter[];
	page_size_options?: number[];
	child_tables: Record<string, { doctype: string; fields: Array<Record<string, unknown>>; title_field?: string }>;
	section?: string;
	permissions: Record<string, boolean>;
};

export async function apiDashboard(call: JanCall) {
	return (await call(`${API}.vehicles.get_dashboard_stats`)) as DashboardStats;
}

export async function apiListVehicles(
	call: JanCall,
	params: { search?: string; limit?: number; start?: number } = {},
) {
	return (await call(`${API}.vehicles.list_vehicles`, params as Record<string, unknown>)) as {
		vehicles: VehicleRow[];
		total: number;
	};
}

export async function apiGetVehicle(call: JanCall, item: string) {
	return (await call(`${API}.vehicles.get_vehicle`, { item })) as Record<string, unknown>;
}

export async function apiUpdateVehicleSpecs(
	call: JanCall,
	item: string,
	fields: Record<string, unknown>,
) {
	return (await call(`${API}.vehicles.update_vehicle_specs`, {
		item,
		fields: JSON.stringify(fields),
	})) as Record<string, unknown>;
}

export async function apiGetOrCreateCarCosting(call: JanCall, item: string) {
	return (await call(`${API}.car_costing.get_or_create`, { item })) as {
		name: string;
		doc: Record<string, unknown>;
	};
}

export async function apiGetCarCosting(call: JanCall, name: string) {
	return (await call(`${API}.car_costing.get_car_costing`, { name })) as Record<string, unknown>;
}

export async function apiSaveCarCosting(call: JanCall, doc: Record<string, unknown>) {
	return (await call(`${API}.car_costing.save_car_costing`, {
		doc: JSON.stringify(doc),
	})) as Record<string, unknown>;
}

export async function apiFetchFx(call: JanCall, docname: string, costing_date?: string) {
	return (await call(`${API}.car_costing.fetch_exchange_rates`, {
		docname,
		costing_date,
	})) as { exchange_rate: number; yen_exchange_rate: number };
}

export async function apiRecalculateCarCosting(call: JanCall, docname: string) {
	return (await call(`${API}.car_costing.recalculate`, { docname })) as Record<string, unknown>;
}

export async function apiLoadFromItem(call: JanCall, docname: string, item: string) {
	return (await call(`${API}.car_costing.load_from_item`, { docname, item })) as string;
}

export async function apiListImportFiles(
	call: JanCall,
	params: { search?: string; limit?: number; start?: number } = {},
) {
	return (await call(`${API}.import_files.list_import_files`, params as Record<string, unknown>)) as {
		import_files: Array<Record<string, unknown>>;
		total: number;
	};
}

export async function apiGetImportFile(call: JanCall, name: string) {
	return (await call(`${API}.import_files.get_import_file`, { name })) as Record<string, unknown>;
}

export async function apiGetIfcv(call: JanCall, name: string) {
	return (await call(`${API}.ifcv.get_ifcv`, { name })) as Record<string, unknown>;
}

export async function apiGetVehicleLedger(call: JanCall, name: string, item: string) {
	return (await call(`${API}.ifcv.get_vehicle_ledger`, { name, item })) as Record<string, unknown>;
}

export async function apiReloadIfcv(call: JanCall, name: string) {
	return (await call(`${API}.ifcv.reload_from_import_file`, { name })) as Record<string, unknown>;
}

/* ---- Generic DocType / Reports / Excel Importer ---- */

export async function apiListJanSections(call: JanCall) {
	return (await call(`${API}.docs.list_jan_sections`)) as { sections: JanSection[] };
}

export async function apiGetDocMeta(call: JanCall, slug: string) {
	return (await call(`${API}.docs.get_meta`, { slug })) as DocMeta;
}

export async function apiListDocs(
	call: JanCall,
	slug: string,
	params: {
		search?: string;
		limit?: number;
		start?: number;
		filters?: unknown;
		order_by?: string;
		order_field?: string;
		order_dir?: string;
	} = {},
) {
	const { filters, ...rest } = params;
	return (await call(`${API}.docs.list_docs`, {
		slug,
		...rest,
		filters: filters != null ? JSON.stringify(filters) : undefined,
	})) as {
		doctype: string;
		rows: Array<Record<string, unknown>>;
		total: number;
		fields: string[];
		page_size_options?: number[];
		start?: number;
		limit?: number;
	};
}

export async function apiGetDoc(call: JanCall, slug: string, name: string) {
	return (await call(`${API}.docs.get_doc`, { slug, name })) as Record<string, unknown>;
}

export async function apiSaveDoc(call: JanCall, slug: string, doc: Record<string, unknown>) {
	return (await call(`${API}.docs.save_doc`, {
		slug,
		doc: JSON.stringify(doc),
	})) as Record<string, unknown>;
}

export async function apiSubmitDoc(call: JanCall, slug: string, name: string) {
	return (await call(`${API}.docs.submit_doc`, { slug, name })) as Record<string, unknown>;
}

export async function apiCancelDoc(call: JanCall, slug: string, name: string) {
	return (await call(`${API}.docs.cancel_doc`, { slug, name })) as Record<string, unknown>;
}

export async function apiAmendDoc(call: JanCall, slug: string, name: string) {
	return (await call(`${API}.docs.amend_doc`, { slug, name })) as Record<string, unknown>;
}

export async function apiLinkSearch(
	call: JanCall,
	doctype: string,
	txt: string,
	filters?: unknown,
	reference_doctype?: string,
) {
	return (await call(`${API}.docs.link_search`, {
		doctype,
		txt,
		filters: filters ? JSON.stringify(filters) : undefined,
		reference_doctype,
		page_length: 20,
	})) as Array<{ value: string; description?: string; label?: string }>;
}

export async function apiListCompanies(call: JanCall) {
	return (await call(`${API}.docs.list_companies`)) as { companies: string[]; default: string };
}

export async function apiGetAccountChildren(
	call: JanCall,
	company: string,
	parent?: string,
	is_root = false,
) {
	return (await call(`${API}.docs.get_account_children`, {
		company,
		parent: parent || "",
		is_root: is_root ? 1 : 0,
	})) as { nodes: Array<Record<string, unknown>>; company: string; parent: string };
}

export async function apiAddAccount(
	call: JanCall,
	payload: {
		company: string;
		parent_account: string;
		account_name: string;
		account_number?: string;
		is_group?: number;
		account_type?: string;
		root_type?: string;
		account_currency?: string;
	},
) {
	return (await call(`${API}.docs.add_account`, payload as Record<string, unknown>)) as { name: string };
}

export async function apiRebuildAccountTree(call: JanCall, company?: string) {
	return (await call(`${API}.docs.rebuild_account_tree`, { company })) as { ok: boolean };
}

export async function apiListReports(
	call: JanCall,
	params: { search?: string; limit?: number; start?: number } = {},
) {
	return (await call(`${API}.reports.list_reports`, params as Record<string, unknown>)) as {
		reports: Array<Record<string, unknown>>;
		total: number;
	};
}

export async function apiGetReportMeta(call: JanCall, report_name: string) {
	return (await call(`${API}.reports.get_report_meta`, { report_name })) as Record<string, unknown>;
}

export async function apiRunReport(
	call: JanCall,
	report_name: string,
	filters: Record<string, unknown> = {},
	opts: { ignore_prepared_report?: boolean; prepared_report_name?: string } = {},
) {
	return (await call(`${API}.reports.run_report`, {
		report_name,
		filters: JSON.stringify(filters),
		ignore_prepared_report: opts.ignore_prepared_report ? 1 : 0,
		prepared_report_name: opts.prepared_report_name,
	})) as {
		columns: Array<Record<string, unknown>>;
		result: Array<Record<string, unknown>>;
		prepared_report?: boolean;
		doc?: Record<string, unknown> | null;
		message?: unknown;
	};
}

export async function apiGeneratePreparedReport(
	call: JanCall,
	report_name: string,
	filters: Record<string, unknown> = {},
) {
	return (await call(`${API}.reports.generate_prepared_report`, {
		report_name,
		filters: JSON.stringify(filters),
	})) as { name: string };
}

export async function apiListPreparedReports(
	call: JanCall,
	report_name: string,
	filters: Record<string, unknown> = {},
) {
	return (await call(`${API}.reports.list_prepared_reports`, {
		report_name,
		filters: JSON.stringify(filters),
	})) as { prepared_reports: Array<Record<string, unknown>> };
}

export async function apiRunCostingReport(call: JanCall, filters: Record<string, unknown> = {}) {
	return (await call(`${API}.costing_report.run`, {
		filters: JSON.stringify(filters),
	})) as { columns: Array<Record<string, unknown>>; result: Array<Record<string, unknown>> };
}

export async function apiRunSaleReport(call: JanCall, filters: Record<string, unknown> = {}) {
	return (await call(`${API}.sale_report.run`, {
		filters: JSON.stringify(filters),
	})) as { columns: Array<Record<string, unknown>>; result: Array<Record<string, unknown>> };
}

export async function apiListImporters(
	call: JanCall,
	params: { search?: string; limit?: number; start?: number } = {},
) {
	return (await call(`${API}.excel_importer.list_importers`, params as Record<string, unknown>)) as {
		importers: Array<Record<string, unknown>>;
		total: number;
	};
}

export async function apiGetImporter(call: JanCall, name: string) {
	return (await call(`${API}.excel_importer.get_importer`, { name })) as Record<string, unknown>;
}

export async function apiSaveImporter(call: JanCall, doc: Record<string, unknown>) {
	return (await call(`${API}.excel_importer.save_importer`, {
		doc: JSON.stringify(doc),
	})) as Record<string, unknown>;
}

export async function apiStartImport(call: JanCall, docname: string, retry_failed_only = false) {
	return (await call(`${API}.excel_importer.start_import`, {
		docname,
		retry_failed_only,
	})) as Record<string, unknown>;
}

export async function apiGetImportProgress(call: JanCall, docname: string) {
	return (await call(`${API}.excel_importer.get_progress`, { docname })) as Record<string, unknown>;
}
