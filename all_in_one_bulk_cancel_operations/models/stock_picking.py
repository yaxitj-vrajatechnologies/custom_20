from odoo import models, fields
from odoo.exceptions import ValidationError


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    def action_cancel(self):
        for rec in self:
            if rec.state == 'done':
                for move_line in rec.move_ids:
                    move_line.cancel_move_record()
        super(StockPicking, self).action_cancel()

    def all_in_one_bulk_cancel_do_io(self):
        """
        - This method is called when Cancel order called from action of list view of stock picking module
        - From this method order cancel process get done & with that stock inventory adjustment process get done.
        """
        if self.filtered(lambda r: r.state == 'cancel'):
            raise ValidationError('One or many records are already cancelled.')
        if self.filtered(lambda r: r.state != 'done'):
            raise ValidationError('One or many records are not done yet.')
        for rec in self:
            rec.action_cancel()
