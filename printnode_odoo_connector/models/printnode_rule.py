from odoo import models, fields, api, _
from odoo.exceptions import  ValidationError
from odoo.fields import Domain
from odoo.tools.safe_eval import safe_eval


class PrintNodeRule(models.Model):
    _name = 'printnode.rule'
    _rec_name='action'

    action = fields.Many2one('printnode.rule.action',string='Print Action',readonly=True,
                             required=True, ondelete='cascade',help="Select a print action for this rule to listen to.")

    active = fields.Boolean(string='Active',default=False,
                            help="Turn this on to activate the print rule. If turned off, it will be moved to 'archive' but can still be found using the filter button.")

    description = fields.Char(string='Description',size=200,help="Notes or memo about this rule.")

    domain = fields.Text(string='Domain',default='[]',help="Optional filter domain to determine when this rule should trigger.")

    model_id = fields.Many2one('ir.model',string='Model',related='action.model_id',readonly=True,help="The model on which this print rule works.")

    report_type = fields.Selection(related='report_id.report_type',readonly=True)

    model = fields.Char(string='Related Document Model',related='report_id.model',readonly=True,help="Technical name of the related model.")

    reports_model_id = fields.Many2one('ir.model',string='Document Model',related='action.reports_model_id',readonly=True,
                            help="The model used to generate the report.")

    total_copies = fields.Integer(string="Copies",default=1,help="Number of copies to print for this rule.")

    report_id = fields.Many2one('ir.actions.report',string='Report',required=True,domain="[('report_type', 'in', ('qweb-pdf', 'qweb-text', 'py3o'))]",
                            help="Select the report that will be printed by this rule.")

    printer_id = fields.Many2one('printnode.printer.vts',string='Printer', domain=[('status', '=', 'online')],
                            help="Printer to use for this rule. Optional.")
    available_paper_ids = fields.Many2many('printnode.paper.vts', string='Papers',related='printer_id.paper_ids')
    report_paper_id = fields.Many2one('printnode.paper.vts',string='Report Paper Format',domain="[('id', 'in', available_paper_ids)]")


    @api.constrains('total_copies')
    def _check_total_copies(self):
        for record in self:
            if record.total_copies < 1:
                raise ValidationError(_("Total Number of Copies can't be less than 1"))

    def _apply_domain_filter(self,ids_list):
        """
            Get objects by IDs with applied domain
        """
        self.ensure_one()

        Model = self.env[self.model_id.model]
        if self.domain == '[]':
            return Model.browse(ids_list)
        return Model.search(
            Domain('id', 'in', ids_list) & Domain(safe_eval(self.domain))
        )

    def _get_available_printer(self):
        """
        Return printer to use for current rule 
       
        """
        self.ensure_one()

        user = self.env.user

        external_printer_id = user.get_printer(self.report_id.id)
        printer = self.printer_id or external_printer_id
        paper = self.report_paper_id.name

        if not printer:
            log_id = self.env['printnode.log.vts'].sudo().generate_printnode_logs(printnode_opr_name='printer_configuration',
                printnode_opr_type='print_request',instance=printer.printnode_instance_id.id ,
                printnode_opr_message=f"No printer configured for report {self.report_id.name}")

            self.env['printnode.log.vts.line'].sudo().generate_printnode_process_line(
                printnode_opr_name='printer_configuration',printnode_opr_type='print_request',
                instance=printer.printnode_instance_id.id,printnode_opr_message=f"Printer configuration missing for report {self.report_id.name}",
                process_response_message="No printer defined at user level or company level.",log_id=log_id,fault_operation=True)

        return printer,paper

    def printnode_print_reports(self, action, ids_list, **kwargs):
        user = self.env.user
        company = self.env.company

        if not (company.printnode_auto_print and user.printnode_auto_print):
            return

        rules = self.sudo().search([('active', '=', True),('action.code', '=', action)])
        printed=False

        for rule in rules:
            objects = rule._apply_domain_filter(ids_list)
            rule_method_name = f"_rule_{rule.action.code}"

            if objects:
                printer,paper = rule._get_available_printer()
                if printer:
                    if rule.model_id != rule.reports_model_id:
                        if hasattr(objects, rule_method_name):
                            rule_method = getattr(objects, rule_method_name)
                            printed = rule_method(rule=rule,report_info=rule.report_id,printer_id=printer,
                                total_copies=rule.total_copies)
                    elif hasattr(self.env[rule.model_id.model], rule_method_name):
                        rule_method = getattr(objects, rule_method_name)
                        printed = rule_method(rule=rule,report_info=rule.report_id,printer_id=printer,
                            total_copies=rule.total_copies)
                    else:
                        printed = printer.printnode_print_document(rule.report_id,objects,total_copies=rule.total_copies,paper=paper)
        return printed
