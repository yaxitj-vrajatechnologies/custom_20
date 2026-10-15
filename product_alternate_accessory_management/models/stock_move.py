from odoo import models


class StockMove(models.Model):
    _inherit = 'stock.move'

    def _action_done(self, *args, **kwargs):
        res = super()._action_done(*args, **kwargs)

        products = self.mapped('product_id.product_tmpl_id')

        products._compute_alternative_products()
        products._compute_product_accessories()

        return res