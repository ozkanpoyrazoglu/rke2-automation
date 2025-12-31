# Cluster Lock ve Guardrail'ler

Unsafe operasyonları ve race condition'ları engellemek için minimal stage enforcement implementasyonu.

## Cluster Lock

### Database Schema
`Cluster` modeline eklendi:
```python
operation_status = Column(String, default="idle")  # idle|running
current_job_id = Column(Integer)
operation_started_at = Column(DateTime)
operation_locked_by = Column(String)  # operation tipi
```

### Lock Fonksiyonları

**acquire_cluster_lock()**
- `SELECT FOR UPDATE` ile race condition engelleniyor
- Cluster zaten locked ise HTTP 409 dönüyor
- Mesaj: `"Cluster is busy with operation 'X' (job Y). Please wait."`

**release_cluster_lock()**
- Lock'u idle state'e döndürüyor
- `finally` block'larda çağrılıyor (failure olsa bile release ediliyor)

## Guardrail'ler

### G1: Bootstrap Prerequisite
Initial master ACTIVE olmadan node eklenemiyor.

**Kontroller:**
- Initial master var mı
- Status ACTIVE mi
- RKE2 API'ye bağlanabiliyor mu (port 9345, best-effort)

**Hata:** `"Initial master 'm1' is not active (status: INSTALLING). Cannot add nodes."`

### G2: Safe Master Removal
Cluster'ı kırmayacak şekilde master siliniyor.

**Kontroller:**
- Son master silinemiyor
- Etcd quorum korunuyor
- Çift sayıda master uyarısı
- Confirmation flag zorunlu

**Hatalar:**
- `"Cannot remove all control-plane nodes. At least 1 required."`
- `"Removing 2 server(s) would break etcd quorum."`
- `"Removing control-plane nodes requires explicit confirmation."`

**API:** `confirm_master_removal: bool = False` query parameter eklendi

### G3: Split Master+Worker Additions
Master ve worker birlikte eklenince sıralı çalışıyor.

**Davranış:**
- Master job oluşturuluyor
- Worker'lar sonra ekleniyor mesajı dönüyor
- Response: `{"sequenced": true, "workers_pending": 3}`

**Not:** Şu anda worker job otomatik başlamıyor, job completion hook gerekiyor.

### G4: Node Identity Validation
Duplicate node eklenemiyor.

**Kontroller:**
- Hostname unique mi
- IP unique mi

**Hata:** `"Node with hostname 'worker-01' already exists in cluster"`

## Hata Response'ları

### 409 Conflict (Cluster Locked)
```json
{
  "detail": "Cluster is busy with operation 'scale_add_masters' (job 42)."
}
```

### 400 Bad Request (Bootstrap Not Ready)
```json
{
  "detail": "Initial master 'm1' is not active (status: INSTALLING)."
}
```

### 400 Bad Request (Duplicate Node)
```json
{
  "detail": "Node with hostname 'worker-01' already exists in cluster"
}
```

## Değiştirilen Dosyalar

**Yeni:**
- `backend/migrations/003_add_cluster_lock_fields.py`
- `backend/app/services/cluster_lock_service.py`

**Güncellenen:**
- `backend/app/models.py` - Lock field'ları eklendi
- `backend/app/routers/jobs.py` - Lock acquire/release
- `backend/app/routers/clusters.py` - Guardrail'ler eklendi
- `backend/app/services/ansible_service.py` - Lock release ve stage update

## Test

### Concurrent Operations
```bash
# Install başlat
curl -X POST http://localhost:8000/api/jobs/install/1

# Install devam ederken node ekle (409 dönmeli)
curl -X POST http://localhost:8000/api/clusters/1/scale/add \
  -d '{"nodes": [{"hostname": "w2", "ip": "10.0.0.5", "role": "agent"}]}'
```

### Bootstrap Check
```bash
# Initial master active değilken worker ekle (400 dönmeli)
curl -X POST http://localhost:8000/api/clusters/1/scale/add \
  -d '{"nodes": [{"hostname": "w1", "ip": "10.0.0.4", "role": "agent"}]}'
```

### Master Removal
```bash
# Son master'ı sil (400 dönmeli)
curl -X POST http://localhost:8000/api/clusters/1/scale/remove \
  -d '{"nodes": [{"hostname": "m1", "ip": "10.0.0.1", "role": "server"}]}'

# Confirmation ile sil (başarılı olmalı)
curl -X POST "http://localhost:8000/api/clusters/2/scale/remove?confirm_master_removal=true" \
  -d '{"nodes": [{"hostname": "m2", "ip": "10.0.1.11", "role": "server"}]}'
```

## Bilinen Limitler

1. **G3 Sequential:** Worker job otomatik başlamıyor, job completion hook gerekiyor
2. **Lock Timeout:** Stuck lock'lar için timeout mekanizması yok
3. **Bootstrap Check:** Port 9345 connectivity check best-effort, firewall nedeniyle fail olabilir

## Gelecek İyileştirmeler

- Lock timeout/expiry
- Worker job auto-queuing (G3 tam implementasyon)
- Operation queue (reject yerine queue'ya al)
- Force unlock admin endpoint
