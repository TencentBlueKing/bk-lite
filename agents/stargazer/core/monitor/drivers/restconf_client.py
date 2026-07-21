import requests


def get_token_from_response(response):
    return response.get("token")


def set_headers_by_token(headers, token):
    headers.update({"Authorization": f"Bearer {token}"})


class RestApiClient:
    def __init__(self, base_url, save_session=False, timeout=10):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.session = requests.Session() if save_session else requests
        self.token = None
        self.json = True

    def set_token(self, token):
        self.token = token

    def set_header(self, key, value):
        """Attach a sticky header for subsequent session requests.

        Enterprise storage monitors (PowerStore, OceanStor, StorageGRID, …)
        rely on this for token / CSRF / cookie headers issued at login.
        """
        if isinstance(self.session, requests.Session):
            self.session.headers[key] = value
        else:
            if not hasattr(self, "_sticky_headers"):
                self._sticky_headers = {}
            self._sticky_headers[key] = value

    def request(
        self,
        method,
        endpoint,
        params=None,
        data=None,
        json=None,
        headers=None,
        timeout=None,
        token_header_func=None,
        real_response=False,
        **kwargs,
    ):
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        timeout = timeout or self.timeout

        if headers is None:
            headers = {}
        sticky = getattr(self, "_sticky_headers", None)
        if sticky:
            for key, value in sticky.items():
                headers.setdefault(key, value)
        enable_json = json if json is not None else self.json
        if enable_json:
            headers.setdefault("Content-Type", "application/json")
        if self.token:
            func = token_header_func or set_headers_by_token
            func(headers, self.token)

        try:
            response = self.session.request(
                method=method.upper(),
                url=url,
                params=params,
                data=data,
                json=json,
                headers=headers,
                timeout=timeout,
                **kwargs,
            )
            response.raise_for_status()
            if real_response:
                return response
            if enable_json:
                return response.json()
            else:
                return response.content.decode("utf-8")
        except requests.exceptions.RequestException as e:
            raise RuntimeError(f"REST API request error: {e}")

    def get(self, endpoint, params=None, headers=None, timeout=None, **kwargs):
        return self.request(
            "GET", endpoint, params=params, headers=headers, timeout=timeout, **kwargs
        )

    def post(
        self, endpoint, data=None, json=None, headers=None, timeout=None, **kwargs
    ):
        return self.request(
            "POST",
            endpoint,
            data=data,
            json=json,
            headers=headers,
            timeout=timeout,
            **kwargs,
        )

    def put(self, endpoint, data=None, json=None, headers=None, timeout=None, **kwargs):
        return self.request(
            "PUT",
            endpoint,
            data=data,
            json=json,
            headers=headers,
            timeout=timeout,
            **kwargs,
        )

    def delete(self, endpoint, headers=None, timeout=None, **kwargs):
        return self.request(
            "DELETE", endpoint, headers=headers, timeout=timeout, **kwargs
        )

    def login(
        self,
        login_url,
        method,
        credentials,
        headers=None,
        real_response=False,
        need_token=True,
        token_func=None,
        **kwargs,
    ):
        response = self.request(
            method,
            login_url,
            json=credentials,
            headers=headers,
            real_response=real_response,
            **kwargs,
        )
        if need_token:
            func = token_func or get_token_from_response
            self.token = func(response)
            if not self.token:
                raise ValueError("Failed to retrieve token from login response.")
        return response

    def logout(self):
        self.token = None
        if isinstance(self.session, requests.Session):
            self.session.close()
