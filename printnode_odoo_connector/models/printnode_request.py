from odoo import models
from odoo.exceptions import UserError
import requests


class PrintNodeAPIVts(models.AbstractModel):
    _name = "printnode.api.vts"
    _description = "PrintNOde API Request"

    def printnode_get_request(self,request_url,printnode_api_key):
        try:
            response = requests.get(request_url,auth=(printnode_api_key, ''),timeout=10)
            return response.json(), response.status_code
        except requests.exceptions.ConnectionError:
            raise UserError("Connection Error: Please check your internet connection or PrintNode API endpoint.")
        except requests.exceptions.Timeout:
            raise UserError("Timeout Error: The request to PrintNode API took too long. Please try again later.")
        except requests.exceptions.HTTPError as e:
            raise UserError(f"HTTP Error: {str(e)}")
        except requests.exceptions.RequestException as e:
            raise UserError(f"Request Error: {str(e)}")

    def get_data_from_printnode(self, printnode_api, printnode_api_key, endpoint):

        request_url = f"{printnode_api}/{endpoint}"

        response_info, response_status = self.printnode_get_request(request_url,printnode_api_key)

        return response_info, response_status