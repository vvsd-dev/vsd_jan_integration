// Copyright (c) 2026, VV Systems Developer LTD and contributors
// For license information, please see license.txt

frappe.ui.form.on('Item Excel Importer', {
	refresh: function(frm) {
		if (!frm.is_new() && frm.doc.excel_file) {
			if (frm.doc.import_status !== 'Queued' && frm.doc.import_status !== 'In Progress') {
				frm.add_custom_button(__('Start Import'), function() {
					frappe.confirm(
						__('Are you sure you want to process and import items from this Excel file in the background?'),
						function() {
							frappe.call({
								method: 'vsd_jan_integration.vsd_jan_international_customization.doctype.item_excel_importer.item_excel_importer.enqueue_import',
								args: {
									docname: frm.doc.name,
									retry_failed_only: false
								},
								freeze: true,
								freeze_message: __('Queueing import job in background...'),
								callback: function(r) {
									if (!r.exc && r.message) {
										frappe.show_alert({
											message: __('Import job queued successfully.'),
											indicator: 'blue'
										});
										frm.reload_doc();
									}
								}
							});
						}
					);
				}).addClass('btn-primary');
			}

			// Add Export Errored Rows & Retry Failed buttons if previous run had errors / failed records
			var has_failed = frm.doc.failed_records && frm.doc.failed_records !== '[]' && frm.doc.failed_records !== '{}';
			if (has_failed) {
				frm.add_custom_button(__('Export Errored Rows'), function() {
					var url = frappe.urllib.get_full_url(
						'/api/method/vsd_jan_integration.vsd_jan_international_customization.doctype.item_excel_importer.item_excel_importer.download_errored_rows?docname=' + encodeURIComponent(frm.doc.name)
					);
					window.open(url);
				}).addClass('btn-secondary');
			}

			if (has_failed && (frm.doc.import_status === 'Completed with Errors' || frm.doc.import_status === 'Failed')) {
				frm.add_custom_button(__('Retry Failed'), function() {
					frappe.confirm(
						__('Are you sure you want to retry importing only the failed records?'),
						function() {
							frappe.call({
								method: 'vsd_jan_integration.vsd_jan_international_customization.doctype.item_excel_importer.item_excel_importer.enqueue_import',
								args: {
									docname: frm.doc.name,
									retry_failed_only: true
								},
								freeze: true,
								freeze_message: __('Queueing retry job...'),
								callback: function(r) {
									if (!r.exc && r.message) {
										frappe.show_alert({
											message: __('Retry job queued successfully.'),
											indicator: 'blue'
										});
										frm.reload_doc();
									}
								}
							});
						}
					);
				}).addClass('btn-danger');
			}
		}
	}
});
