import base64
import json
import requests
import os
from dotenv import load_dotenv
from datetime import datetime, timedelta
from flask import abort


class CentralDBAdapter:

    token = {}

    def __init__(self):
        load_dotenv()
        self.base_url = os.getenv("CENTRAL_DB_BASE_URL")
        self.token = None

    def get_token(self):

        # print(f"headers: {headers} user {os.environ.get('NORDPOOL_USERNAME')} pass {os.environ.get('NORDPOOL_PASSWORD')}")
        __class__.token = json.loads(
            requests.post(os.environ.get("CENTRAL_DB_BASE_URL") + "/oauth/token", data={
                'grant_type': 'password',
                'client_id': os.environ.get("CENTRAL_DB_CLIENT_ID"),
                'username': os.environ.get("CENTRAL_DB_USERNAME"),
                'password': os.environ.get("CENTRAL_DB_PASSWORD"),
            },
            ).content)
        __class__.token['acquired_at'] = datetime.utcnow()

    def have_valid_token(self):
        return __class__.token and 'acquired_at' in __class__.token and 'expires_in' in __class__.token and (__class__.token['acquired_at'] + timedelta(seconds=__class__.token['expires_in'] - 30) > datetime.utcnow())

    def auth_headers(self):

        if not self.have_valid_token():
            self.get_token()

        return {'Authorization': f"Bearer {__class__.token['access_token']}"}

    def get_collection(self, collection, where_params):
        url = f"{self.base_url}/{collection}"

        headers = self.auth_headers()

        result = []
        params = {'where': json.dumps(where_params)}
        while True:
            print("url", url)
            print("params", params)
            # print("where_params", where_params)

            response = requests.request("GET",
                                        url,
                                        headers=headers,
                                        params=params)

            # print(response.text)
            resp_json = json.loads(response.text)
            result.extend(resp_json["_items"])
            if not 'next' in resp_json['_links']:
                break
            url = f"{self.base_url}/{resp_json['_links']['next']['href']}"
        return result

    def get_load_entries(self, prosumer_ids, start_timestamp, end_timestamp):
        return self.get_collection('load_entries', {"prosumer_id": {"$in": prosumer_ids},
                                                    "timestamp": {"$gte": start_timestamp, "$lt": end_timestamp}})

    def get_curtailable_loads(self, prosumer_ids, start_timestamp, end_timestamp):
        return self.get_collection('curtailable_loads', {"prosumer_id": {"$in": prosumer_ids},
                                                         "timestamp": {"$gte": start_timestamp, "$lt": end_timestamp}})

    def get_flex_request_data_points(self, flex_request_id, start_timestamp, end_timestamp):
        return self.get_collection('flex_request_data_points', {"flex_request_id": flex_request_id,
                                                                "timestamp": {"$gte": start_timestamp, "$lt": end_timestamp}})

    def get_objects(self, collection, names):
        return self.get_collection(collection, {"name": {"$in": names}})

    def get_dr_prosumers(self, prosumer_names, start_timestamp, end_timestamp):
        dr_prosumers = self.get_objects('dr_prosumers', prosumer_names)

        dr_prosumer_ids = {prosumer['_id']
            : prosumer for prosumer in dr_prosumers}
        print(dr_prosumer_ids)
        curtailable_loads = self.get_curtailable_loads(list(dr_prosumer_ids.keys()), start_timestamp.strftime(
            '%Y-%m-%dT%H:%M:%SZ'), end_timestamp.strftime('%Y-%m-%dT%H:%M:%SZ'))

        print(curtailable_loads)
        load_entries = self.get_load_entries(list(dr_prosumer_ids.keys()), start_timestamp.strftime(
            '%Y-%m-%dT%H:%M:%SZ'), end_timestamp.strftime('%Y-%m-%dT%H:%M:%SZ'))
        print(load_entries)

        for load in curtailable_loads:
            prosumer = dr_prosumer_ids[load["prosumer_id"]]
            if "curtailable_loads" not in prosumer:
                prosumer["curtailable_loads"] = []
            prosumer["curtailable_loads"] += [load]

        for load in load_entries:
            arr = dr_prosumer_ids[load["prosumer_id"]
                                  ][load["type"]][load["offset"]]
            if "load_entries" not in arr:
                arr["load_entries"] = []
            arr["load_entries"] += [load]

        dr_prosumer_names = {prosumer['name']
            : prosumer for prosumer in dr_prosumers}

        res = [ dr_prosumer_names[p] for p in prosumer_names]
        return res

    def get_flex_request(self, flex_request_name, start_timestamp, end_timestamp):
        flex_requests = self.get_objects('flex_requests', [flex_request_name])

        if len(flex_requests) != 1:
            abort(
                500, description=f"error obtaining data for flex_requestL: '{flex_request_name}, found: {len(flex_requests)}'")

        flex_request = flex_requests[0]

        flex_request['data_points'] = self.get_flex_request_data_points(flex_request['_id'], start_timestamp.strftime(
            '%Y-%m-%dT%H:%M:%SZ'), end_timestamp.strftime('%Y-%m-%dT%H:%M:%SZ'))

        return flex_request