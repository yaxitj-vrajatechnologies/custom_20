import requests
import logging
from .dpd_response import Response

_logger = logging.getLogger("DPD Benelux")


class DPDFranceRequest():


    def send_request(self, request_type, api_url, request_data,headers):
        _logger.info("Shipment Request API URL:::: %s" % api_url)
        _logger.info("Shipment Request Data:::: %s" % request_data)
        response_data = requests.request(method=request_type, url=api_url, headers=headers, data=request_data)
        _logger.info("::: Successfully response from {}".format(api_url))
        _logger.info("::: Response Data {}".format(response_data.text))
        if response_data.status_code in [200, 201]:
            try:
                response_data = Response(response_data)
                response_data = response_data.dict()
                _logger.info(">>> Response Data {}".format(response_data))
                return True, response_data
            except Exception as parse_error:
                _logger.error("Failed to parse response: %s" % response_data.text)
                return False, "Response parse error: %s" % str(parse_error)
        else:
            return False, response_data.text
