import datetime
from odoo import api, fields, models, _
from odoo.exceptions import UserError
from odoo.tools.safe_eval import safe_eval

class ActionsReport(models.Model):
    _inherit = "ir.actions.report"

    printnode_action_ids =fields.One2many("print.base.user", "report_id", string="Actions")
    is_color_printer = fields.Boolean("Color Printer")

    def print_action(self):
        action = {}
        if user_action := self.env["print.base.user"].sudo().search([("user_id", "=", self.env.uid),
                ("report_id", "=", self.id),("action_type", "!=", "user_default"),],limit=1):
            action.update({t: u for t, u in user_action.print_action().items() if u})
        return action

    @api.model
    def printnode_print_action_for_report(self, report_name, value_number=False):
        name_report = self._get_report_from_name(report_name)
        if not name_report:
            return {}
        report_result = name_report.print_action()
        report_result.update(
            {
                "printer_name": report_result["printer"].name
                if report_result.get("printer")
                else False,
                "report_id": report_result.get("printer").id if report_result.get("printer") else report_result.get("printer"),
                "is_online": report_result["printer"].status == "online" if report_result.get("printer") else False,
                "is_color_printer": report_result["printer"].is_color_printer if report_result.get("printer") else False,
                "is_qweb_color_print": name_report.is_color_printer,
            }
        )
        return report_result

    def print_report_validation(self, printer):
        if printer:
            online = printer.printnode_instance_id.check_printer_status(printer)
            if not online:
                log_id = self.env['printnode.log.vts'].sudo().generate_printnode_logs(
                    printnode_opr_name='printjob_request',printnode_opr_type='print_request', instance=printer.printnode_instance_id.id,
                    printnode_opr_message="Error during Printjob Printing Process")

                self.env['printnode.log.vts.line'].sudo().generate_printnode_process_line(
                    printnode_opr_name='printjob_request',printnode_opr_type='print_request',
                    instance=printer.printnode_instance_id.id if printer.printnode_instance_id else False,
                    printnode_opr_message=f"There is no available printer to print",
                    process_request_message='', process_response_message='', log_id=log_id,
                    fault_operation=True)
                return
            if self.report_type not in ["qweb-html", "qweb-pdf"]:
                return(
                    _(
                        "The chosen report type ({}) is not supported by printer {}. Kindly verify the report type in the selected report."
                    ).format("HTML", printer.name)
                )
            return True
        return (
            _("The printer or document necessary to print this report cannot be found.")
        )

    def direct_document_print(self, report_ref, res_ids, data=None, **kwargs):
        data = data or {}
        # Get printing details and the printer from context
        printing_details = self.print_action()
        printer = printing_details.pop("printer", None)

        report = self._get_report_from_name(report_ref)

        # Raise an exception if no printer is configured
        if not printer:
            raise UserError(_("No printer configured to print this report."))
        # Validate the report for printing
        report_validation = self.print_report_validation(printer)

        if res_ids and report_validation:
            # Fetch objects based on res_ids
            obj = self.env[self.model].browse(res_ids)
            title = self.name
            if self.print_report_name and len(obj) <= 1:
                title = safe_eval(self.print_report_name,{"object": obj, "time": datetime.datetime.now().time()})
            total_copies = int(data.get("value_number")) if data.get("value_number") else 1
            paper_id=self.env['printnode.paper.vts'].sudo().search([('name','=',printing_details.get('paper'))],limit=1)
            printer.with_context(skip_printnode_rule_check=True).printnode_print_document(report,obj,
                total_copies=total_copies,data=data,paper=paper_id)
        return True

    def document_sent_to_printer(self, printing_details, printer, document):
        if self.env.context.get("force_stop_printing") or not printing_details:
            return False
        return bool(printing_details["action"] == "printnode" and printer and document)

class PrintBaseUser(models.Model):
    _name = "print.base.user"
    _description = "Print Action Based On User"

    report_id = fields.Many2one("ir.actions.report", string="Report", required=True, ondelete="cascade")

    action_type = fields.Selection([
            ("printnode", "Send to PrintNode"),
            ("user_default", "User defaults"),
        ],string="Default Action",default="user_default",required=True)

    user_id = fields.Many2one("res.users",string="User",required=True,ondelete="cascade")
    printer_id = fields.Many2one('printnode.printer.vts', string='Printer', domain=[('status', '=', 'online')], help="Printer to use for this rule. Optional.")
    printer_paper_ids = fields.Many2many('printnode.paper.vts', string='Papers', related='printer_id.paper_ids')
    printnode_paper_id = fields.Many2one('printnode.paper.vts', string="Select Papers",domain="[('id', 'in', printer_paper_ids)]")
    print_type = fields.Selection(selection=[("print", "Print"), ("download", "Download"), ("open", "Open")],
        string="Default printing option")


    def print_action(self):
        if not self:
            return {}
        return {
            "action": self.action_type,
            "printer": self.printer_id,
            "paper": self.printnode_paper_id.name if self.printnode_paper_id else False,
        }
