from odoo import models


class SaleOrderLine(models.Model):
    _inherit = "sale.order.line"

    def _compute_name(self):
        super()._compute_name()
        for line in self:
            if not line.name:
                line.name = ''