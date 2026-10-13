import base64
from odoo import models, fields, api, _
from datetime import timedelta
from dateutil.relativedelta import relativedelta
from odoo.exceptions import ValidationError


class FestivalOffersVTS(models.Model):
    _name = 'festival.offer.vts'
    _description = 'Offers'

    name = fields.Char(
        string="Offer",
        help="Enter the name of offer"
    )

    starting_offer_date = fields.Date(
        string="Starting Date",
        help="Starting date of the offer",
        default=fields.Datetime.now
    )

    ending_offer_date = fields.Date(
        string="Ending Date",
        help="Last date of the offer"
    )

    launch_date = fields.Date(
        string="Launch Date",
        help="Date of the product launch"
    )

    offer_discount = fields.Integer(
        string="Discount (%)",
        help="Total discount for the offer"
    )

    offer_type = fields.Selection([
        ('product_launch', 'Product Launch'),
        ('personalized_pricelist', 'Personalized Pricelist'),
        ('other', 'Others Offers')
    ], default='other',string="Offer Type")

    partner_category_ids = fields.Many2many(
        'res.partner.category',
        string="Customer Tags",
        help="Customers with the selected tag will receive a notification about this offer"
    )

    whatsapp_template_id = fields.Many2one(
        'whatsapp.template',
        string="WhatsApp Template",
        store=True,
    )

    select_product_opr = fields.Selection([
        ('include_product','Selected Product'),
        ('exclude_product','Excluded Product'),
        ('all_product','All product')
    ], string="Offer Apply On",default="include_product")

    product_ids = fields.Many2many(
        'product.product',
        string="Products",
        help="Offer applied on selected products"
    )

    description = fields.Text(
        string="Product Description"
    )

    number_of_repetitions = fields.Integer(
        string="Repeat After",
        default=1,
        help="Total Number of repetition of the notification"
    )

    repeat_unit = fields.Selection([
        ('day', 'Day'),
        ('week', 'Week'),
        ('month', 'Month')
    ], string="Unit", default='day')

    status = fields.Selection([
        ('draft', 'Draft'),
        ('running', 'Running'),
        ('expired', 'Expired')
    ], string="Status", default='draft', compute="_compute_status", store=True)

    state = fields.Selection([
        ('draft', 'Draft'),
        ('sent', 'Sent')
    ], default='draft', string="Status")

    notify_before = fields.Integer(
        string="Notify Before",
        default=1,
        help="Send Notification to user before selected days"
    )

    notify_unit = fields.Selection([
        ('day', 'Day'),
        ('week', 'Week'),
        ('month', 'Month'),
        ('custom', 'Custom')
    ], string="Unit", default='day')

    notify_custom_date = fields.Date(
        string="Notify Before"
    )

    last_cron_run = fields.Datetime(string="Last Cron Run")

    custom_notify_date = fields.Date(
        string="Notification Date",
        help="The notification will be automatically sent to customers on the specified date")

    # ==================================================================================

    @api.constrains('custom_notify_date')
    def _check_custom_notify_date(self):
        for record in self:
            if record.custom_notify_date and record.custom_notify_date < fields.Date.today():
                raise ValidationError(
                    "Invalid Notification Date! The notification cannot be scheduled for a past date. "
                    "Please choose today's date or a future date.")

    #    Validation Error For selecting Invalid repetition configuration

    @api.constrains(
        'starting_offer_date',
        'ending_offer_date',
        'number_of_repetitions',
        'repeat_unit'
    )

    def _check_offer_repetition_validity(self):
        for rec in self:
            if not rec.starting_offer_date or not rec.ending_offer_date:
                continue

            if rec.starting_offer_date > rec.ending_offer_date:
                raise ValidationError(_(
                    "The starting offer date must be less than or equal to the ending offer date."
                ))

            # Total offer duration
            offer_days = (rec.ending_offer_date - rec.starting_offer_date).days

            # Calculate repetition duration
            if rec.repeat_unit == 'day':
                repetition_days = rec.number_of_repetitions
            elif rec.repeat_unit == 'week':
                repetition_days = rec.number_of_repetitions * 7
            elif rec.repeat_unit == 'month':
                repetition_days = rec.number_of_repetitions * 30
            else:
                repetition_days = 0

            if repetition_days > offer_days:
                raise ValidationError(_(
                    "Invalid repetition configuration.\n\n"
                    "Offer duration: %s days\n"
                    "Repetition after: %s days.\n\n"
                    "Please reduce the repetition or extend the offer end date."
                ) % (offer_days, repetition_days))

    # -----------------------------------------------------------------------------------

    @api.constrains('launch_date', 'notify_before', 'notify_unit', 'notify_custom_date')
    def _check_product_launch_notification_validity(self):
        today = fields.Date.today()

        for rec in self:
            if not rec.launch_date:
                continue

            if rec.launch_date < today:
                raise ValidationError(_(
                    "Invalid Launch Date.\n\n"
                    "The product launch date (%s) cannot be earlier than today (%s)."
                ) % (rec.launch_date, today))

            remaining_days = (rec.launch_date - today).days

            if rec.notify_unit == 'day':
                notify_days = rec.notify_before
            elif rec.notify_unit == 'week':
                notify_days = rec.notify_before * 7
            elif rec.notify_unit == 'month':
                notify_days = rec.notify_before * 30
            elif rec.notify_unit == 'custom' and rec.notify_custom_date:
                notify_days = (rec.launch_date - rec.notify_custom_date).days
            else:
                notify_days = rec.notify_before

            if notify_days > remaining_days:
                raise ValidationError(_(
                    "Invalid notification configuration.\n\n"
                    "Launch date is in %s days.\n"
                    "You are trying to notify %s days before.\n\n"
                    "Please reduce the notification period or change the launch date."
                ) % (remaining_days, notify_days))

    # ==================================================================================

    @api.depends('starting_offer_date', 'ending_offer_date')
    def _compute_status(self):
        now = fields.Date.today()

        for record in self:
            if record.ending_offer_date and now > record.ending_offer_date:
                record.status = 'expired'
            elif record.starting_offer_date and now >= record.starting_offer_date:
                record.status = 'running'
            else:
                record.status = 'draft'

    def action_reset_to_draft(self):
        for record in self:
            if record.offer_type == 'other':
                record.status = 'draft'
            elif record.offer_type == 'product_launch':
                record.state = 'draft'
            elif record.offer_type == 'personalized_pricelist':
                record.state = 'draft'

    def action_offer_expire(self):
        for records in self:
            records.status = 'expired'

    @api.onchange('offer_type')
    def _onchange_offer_type(self):
        if self.offer_type == 'product_launch':
            self.whatsapp_template_id = self.env.ref(
                'whatsapp_notification_management.whatsapp_template_product_launch',
                raise_if_not_found=False
            )
        elif self.offer_type == 'personalized_pricelist':
            self.whatsapp_template_id = self.env.ref(
                'whatsapp_notification_management.whatsapp_template_personalized_product_price',
                raise_if_not_found=False
            )
        elif self.offer_type == 'other':
            self.whatsapp_template_id = self.env.ref(
                'whatsapp_notification_management.whatsapp_template_festival_offer',
                raise_if_not_found=False
            )

    # ==================================================================================
    #         SEND OFFERS NOTIFICATION

    def send_offer_notification(self):
        """Send festival offer details to customers based on target categories and products."""
        for record in self:

            template = record.whatsapp_template_id

            partners = self.env['res.partner'].search([
                ('category_id', 'in', record.partner_category_ids.ids),
                ('phone', '!=', False)
            ])

            discount = f"{record.offer_discount}%" if record.offer_discount else ''
            start_date = record.starting_offer_date.strftime('%d-%m-%Y') if record.starting_offer_date else ''
            end_date = record.ending_offer_date.strftime('%d-%m-%Y') if record.ending_offer_date else ''


            for partner in partners:
                attachment = record.generate_product_offer_pdf()
                composer = self.env['whatsapp.composer'].create({
                    'res_model': 'res.partner',
                    'res_ids': [partner.id],
                    'wa_template_id': template.id,

                    # TEMPLATE VARIABLES
                    'free_text_1': partner.name or '',
                    'free_text_2': discount,
                    'free_text_3': 'all product' if record.select_product_opr == 'all_product' else 'selected products',
                    'free_text_4': start_date,
                    'free_text_5': end_date,


                    # Attachment
                    'attachment_id': attachment.id
                })

                composer.action_send_whatsapp_template()

    def generate_product_offer_pdf(self):
        report_ref = 'whatsapp_notification_management.action_report_product_offer_pdf'

        pdf_content, _ = self.env['ir.actions.report']._render_qweb_pdf(
            report_ref,
            res_ids=[self.id]
        )

        attachment = self.env['ir.attachment'].create({
            'name': 'product_offer.pdf',
            'type': 'binary',
            'datas': base64.b64encode(pdf_content),
            'res_model': self._name,
            'res_id': self.id,
            'mimetype': 'application/pdf',
        })


        return attachment

    def cron_send_offer_notification(self):

        today = fields.Date.today()
        offer_template = self.env['whatsapp.template'].search([('template_name', '=', 'special_offers_discount')])

        records = self.search([
            ('status', '=', 'running'),
            ('whatsapp_template_id', '=', offer_template.id),
            ('offer_type', '=', 'other'),
            ('partner_category_ids', '!=', False),
        ])

        for record in records:

            next_run = False
            last_run = record.last_cron_run.date() if record.last_cron_run else today
            if record.repeat_unit == 'day':
                next_run = last_run + timedelta(days=record.number_of_repetitions)
            elif record.repeat_unit == 'week':
                next_run = last_run + timedelta(weeks=record.number_of_repetitions)
            elif record.repeat_unit == 'month':
                next_run = last_run + relativedelta(months=record.number_of_repetitions)

            if today == next_run:
                record.send_offer_notification()
                record.sudo().write({'last_cron_run': today})

    # -----------------------------------------------------------------------------------
    #     product launch

    def send_product_launch_notification(self):
        """Send WhatsApp notification to customers when a product is launched"""

        for record in self:

            template = record.whatsapp_template_id

            partners = self.env['res.partner'].sudo().search([
                ('category_id', 'in', record.partner_category_ids.ids),
                ('phone', '!=', False)
            ])

            product_names = '  '.join(f"• {name}" for name in record.product_ids.mapped('name')) or ''
            # product_names = ', '.join(record.product_ids.mapped('name')) or ''

            description = record.description or ''
            launch_date = record.launch_date.strftime('%d-%m-%Y') if record.launch_date else ''
            company_name = self.env.company.name or ''

            for partner in partners:
                composer = self.env['whatsapp.composer'].create({
                    'res_model': 'res.partner',
                    'res_ids': str([partner.id]),
                    'wa_template_id': template.id,

                    # Template variables
                    'free_text_1': partner.name or '',
                    'free_text_2': product_names,
                    'free_text_3': description,
                    'free_text_4': launch_date,
                    'free_text_5': company_name,
                })

                composer.action_send_whatsapp_template()

            record.sudo().write({'state': 'sent'})

    def cron_send_product_launch_notification(self):
        product_template = self.env['whatsapp.template'].search([('template_name', '=', 'new_product_launch')])
        if not product_template:
            return

        records = self.search([
            ('launch_date', '!=', False),
            ('partner_category_ids', '!=', False),
            ('state', '=', 'draft'),
            ('offer_type', '=', 'product_launch'),
            ('whatsapp_template_id', '=', product_template.id)
        ])

        today = fields.Date.today()

        for record in records:

            notify_date = False

            if record.notify_unit == 'day':
                notify_date = record.launch_date - timedelta(days=record.notify_before)

            elif record.notify_unit == 'week':
                notify_date = record.launch_date - timedelta(weeks=record.notify_before)

            elif record.notify_unit == 'month':
                notify_date = record.launch_date - relativedelta(months=record.notify_before)

            elif record.notify_unit == 'custom':
                notify_date = record.notify_custom_date if record.notify_custom_date else False

            if today == notify_date:
                record.send_product_launch_notification()
                record.sudo().write({'state': 'sent'})


   # ========================================================================================
   #      Personalized Product

    def cron_send_personalized_pricelist_notification(self):
        today = fields.Date.today()
        template = self.env['whatsapp.template'].search([('template_name', '=', 'personalized_product_price_offers')],
                                                        limit=1)
        if not template:
            return
        records = self.search([
            ('whatsapp_template_id', '=', template.id),
            ('custom_notify_date', '=', today),
            ('offer_type', '=', 'personalized_pricelist'),
            ('state', '=', 'draft')])

        for record in records:
            record.send_personalized_product_price_to_customer()
            record.sudo().write({'state': 'sent'})

    def send_personalized_product_price_to_customer(self):

        for record in self:

            template = record.whatsapp_template_id

            partners = self.env['res.partner'].search([
                ('category_id', 'in', record.partner_category_ids.ids),
                ('phone', '!=', False)
            ])

            for partner in partners:

                pricelist = partner.specific_property_product_pricelist
                if not pricelist:
                    continue

                pricelist_items = self.env['product.pricelist.item'].search([
                    ('pricelist_id', '=', pricelist.id)])

                for item in pricelist_items:

                    product = item.product_tmpl_id.product_variant_id if item.product_tmpl_id else False
                    # qty = item.min_quantity if item.min_quantity > 0 else 1
                    price = item.price

                    # create composer
                    composer = self.env['whatsapp.composer'].create({
                        'res_model': 'res.partner',
                        'res_ids': str([partner.id]),
                        'wa_template_id': template.id,

                        # FREE TEXT VARIABLES (important)
                        'free_text_1': partner.name or '',
                        'free_text_2': product.name if product else 'All Products',
                        'free_text_3': price or " ",
                        'free_text_4': self.env.company.website or '',
                        'free_text_5': self.env.company.name or '',
                    })

                    composer.action_send_whatsapp_template()

            record.sudo().write({'state': 'sent'})
