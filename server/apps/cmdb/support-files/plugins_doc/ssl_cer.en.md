### Overview
Performs a TLS handshake against the domain of an already created SSL certificate instance, collects issuer, issued time, and expiry time, and writes them back to the same instance. Does not create or delete certificate assets, and does not change the instance name or domain.

### Prerequisites
1. Create instances first (instance name + domain), then create the collection task.
2. The collection task selects instances only; network segments cannot be selected.
3. Default port 443; no credentials.
4. Expired or self-signed certificates are still collected (certificate chain is not verified).

### Entry Point
CMDB → Management → Auto Discovery → Collection → Professional Collection → SSL Certificate.
