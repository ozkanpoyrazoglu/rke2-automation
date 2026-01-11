# Pre-flight Check & DeepSeek R1 Analysis

RKE2 upgrade öncesi cluster sağlık kontrolü ve LLM analizi.

## Özellikler

### Data Collection (Preflight Check)
- OS/Node: disk, swap, memory, NTP, firewall, port erişimi
- RKE2/etcd: service status, cluster health, certificate expiry
- Kubernetes: node status, pod restarts, CrashLoopBackOff, admission webhooks
- Network: CNI health, ingress controller
- Storage: StorageClass, provisioner, pending PVCs

### LLM Analysis (DeepSeek R1)
- Amazon Bedrock üzerinden DeepSeek R1 modeline gönderilir
- Çıktı: GO/NO-GO/CAUTION verdict + action plan
- Kritik sorunları otomatik tespit eder (etcd unhealthy, disk dolu, crash loop pods)

## Kullanım

### 1. Sadece Data Collection
```bash
POST /api/clusters/{cluster_id}/preflight-check
```

Response:
```json
{
  "cluster_metadata": {...},
  "nodes": [...],
  "checks": [...],
  "etcd": {...},
  "certificates": [...],
  "kubernetes": {...},
  "network": {...},
  "storage": {...}
}
```

### 2. Data Collection + LLM Analysis
```bash
POST /api/clusters/{cluster_id}/preflight-check?analyze=true
```

Response:
```json
{
  "preflight_data": {...},
  "analysis": {
    "verdict": "CAUTION",
    "reasoning_summary": "Etcd healthy but 2 warnings found...",
    "blockers": [],
    "risks": [
      "Disk space on worker-01 is 18% (critical threshold)",
      "Swap enabled on master-02"
    ],
    "action_plan": [
      "Free up disk space on worker-01 (/var/lib/rancher)",
      "Disable swap on master-02: sudo swapoff -a && edit /etc/fstab",
      "Run defrag on etcd: etcdctl defrag"
    ]
  }
}
```

## AWS Bedrock Setup

### Gereksinimler
1. AWS hesabınızda Bedrock erişimi
2. DeepSeek R1 modeline erişim (Model import gerekebilir)
3. IAM credentials (EC2 IAM role veya credentials file)

### Environment Variables
```bash
# Backend container için .env veya docker-compose.yml:
AWS_REGION=us-east-1
BEDROCK_MODEL_ID=arn:aws:bedrock:us-east-1::foundation-model/deepseek-r1

# AWS credentials (IAM role yoksa):
AWS_ACCESS_KEY_ID=...
AWS_SECRET_ACCESS_KEY=...
```

### IAM Policy (Minimum)
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "bedrock:InvokeModel"
      ],
      "Resource": "arn:aws:bedrock:*::foundation-model/deepseek-r1*"
    }
  ]
}
```

## DeepSeek R1 Response Format

Model çıktısı genellikle:
```
<think>
- Disk space critically low on worker-01
- Swap enabled on master-02 violates best practices
- Etcd is healthy but DB size is 2.3GB (defrag recommended)
</think>
{
  "verdict": "CAUTION",
  "reasoning_summary": "...",
  ...
}
```

Backend otomatik olarak `<think>` bloğunu strip edip JSON'u parse eder.

## Troubleshooting

### Analysis fails with "BEDROCK_MODEL_ID not set"
- `.env` dosyasına `BEDROCK_MODEL_ID` ekleyin
- Docker container'ı restart edin

### "No module named 'boto3'"
- `backend/requirements.txt` içine `boto3` ekleyin
- Backend image'ı rebuild edin: `docker-compose build backend`

### JSON parse error
- Log'larda `<think>` bloğunun kaldırılıp kaldırılmadığını kontrol edin
- Model response formatı farklıysa `_parse_deepseek_response` metodunu güncelleyin

### Bedrock API error: "Model not found"
- Model ID'nin doğru olduğundan emin olun
- AWS Console > Bedrock > Model access'ten modelin enabled olduğunu kontrol edin
- DeepSeek R1 import edilmişse ARN'i tam yazın

## Örnek Output
`backend/app/services/preflight/example_output.json` dosyasında sample veri var.

## Mimari

```
Frontend
   ↓
POST /api/clusters/1/preflight-check?analyze=true
   ↓
PreflightCollector (SSH + kubectl ile data toplar)
   ↓
DeepSeekBedrockAnalyzer (Bedrock'a gönderir)
   ↓
AnalysisResult (verdict + action plan)
   ↓
Response to frontend
```

## Cost Optimization

DeepSeek R1 maliyetli olabilir. İpuçları:
- `analyze=true` parametresini sadece gerektiğinde kullanın
- Preflight data'yı frontend'de cache'leyin
- İlk önce `analyze=false` ile data toplayın, UI'da gösterin
- Kullanıcı onaylarsa tekrar `analyze=true` ile istek atın

## Read-only Operations

Tüm preflight checkler read-only:
- SSH komutları sadece `df`, `swapon`, `systemctl status` gibi query komutları
- kubectl sadece `get` ve `describe` kullanır
- Hiçbir şey değiştirilmez, silinmez, restart edilmez
