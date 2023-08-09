# Core Solution Services

> This codebase is generated from https://github.com/GoogleCloudPlatform/solutions-builder

## Prerequisite

| Tool | Required Version | Installation |
|---|---|---|
| Python                 | &gt;= 3.9     | |
| gcloud CLI             | Latest        | https://cloud.google.com/sdk/docs/install |
| Terraform              | &gt;= v1.3.7  | https://developer.hashicorp.com/terraform/downloads |
| Skaffold               | &gt;= v2.4.0  | https://skaffold.dev/docs/install/ |
| Kustomize              | &gt;= v5.0.0  | https://kubectl.docs.kubernetes.io/installation/kustomize/ |
| solutions-builder CLI | &gt;= v1.13.0 | https://github.com/GoogleCloudPlatform/solutions-builder |

## Setup

### Create a new Google Cloud project

We'd recommend starting from a brand new GCP project. Create a new GCP project at [https://console.cloud.google.com/projectcreate]

### Install Solutions Builder package
```
pip install -U solutions-builder
```

### Set up gcloud CLI
```
export PROJECT_ID=<my-project-id>
gcloud auth login
gcloud auth application-default login
gcloud config set project $PROJECT_ID
```

Initialize the Cloud infra:
```
sb set project-id $PROJECT_ID
sb infra apply 1-bootstrap
```

Log in to the bastion host.
```
# TBD
```

Set up Cloud foundation and GKE cluster

```
sb infra apply-2-foundation
sb infra apply 2-gke
```

### Add a HTTP Load balancer with DNS domain
```
sb components add terraform_gke_ingress
```

Update the following questions in the promopt:
```
🎤 Cluster external endpoint IP address?
   x.x.x.x
🎤 Kubernetes service names in ingress? (comma-separated string)
   authentication,jobs-service,llm-service,user-management
🎤 DNS domains (comma-separated string)?
   example.domain.com
```
- Note: You can leave the DNS domains as empty if you don't have any custom domains. If so, you'd use IP address to connect to API endpoints later on.

Apply terraform for GKE ingress:
```
sb infra apply 3-gke-ingress
```

(Optional) Add an A record to your DNS:
![Alt text](.github/assets/dns_a_record.png)
- Set the IP address to the external IP address in the ingress.

## Deploy

### Set up each microservice:
- LLM Service: [components/llm_service/README.md](./components/llm_service/README.md)

### Deploy all microservices (optionally with Ingress) to GKE cluster:
```
sb deploy
```

### Set up admin user

In the source code:
```
PYTHONPATH=components/common/src/ python components/authentication/src/utils/setup.py create_admin

# Input the base URL for the deployed API endpoint:
Provide the base url for the API endpoint (e.g.  http://127.0.0.1/): https://your.domain.com/
```

- This will add the `admin` user to the Firestore (`users` collection).

### Verify deployed APIs

Once deployed, check out the API docs with the following links:
- https://<cluster-ip-address>/authentication/api/v1/docs
- https://<cluster-ip-address>/user-management/api/v1/docs
- https://<cluster-ip-address>/jobs-service/api/v1/docs
- https://<cluster-ip-address>/llm-service/api/v1/docs
