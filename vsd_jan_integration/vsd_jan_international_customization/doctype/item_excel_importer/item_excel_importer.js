// Copyright (c) 2026, VV Systems Developer LTD and contributors
// For license information, please see license.txt

frappe.ui.form.on('Item Excel Importer', {
	refresh: function(frm) {
		frm.trigger('setup_realtime_listener');
		frm.trigger('render_progress_html');

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
	},

	setup_realtime_listener: function(frm) {
		if (frm.doc.name && (frm.doc.import_status === 'In Progress' || frm.doc.import_status === 'Queued')) {
			frappe.realtime.off('item_excel_import_progress_' + frm.doc.name);
			frappe.realtime.on('item_excel_import_progress_' + frm.doc.name, function(data) {
				if (data) {
					frm.doc.processed_invoices = data.processed_invoices || 0;
					frm.doc.total_invoices = data.total_invoices || 0;
					frm.doc.processed_cars = data.processed_cars || 0;
					frm.doc.total_cars = data.total_cars || 0;
					if (data.estimated_time) {
						frm.doc.estimated_time = data.estimated_time;
					}
					frm.active_step_text = data.active_step_text || '';
					frm.progress_percent = data.percent || 0;
					frm.trigger('render_progress_html');

					if (data.status && data.status !== 'In Progress' && data.status !== 'Queued') {
						frm.reload_doc();
					}
				}
			});
		}
	},

	render_progress_html: function(frm) {
		if (!frm.fields_dict.progress_html) return;
		var status = frm.doc.import_status;
		if (!status || status === 'Pending') {
			frm.fields_dict.progress_html.set_value('');
			return;
		}

		var percent = frm.progress_percent || 0;
		if (status === 'Completed') percent = 100;

		var step_text = frm.active_step_text || (status === 'Completed' ? 'Import completed successfully.' : 'Processing import...');
		var indicator = 'info';
		var bg_class = 'bg-primary';

		if (status === 'Completed') {
			indicator = 'success';
			bg_class = 'bg-success';
		} else if (status === 'Completed with Errors') {
			indicator = 'warning';
			bg_class = 'bg-warning';
		} else if (status === 'Failed') {
			indicator = 'danger';
			bg_class = 'bg-danger';
		}

		var is_active = (status === 'In Progress' || status === 'Queued');
		var spinner_html = is_active ? '<i class="fa fa-circle-o-notch fa-spin" style="margin-right: 6px; color: #2563eb;"></i>' : '';

		var html = `
			<div class="import-progress-card" style="border: 1px solid #e2e8f0; border-radius: 10px; padding: 18px; margin-bottom: 20px; background-color: #ffffff; box-shadow: 0 1px 3px rgba(0,0,0,0.05);">
				<div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px;">
					<strong style="font-size: 14px; color: #1e293b;">Import Status: <span class="indicator-pill ${indicator}">${status}</span></strong>
					<span style="font-weight: 700; font-size: 14px; color: #2563eb;">${percent}%</span>
				</div>
				<div class="progress" style="height: 14px; border-radius: 7px; background-color: #f1f5f9; overflow: hidden; margin-bottom: 12px;">
					<div class="progress-bar ${bg_class} ${is_active ? 'progress-bar-striped progress-bar-animated' : ''}" role="progressbar" style="width: ${percent}%;"></div>
				</div>
				<div style="font-size: 13px; color: #334155; margin-bottom: 12px; font-weight: 500; display: flex; align-items: center;">
					${spinner_html}
					<span>${step_text}</span>
				</div>
				<div style="display: flex; flex-wrap: wrap; gap: 20px; font-size: 12px; color: #64748b; border-top: 1px solid #f1f5f9; padding-top: 10px;">
					<div><i class="fa fa-file-text-o" style="margin-right: 4px;"></i><strong>Invoices:</strong> ${frm.doc.processed_invoices || 0} / ${frm.doc.total_invoices || 0}</div>
					<div><i class="fa fa-car" style="margin-right: 4px;"></i><strong>Cars:</strong> ${frm.doc.processed_cars || 0} / ${frm.doc.total_cars || 0}</div>
					<div><i class="fa fa-clock-o" style="margin-right: 4px;"></i><strong>Time Elapsed:</strong> ${frm.doc.estimated_time || '0s'}</div>
				</div>
			</div>
		`;

		frm.fields_dict.progress_html.set_value(html);
	}
});

