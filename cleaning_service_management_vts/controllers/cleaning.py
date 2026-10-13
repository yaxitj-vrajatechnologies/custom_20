# -*- coding: utf-8 *-*
from odoo import http
from odoo.http import request
from datetime import datetime, timedelta


class CleaningController(http.Controller):

    @http.route('/cleaning', type='http', auth='public', website=True)
    def cleaning_form(self, **kwargs):
        services = request.env['service.type.vts'].sudo().search([])
        shifts = request.env['cleaning.shift.vts'].sudo().search([])
        countries = request.env['res.country'].sudo().search([], order='name asc')
        states = request.env['res.country.state'].sudo().search([], order='name asc')
        partner = request.env.user.partner_id
        customer_name = partner.name if partner and partner.active else ''

        error = request.session.pop('form_error', None)
        post = request.session.pop('form_post', None)

        return request.render('cleaning_service_management_vts.cleaning_form_template', {
            'services': services,'shifts': shifts,'partner': partner,'countries': countries,'customer_name': customer_name,
            'states': states,'error': error,'post': post,})

    @http.route('/cleaning/get_slots', type='json', auth='public', website=True)
    def get_slots(self, shift_id=None, **kwargs):
        if not shift_id:
            return []
        slot_records = request.env['cleaning.shift.slot.vts'].sudo().search([
            ('shift_id', '=', int(shift_id))
        ], order='slot_start_time asc')
        return [{'id': sl.id, 'name': sl.name} for sl in slot_records]

    @http.route('/cleaning/submit', type='http', auth='public', methods=['POST'], website=True)
    def cleaning_submit(self, **post):
        from odoo.exceptions import ValidationError
        from dateutil.relativedelta import relativedelta

        try:
            is_recurring = True if post.get('is_recurring') else False
            preferred_date = datetime.strptime(post.get('preferred_date'), '%d/%m/%Y').date() if post.get(
                'preferred_date') else False
            end_date = datetime.strptime(post.get('end_date'), '%d/%m/%Y').date() if post.get('end_date') else False
            repeat_interval = int(post.get('repeat_interval')) if post.get('repeat_interval') else 1
            recurring_type = post.get('recurring_type')

            if is_recurring and end_date and preferred_date:
                if recurring_type == 'day':
                    min_end_date = preferred_date + timedelta(days=repeat_interval)
                elif recurring_type == 'week':
                    min_end_date = preferred_date + timedelta(weeks=repeat_interval)
                elif recurring_type == 'month':
                    min_end_date = preferred_date + relativedelta(months=repeat_interval)
                else:
                    min_end_date = preferred_date

                if end_date < min_end_date:
                    raise ValidationError(
                        f"Ending Date must be at least {min_end_date} "
                        f"({repeat_interval} {recurring_type}(s) after Preferred Date {preferred_date})."
                    )

            partner = request.env.user.partner_id

            if partner and not partner.active:
                partner = request.env['res.partner'].sudo().search(
                    [('name', '=', post.get('partner_name')), ('email', '=', post.get('email_info'))], limit=1)
            if not partner:
                partner = request.env['res.partner'].sudo().create({
                    'name': post.get('partner_name'),
                    'street': post.get('partner_address'),
                    'email': post.get('email_info'),
                    'country_id': int(post.get('country_info')) if post.get('country_info') else False,
                    'state_id': int(post.get('state_info')) if post.get('state_info') else False,
                    'phone': post.get('contact_number'),
                    'zip': post.get('zipcode_info'),
                    'city': post.get('city_info'),
                })

            booking_request = request.env['booking.request'].sudo().create({
                'partner_id': partner.id,
                'service_type_id': int(post.get('service_type_id')),
                'floor_count': post.get('floor_count'),
                'room_count': post.get('room_count'),
                'area_sqft': post.get('area_sqft'),
                'cleaning_shift_id': int(post.get('cleaning_shift_id')) if post.get('cleaning_shift_id') else False,
                'preferred_date': preferred_date.strftime('%Y-%m-%d') if preferred_date else False,
                'is_recurring': is_recurring,
                'repeat_interval': post.get('repeat_interval'),
                'recurring_type': recurring_type,
                'special_instructions': post.get('special_instructions'),
                'email': post.get('email_info'),
                'mobile': post.get('contact_number'),
                'end_date': end_date.strftime('%Y-%m-%d') if end_date else False,
                'shift_slot_id': post.get('shift_slot_id')
            })

            if booking_request:
                booking_request._onchange_service_type_id()
                booking_request._onchange_partner_id()

            return request.redirect('/cleaning-thank-you')

        except ValidationError as e:
            request.session['form_error'] = str(e.args[0])
            request.session['form_post'] = post
            return request.redirect('/cleaning')

    @http.route('/cleaning-thank-you', type='http', auth='public', website=True)
    def thank_you(self, **kwargs):
        return request.render('cleaning_service_management_vts.cleaning_thank_you')

    @http.route('/cleaning/get_disabled_dates', type='json', auth='public', website=True)
    def get_disabled_dates(self, **kwargs):

        holidays = request.env['cleaning.holiday.vts'].sudo().search([('is_active', '=', True)])

        weekly_off_days = []
        disabled_dates = []

        for holiday in holidays:

            # Weekly Off
            if holiday.holiday_type == 'weekly_off' and holiday.day_of_week:
                weekly_off_days.append(int(holiday.day_of_week))

            # Exception Holidays
            elif holiday.holiday_type == 'exception' and holiday.date_from and holiday.date_to:

                current_date = holiday.date_from

                while current_date <= holiday.date_to:
                    disabled_dates.append(current_date.strftime('%Y-%m-%d'))
                    current_date += timedelta(days=1)

        return {
            'weekly_off_days': weekly_off_days,
            'disabled_dates': disabled_dates,
        }
