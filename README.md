# OpenCTI-KUMA Lookup Proxy

## Description

The OpenCTI-KUMA integration automates the verification of Indicators of Compromise (IoCs) detected in security events from **Kaspersky Unified Monitoring and Analysis Platform (KUMA)** against the OpenCTI Threat Intelligence database.  

**Main goals of the integration:**

- Automatically check IoCs from KUMA events.  
- Enrich events with Threat Intelligence data.  
- Link indicators to OpenCTI analytical reports.  
- Accelerate analysis and incident investigation in SOC environments.  

The **OpenCTI-KUMA Lookup Proxy** acts as an intermediary between KUMA and OpenCTI, providing a REST API to verify indicators and retrieve contextual information.

---

## Integration Architecture

- **Service**: OpenCTI-KUMA Lookup Proxy implemented in Python using FastAPI.  
- **Deployment**: Docker container in the same Docker network as OpenCTI.  
- **Server**: Gunicorn with Uvicorn workers to handle asynchronous HTTP requests.  
- **Reverse Proxy**: Nginx providing HTTPS access to the service (port 8000).  

**Gunicorn worker configuration:**
```text
workers = 2 × CPU + 1
```

---

## API сервиса

### 1. `POST /api/1.1/lookup`

Checks KUMA indicators against OpenCTI.

**Request Body**:
```json
[
  {"object": "example.com"},
  {"object": "8.8.8.8"}
]
```

### 2. `GET /health`

Checks the health status of the service.

## Docker

| Переменная | Описание                                                         | Default                    |
|------------|------------------------------------------------------------------|----------------------------|
| `OPENCTI_URL_INTEGRATION` | OpenCTI GraphQL API URL                                          | `http://opencti:8080`      |
| `OPENCTI_URL` | OpenCTI UI URL                                                      | `https://opencti.test.com` |
| `OPENCTI_TOKEN` | Bearer token for the OpenCTI service user                     | `<token>`                  |
| `LOOKUP_BASIC_USER` | Username KUMA uses to connect to the proxy | `user`                     |
| `LOOKUP_BASIC_PASSWORD` | Password for KUMA to connect to the proxy                                      | `password`                 |
| `OPENCTI_TLS_VERIFY` | TLS verification when connecting to OpenCTI (`true/false`)             | `false`                    |
| `HTTP_TIMEOUT_SECONDS` | Timeout for HTTP requests to OpenCTI                                  | `60`                       |
| `HTTP_RETRIES` | Number of retry attempts for failed requests                             | `2`                        |
| `BATCH_SIZE` | Number of indicators per batch request                     | `40`                       |
| `CONCURRENCY` | Maximum number of concurrent requests                    | `10`                       |

---

### Docker build

```bash
docker build -t opencti-kuma-proxy:1.1 .
```

### Docker run
```bash
docker compose --env-file .env -f ./docker-compose.yml up -d
```

## Note
If you need to maximize search speed, replace the "contains" operator in your GraphQL queries with the "eq" operator. This will significantly improve response speed, but if you initially search for "url," for example, the search results won't be expanded to include domain name or IP address information, and vice versa.