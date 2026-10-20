# -*- coding: utf-8 -*-
import binascii
import xml.etree.ElementTree as etree
from .dpd_request import DPDFranceRequest
import logging
from odoo import fields, models, _
from odoo.exceptions import ValidationError


class DPDDeliveryCarrier(models.Model):
    _inherit = 'delivery.carrier'

    delivery_type = fields.Selection(selection_add=[("dpd_fr", "DPD France")],
                                     ondelete={'dpd_fr': 'set default'})

    def dpd_fr_rate_shipment(self, order):
        return {'success': True, 'price': 0.0, 'error_message': False, 'warning_message': False}

    def dpd_fr_send_shipping(self, pickings):
        try:
            url = (self.company_id and self.company_id.dpd_fr_api_url)
            request_body = self.prepare_dpd_fr_request_body(picking=pickings)
            headers = {
                'SOAPAction': "http://www.cargonet.software/CreateMultiShipmentBc",
                'Content-Type': "text/xml; charset='utf-8'"
            }
            logging.info("Request Body ::: %s" % request_body)
            success, response_data = DPDFranceRequest.send_request(self, "POST", api_url=url, request_data=request_body,
                                                                   headers=headers)
            logging.info("Response Data ::: %s" % response_data)
            if success:
                result = response_data and response_data.get('Envelope') and response_data.get('Envelope').get(
                    'Body') and response_data.get('Envelope').get('Body').get(
                    'CreateMultiShipmentBcResponse') and response_data.get('Envelope').get('Body').get(
                    'CreateMultiShipmentBcResponse').get('CreateMultiShipmentBcResult')
                if not result:
                    raise ValidationError(_("Label Data not found in response {}".format(response_data)))
                parcel_barcode_numbers = result and result.get('shipments') and result.get('shipments').get(
                    'ShipmentBc') and result.get(
                    'shipments').get('ShipmentBc')
                barcode_ids = []
                if isinstance(parcel_barcode_numbers, dict):
                    parcel_barcode_numbers = [parcel_barcode_numbers]
                for parcel_barcode_number in parcel_barcode_numbers:
                    barcode_ids.append(parcel_barcode_number.get('Shipment').get('BarcodeId'))
                for barcode_id in barcode_ids:
                    dpd_france_geo_label_request_data = self._prepare_get_label_request(barcode_id)
                    headers = {
                        'SOAPAction': "http://www.cargonet.software/GetLabelBc",
                        'Content-Type': "text/xml; charset='utf-8'"
                    }
                    success, response_data = DPDFranceRequest.send_request(self, "POST", api_url=url,
                                                                           request_data=dpd_france_geo_label_request_data,
                                                                           headers=headers)
                    logging.info("Response Data ::: %s" % response_data)
                    if success:
                        labels_container = (
                                response_data.get('Envelope') and
                                response_data.get('Envelope').get('Body') and
                                response_data.get('Envelope').get('Body').get('GetLabelBcResponse') and
                                response_data.get('Envelope').get('Body').get('GetLabelBcResponse').get(
                                    'GetLabelBcResult') and
                                response_data.get('Envelope').get('Body').get('GetLabelBcResponse').get(
                                    'GetLabelBcResult').get('labels')
                        )

                        if labels_container:
                            # Step 2: Extract the 'Label' list from inside 'labels'
                            # xmltodict returns a list when multiple <Label> exist, dict when only one
                            label_list = labels_container.get('Label', [])

                            # Step 3: Normalize to list (handles single Label case)
                            if isinstance(label_list, dict):
                                label_list = [label_list]

                            # Step 4: Loop and attach each label as a separate PDF
                            for data in label_list:
                                doc_type = data.get('type', 'UNKNOWN')  # e.g. 'EPRINT' or 'EPRINTATTACHMENT'
                                label_content = data.get('label', '')
                                if label_content:
                                    binary_data = binascii.a2b_base64(str(label_content))
                                    pickings.message_post(
                                        body="Shipment Created! Tracking number - %s (%s)" % (barcode_id, doc_type),
                                        attachments=[('DPD-%s-%s.pdf' % (barcode_id, doc_type.lower()), binary_data)]
                                    )
                        else:
                            pickings.message_post(
                                body="Label Not created for barcode ID: {0}".format(barcode_id)
                            )
                    else:
                        pickings.message_post(body="Label Not created for barcode ID : {0}".format(barcode_id))
                shipping_data = {
                    'exact_price': 0.0,
                    'tracking_number': ','.join(barcode_ids)}
                return [shipping_data]
            else:
                raise ValidationError(response_data)
        except Exception as e:
            raise ValidationError(e)

    def _prepare_get_label_request(self, shipment_number):
        # --- Envelope ---
        envelope = etree.Element('Envelope')
        envelope.attrib['xmlns'] = 'http://www.w3.org/2003/05/soap-envelope'

        # --- Header ---
        header = etree.SubElement(envelope, 'Header')
        user_credentials = etree.SubElement(header, 'UserCredentials')
        user_credentials.attrib['xmlns'] = 'http://www.cargonet.software'
        etree.SubElement(user_credentials, 'userid').text = '{}'.format(
            self.company_id and self.company_id.dpd_fr_username)
        etree.SubElement(user_credentials, 'password').text = '{}'.format(
            self.company_id and self.company_id.dpd_fr_password)

        # --- Body ---
        body = etree.SubElement(envelope, 'Body')
        get_label = etree.SubElement(body, 'GetLabelBc')
        get_label.attrib['xmlns'] = 'http://www.cargonet.software'
        request = etree.SubElement(get_label, 'request')

        # --- Label Type ---
        label_type = etree.SubElement(request, 'labelType')
        etree.SubElement(label_type, 'type').text = 'PDF'

        # --- Shipment Number ---
        etree.SubElement(request, 'shipmentNumber').text = '{}'.format(shipment_number)

        # --- Customer ---
        customer = etree.SubElement(request, 'customer')
        etree.SubElement(customer, 'centernumber').text = '%s' % (
                self.company_id and self.company_id.dpd_fr_center_number)
        etree.SubElement(customer, 'number').text = '%s' % (
                self.company_id and self.company_id.dpd_fr_customer_number)
        etree.SubElement(customer, 'countrycode').text = '250'

        return etree.tostring(envelope)

    def prepare_dpd_fr_request_body(self, picking):
        sender_add = picking.picking_type_id and picking.picking_type_id.warehouse_id and picking.picking_type_id.warehouse_id.partner_id
        receiver_add = picking and picking.partner_id
        for address in [sender_add, receiver_add]:
            res = [field for field in ['zip', 'name', 'city', 'street', 'country_id'] if not address[field]]
            if res:
                raise ValidationError("Please Define {0} in {1}".format(', '.join(res), address.name))

        envelope = etree.Element('Envelope')
        envelope.attrib['xmlns'] = 'http://schemas.xmlsoap.org/soap/envelope/'

        # --- Header ---
        header = etree.SubElement(envelope, 'Header')
        user_credentials = etree.SubElement(header, 'UserCredentials')
        user_credentials.attrib['xmlns'] = 'http://www.cargonet.software'
        etree.SubElement(user_credentials, 'userid').text = '{}'.format(
            self.company_id and self.company_id.dpd_fr_username)
        etree.SubElement(user_credentials, 'password').text = '{}'.format(
            self.company_id and self.company_id.dpd_fr_password)

        # --- Body ---
        body = etree.SubElement(envelope, 'Body')
        create_multi_shipment = etree.SubElement(body, 'CreateMultiShipmentBc')
        create_multi_shipment.attrib['xmlns'] = 'http://www.cargonet.software'
        request = etree.SubElement(create_multi_shipment, 'request')

        # --- Receiver Address ---
        receiver_address = etree.SubElement(request, 'receiveraddress')
        etree.SubElement(receiver_address, 'countryPrefix').text = '{}'.format(
            receiver_add and receiver_add.country_id and receiver_add.country_id.code)
        etree.SubElement(receiver_address, 'zipCode').text = '{}'.format(receiver_add.zip)
        etree.SubElement(receiver_address, 'city').text = '{}'.format(receiver_add.city)
        etree.SubElement(receiver_address, 'street').text = '{}'.format(receiver_add.street)
        etree.SubElement(receiver_address, 'name').text = '{}'.format(receiver_add.name)
        etree.SubElement(receiver_address, 'phoneNumber').text = '{}'.format(receiver_add.phone)

        # --- Shipper Address ---
        shipper_address = etree.SubElement(request, 'shipperaddress')
        etree.SubElement(shipper_address, 'countryPrefix').text = '{}'.format(
            sender_add and sender_add.country_id and sender_add.country_id.code)
        etree.SubElement(shipper_address, 'zipCode').text = '{}'.format(sender_add.zip)
        etree.SubElement(shipper_address, 'city').text = '{}'.format(sender_add.city)
        etree.SubElement(shipper_address, 'street').text = '{}'.format(sender_add.street)
        etree.SubElement(shipper_address, 'name').text = '{}'.format(sender_add.name)
        etree.SubElement(shipper_address, 'phoneNumber').text = '{}'.format(sender_add.phone)

        # we pass static value for country code, not get value from Odoo, for more information refer doc
        etree.SubElement(request, 'customer_countrycode').text = '250'
        etree.SubElement(request, 'customer_centernumber').text = '%s' % (
                self.company_id and self.company_id.dpd_fr_center_number)
        etree.SubElement(request, 'customer_number').text = '%s' % (
                self.company_id and self.company_id.dpd_fr_customer_number)

        # --- Shipping Date ---
        etree.SubElement(request, 'shippingdate').text = '{0}'.format(
            picking.scheduled_date.strftime("%d.%m.%Y"))

        # --- Slaves (multi-package) ---
        slaves_tag = etree.SubElement(request, 'slaves')

        weight_bulk = picking.weight_bulk
        package_ids = picking.move_line_ids.mapped('result_package_id')
        for package_id in package_ids:
            weight = package_id.shipping_weight
            package_name = package_id.name
            slave_request = etree.SubElement(slaves_tag, 'SlaveRequest')
            etree.SubElement(slave_request, 'weight').text = '{}'.format(weight)
            etree.SubElement(slave_request, 'referencenumber').text = '{}'.format(package_name)
        if weight_bulk:
            slave_request = etree.SubElement(slaves_tag, 'SlaveRequest')
            etree.SubElement(slave_request, 'weight').text = '{}'.format(weight_bulk)
            etree.SubElement(slave_request, 'referencenumber').text = '{}'.format('DPD Default Pack')

        return etree.tostring(envelope)

    def dpd_fr_cancel_shipment(self, pickings):
        raise ValidationError(_('Cancel Service not provide by DPD France'))

    def dpd_fr_get_tracking_link(self, picking):
        return "https://www.dpd.com/fr/en/"
