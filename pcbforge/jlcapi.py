"""JLCPCB Open API client: the component endpoints of JLCPCB's "overseas openapi" SDK.

Endpoints (from the official Java SDK, overseas-openapi-sdk-java 1.0.6):
  /overseas/openapi/component/getComponentDetailByCode    details for a list of C-numbers
  /overseas/openapi/component/getComponentInfos           whole catalogue, paged by lastKey
  /overseas/openapi/component/getComponentLibraryList     JLCPCB's assembly library, paged
  /overseas/openapi/component/getPrivateComponentLibrary  your private / consigned stock

Credentials come from the environment (see .env.example): JLC_APP_ID, JLC_ACCESS_KEY,
JLC_SECRET_KEY, and optionally JLC_API_BASE. Access must be approved by JLCPCB first.

Request signing matches JLCPCB's core library (jlc-openapi-sdk-core-java 1.0.0,
SignAuthorization + HmacSHA256Signer, read from its class files): HMAC-SHA256 over
"METHOD\npath[?query]\ntimestamp\nnonce\nbody\n" with the secret key, Base64-encoded; the
timestamp is Unix seconds and the nonce 32 characters; header
`Authorization: JOP appid="..",accesskey="..",timestamp="..",nonce="..",signature=".."`.
The core library has no default server address (it must be https://); JLC_API_BASE sets it.
"""

import base64
import hashlib
import hmac
import json
import os
import secrets
import time
import urllib.error
import urllib.request

from . import env  # noqa: F401  (loads the repo's .env, where the JLC_* keys live)

DEFAULT_BASE = "https://open.jlcpcb.com"
DETAIL_BATCH = 50   # C-numbers per getComponentDetailByCode call (limit not documented; kept small)


class JlcApiError(RuntimeError):
    pass


def _skew_from(headers) -> float | None:
    """This PC's clock minus the server's, from a response's Date header (None if absent)."""
    from email.utils import parsedate_to_datetime
    try:
        date = headers.get("Date")
        return time.time() - parsedate_to_datetime(date).timestamp() if date else None
    except (TypeError, ValueError):
        return None


class JlcApi:
    def __init__(self, app_id: str, access_key: str, secret_key: str, base_url: str = DEFAULT_BASE,
                 timeout_s: float = 30.0):
        self.app_id, self.access_key, self.secret_key = app_id, access_key, secret_key
        self.base_url = base_url.rstrip("/")
        self.timeout_s = timeout_s
        self.clock_skew_s = 0.0   # this PC's clock minus JLCPCB's (signatures carry a timestamp)
        self._clock_checked = False

    @classmethod
    def from_env(cls):
        """A client from JLC_* environment variables, or None when they aren't set."""
        keys = [os.environ.get(k, "").strip() for k in ("JLC_APP_ID", "JLC_ACCESS_KEY", "JLC_SECRET_KEY")]
        if not all(keys):
            return None
        return cls(*keys, base_url=os.environ.get("JLC_API_BASE", DEFAULT_BASE))

    def _sign(self, method: str, path: str, body: str, timestamp: str, nonce: str) -> str:
        text = f"{method.upper()}\n{path}\n{timestamp}\n{nonce}\n{body}\n"
        mac = hmac.new(self.secret_key.encode(), text.encode(), hashlib.sha256).digest()
        signature = base64.b64encode(mac).decode()
        return (f'JOP appid="{self.app_id}",accesskey="{self.access_key}",timestamp="{timestamp}",'
                f'nonce="{nonce}",signature="{signature}"')

    def call(self, path: str, payload: dict, _retry: bool = True) -> dict:
        """POST `payload` as JSON to `path`; returns the response's `data`. Signatures carry a
        timestamp, so if JLCPCB refuses one and this PC's clock is off from the server's (its
        Date header), the call is re-signed once on the server's time."""
        if not self._clock_checked:
            self.server_clock_skew()
        body = json.dumps(payload, separators=(",", ":"))
        timestamp = str(int(time.time() - self.clock_skew_s))
        nonce = secrets.token_hex(16)   # 32 characters, as the SDK
        req = urllib.request.Request(self.base_url + path, data=body.encode(), method="POST", headers={
            "Content-Type": "application/json",
            "Authorization": self._sign("POST", path, body, timestamp, nonce),
        })
        try:
            with urllib.request.urlopen(req, timeout=self.timeout_s) as resp:
                result = json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            try:   # JLCPCB explains rejections in the body: {"code":400,"success":false,"message":"..."}
                message = json.loads(e.read().decode()).get("message") or ""
            except (ValueError, OSError):
                message = ""
            skew = _skew_from(e.headers)
            if _retry and e.code == 401 and skew is not None and abs(skew - self.clock_skew_s) > 30:
                self.clock_skew_s = skew
                return self.call(path, payload, _retry=False)
            hint = " (API access not approved yet, or wrong JLC_* credentials)" if e.code in (401, 403) else ""
            raise JlcApiError(f"JLCPCB API {path}: HTTP {e.code}{hint} {message}".strip()) from e
        except urllib.error.URLError as e:
            raise JlcApiError(f"JLCPCB API {path}: {e.reason}") from e
        code = result.get("code")
        if code not in (None, 0, 200, "200") or result.get("success") is False:
            raise JlcApiError(f"JLCPCB API {path}: {code} {result.get('message') or result.get('msg') or ''}".strip())
        return result.get("data")

    def server_clock_skew(self) -> float | None:
        """Read JLCPCB's time (a HEAD request's Date header). If this PC is more than 30 s off,
        sign on the server's time from now on. Returns the skew, or None if it can't be read."""
        self._clock_checked = True
        req = urllib.request.Request(self.base_url + "/", method="HEAD")
        try:
            try:
                with urllib.request.urlopen(req, timeout=self.timeout_s) as resp:
                    headers = resp.headers
            except urllib.error.HTTPError as e:
                headers = e.headers
        except (urllib.error.URLError, OSError, ValueError):
            return None
        skew = _skew_from(headers)
        if skew is not None and abs(skew) > 30:
            self.clock_skew_s = skew
        return skew

    def diagnose(self) -> list[str]:
        """Checks that don't reveal the keys: their shape, the PC's clock against JLCPCB's
        server, and one signed test call. Returns report lines."""
        lines = []
        for name, value in (("JLC_APP_ID", self.app_id), ("JLC_ACCESS_KEY", self.access_key),
                            ("JLC_SECRET_KEY", self.secret_key)):
            odd = [what for what, bad in (("spaces", " " in value), ("quotes", any(q in value for q in "'\"")),
                                          ("tabs or line breaks", any(c in value for c in "\t\r\n")),
                                          ("non-ASCII characters", not value.isascii())) if bad]
            lines.append(f"{name}: {len(value)} characters, starts {value[:2]!r}..." +
                         (f"  CONTAINS {', '.join(odd)}" if odd else ""))
        if self.access_key == self.secret_key:
            lines.append("JLC_ACCESS_KEY and JLC_SECRET_KEY are identical: one of them is wrong")
        skew = self.server_clock_skew()
        if skew is None:
            lines.append(f"Clock: couldn't read JLCPCB's time from {self.base_url}")
        else:
            lines.append(f"Clock: this PC is {skew:+.0f} s from JLCPCB's server" +
                         ("; requests are signed on JLCPCB's time instead, but set the PC's clock"
                          if self.clock_skew_s else " (fine)"))
        try:
            got = self.component_details(["C25804"])
            d = got.get("C25804", {})
            lines.append(f"Test call: OK. C25804 = {d.get('componentModel')} {d.get('componentSpecification')}, "
                         f"stock {d.get('stockCount')}")
        except JlcApiError as e:
            if self.clock_skew_s:
                lines.append(f"(signed on JLCPCB's time, {self.clock_skew_s:+.0f} s from this PC's, so the clock "
                             "isn't the cause)")
            lines.append(f"Test call: {e}")
        return lines

    def component_details(self, codes) -> dict[str, dict]:
        """{C-number: detail} for each code JLCPCB knows. Detail keys (from the SDK):
        componentCode, componentModel (MPN), componentSpecification (package), componentBrandEn,
        libraryType, description, datasheetUrl, stockCount, priceRanges[{startQuantity,
        endQuantity, unitPrice}], parameters[{parameterName, parameterValue}], assemblyComponentFlag."""
        codes = sorted({c.strip().upper() for c in codes if c and c.strip()})
        out = {}
        for i in range(0, len(codes), DETAIL_BATCH):
            data = self.call("/overseas/openapi/component/getComponentDetailByCode",
                             {"componentCodes": codes[i:i + DETAIL_BATCH]}) or []
            if isinstance(data, dict):        # tolerate {"data": [...]} nesting
                data = data.get("data") or []
            for d in data:
                out[str(d.get("componentCode", "")).upper()] = d
        return out

    def private_stock(self, page_size: int = 100) -> list[dict]:
        """Your parts held at JLCPCB (bought, global-sourced or consigned)."""
        rows, page = [], 1
        while True:
            data = self.call("/overseas/openapi/component/getPrivateComponentLibrary",
                             {"currentPage": page, "pageSize": page_size}) or {}
            batch = data.get("data") or []
            rows += batch
            if len(batch) < page_size or len(rows) >= (data.get("total") or 0):
                return rows
            page += 1
