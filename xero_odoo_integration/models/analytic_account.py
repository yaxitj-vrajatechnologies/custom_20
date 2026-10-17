import pprint
from odoo import models

class AnalyticAccount(models.Model):
    _inherit = "account.analytic.account"

    def action_xero_instance_for_analytics_account(self):
        return {
            'type': 'ir.actions.act_window',
            'name': 'Xero Instance Wizard',
            'res_model': 'xero.instance.wizard',
            'view_mode': 'form',
            'target': 'new',
        }

    def export_analytics_account(self,instance):
        log_id = self.env['xero.log.vts'].sudo().generate_xero_logs(
            xero_operation_name='tracking_category',
            xero_operation_type='export',
            instance=False,
            xero_operation_message='Export Tracking Category To Xero'
        )

        for analytic_account in self:
            existing_account_map = self.env['xero.analytic.account.map'].search([
                ('analytic_account_id','=',analytic_account.id),
                ('xero_instance_id','=',instance.id),
            ],limit=1)

            if existing_account_map:
                analytic_account.message_post(body=f"Skipping Already Exported Tracking Category:{analytic_account.name}")
                self.env['xero.log.vts.line'].sudo().generate_xero_process_line(
                    xero_operation_name ='tracking_category',
                    xero_operation_type='export',
                    instance=instance.id,
                    log_id=log_id,
                    xero_operation_message=f"Skipping Already Exported Tracking Category: {analytic_account.name}",
                    fault_operation=False
                )
                continue

            existing_plan_map = self.env['xero.analytic.account.map'].search([
                ('analytic_plan_id','=',analytic_account.plan_id.id),
                ('xero_instance_id','=',instance.id),
            ],limit=1)
            xero_plan_id = existing_plan_map.xero_analytic_plan_id

            if existing_plan_map:
                self.put_tracking_option(instance=instance,analytic_account=analytic_account,xero_plan_id=xero_plan_id,log_id=log_id,)
            else:
                payload = {
                    'Name': analytic_account.plan_id.name,
                }
                request_url = f"{instance.xero_base_url}/TrackingCategories"
                try:
                    data, status_code = self.env['xero.api.vts'].xero_put_request(
                        token=instance.access_token,
                        company_id=instance.tenant_id,
                        endpoint=request_url,
                        payload=payload
                    )
                    if status_code in (200, 201):
                        tracking_category_id = data['TrackingCategories'][0]['TrackingCategoryID']
                        analytic_account.message_post(body=f"Tracking Category Successfully exported to Xero: {analytic_account.plan_id.name}")
                        self.env['xero.log.vts.line'].sudo().generate_xero_process_line(
                            xero_operation_name='tracking_category',
                            xero_operation_type='export',
                            instance=instance.id,
                            xero_operation_message=f"Tracking Category Successfully exported to Xero: {analytic_account.plan_id.name}",
                            log_id=log_id,
                            fault_operation=False,
                        )
                        self.put_tracking_option(instance=instance,analytic_account = analytic_account,xero_plan_id=tracking_category_id,log_id=log_id)

                    else:
                        res_error = data.get('Message', data)
                        msg = f"Failed to export Tracking Category {analytic_account.plan_id.name} to Xero. Response: {res_error}"
                        analytic_account.message_post(body=msg)
                        self.env['xero.log.vts.line'].sudo().generate_xero_process_line(
                            xero_operation_name="tracking_category", xero_operation_type="export",
                            instance=instance.id, xero_operation_message=msg,
                            process_request_message=payload, process_response_message=data,
                            log_id=log_id, fault_operation=True)
                except Exception as e:
                    analytic_account.message_post(
                        body=f"Exception while exporting Tracking Category {analytic_account.plan_id.name} to Xero: {str(e)}")
                    self.env['xero.log.vts.line'].sudo().generate_xero_process_line(
                        xero_operation_name="tracking_category", xero_operation_type="export",
                        instance=instance.id, xero_operation_message=f"Exception: {str(e)}",
                        process_request_message=payload, process_response_message=str(e),
                        log_id=log_id, fault_operation=True)

    def put_tracking_option(self,instance,analytic_account,xero_plan_id,log_id,):
        payload = {
            'Name': analytic_account.name,
        }
        request_url = f"{instance.xero_base_url}/TrackingCategories/{xero_plan_id}/Options"

        try:
            data, status_code = self.env['xero.api.vts'].xero_put_request(
                token=instance.access_token,
                company_id=instance.tenant_id,
                endpoint=request_url,
                payload=payload
            )

            if status_code in (200, 201):
                option = data.get('Options', [])[0]

                analytic_map_object = self.env['xero.analytic.account.map']
                mapping_vals= {
                    'xero_instance_id': instance.id,
                    'analytic_account_id': analytic_account.id,
                    'analytic_plan_id': analytic_account.plan_id.id,
                    'xero_analytic_plan_id': xero_plan_id,
                    'xero_analytic_acc_id': option.get('TrackingOptionID'),
                    'xero_analytic_acc_name': option.get('Name'),
                    'xero_response': pprint.pformat(data),
                }
                analytic_map_object.create(mapping_vals)

                analytic_account.message_post(body=f"Tracking Options Successfully exported to Xero: {analytic_account.name}")
                self.env['xero.log.vts.line'].sudo().generate_xero_process_line(
                    xero_operation_name='tracking_category',
                    xero_operation_type='export',
                    instance=instance.id,
                    xero_operation_message=f"Tracking Options Successfully exported to Xero: {analytic_account.name}",
                    log_id=log_id,
                    fault_operation=False,
                )
            else:
                msg = f"Failed to export Tracking Options {analytic_account.name} to Xero. Response: {data}"
                analytic_account.message_post(body=msg)
                self.env['xero.log.vts.line'].sudo().generate_xero_process_line(
                    xero_operation_name="tracking_category", xero_operation_type="export",
                    instance=instance.id, xero_operation_message=msg,
                    process_request_message=payload, process_response_message=data,
                    log_id=log_id, fault_operation=True)
        except Exception as e:
            analytic_account.message_post(body=f"Exception while exporting Tracking Options {analytic_account.name} to Xero: {str(e)}")
            self.env['xero.log.vts.line'].sudo().generate_xero_process_line(
                xero_operation_name="tracking_category", xero_operation_type="export",
                instance=instance.id, xero_operation_message=f"Exception: {str(e)}",
                process_request_message=payload, process_response_message=str(e),
                log_id=log_id, fault_operation=True)
