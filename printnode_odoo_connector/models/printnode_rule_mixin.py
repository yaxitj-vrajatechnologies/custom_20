from odoo import models

class PrintNodeRuleMixin(models.AbstractModel):
    _name = 'printnode.rule.mixin'

    def print_rule(self, action_code, record_ids=None, **kwargs):
        """ Execute configured print rules for the given action.

        :param action_code: rule action identifier
        :param record_ids: optional list of record IDs
        :return: True if printing occurred, otherwise False"""

        model_ids = record_ids if record_ids is not None else self.ids
        rule_obj = self.env['printnode.rule']
        return rule_obj.printnode_print_reports(action=action_code,ids_list=model_ids,**kwargs)
