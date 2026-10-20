from odoo import models


class StockMove(models.Model):
    _inherit = 'stock.move'

    def cancel_move_record(self):
        """
        - This method created to perform operation regarding stock move records & stock adjustment process.
        - After that unlink move lines & cancel stock move.
        """
        self.state = 'draft'
        if self.product_id.type == 'consu':
            if self.picking_code == 'outgoing':
                quantity_done = self.quantity
                location = self.location_id
            elif self.picking_code == 'incoming':
                quantity_done = -self.quantity
                location = self.location_dest_id
            elif self.picking_code == 'internal':
                dest_quantity_done = -self.quantity
                # Remove Stock From Destination
                self.env['stock.quant']._update_available_quantity(product_id=self.product_id,
                                                                   location_id=self.location_dest_id,
                                                                   quantity=dest_quantity_done)
                src_quantity_done = self.quantity
                # Add stock back to source
                self.env['stock.quant']._update_available_quantity(product_id=self.product_id,
                                                                   location_id=self.location_id,
                                                                   quantity=src_quantity_done)
            else:
                quantity_done = 0.00
                location = self.env['stock.location']

            if self.picking_code in ['outgoing', 'incoming']:
                self.env['stock.quant']._update_available_quantity(product_id=self.product_id,
                                                                   location_id=location,
                                                                   quantity=quantity_done)
        self.move_line_ids.unlink()
        self.state = 'cancel'
