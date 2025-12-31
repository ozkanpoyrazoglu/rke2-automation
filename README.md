# RKE2 Automation

On-premise RKE2 cluster yönetimi için internal tool.

## Neler Var

- Yeni cluster oluşturma ve Ansible ile otomatik kurulum
- Mevcut cluster'ları register edip yönetme
- Node ekleme/çıkarma (guardrail'ler ile korumalı)
- Cluster status monitoring ve node sağlık durumu takibi
- Job logları ile canlı Ansible playbook çıktıları
- LLM destekli job özeti ve analiz (AWS Bedrock)

### Güvenlik ve Guardrail'ler

Sistem unsafe operasyonları engelliyor:

- **Cluster Lock:** Aynı anda tek operasyon (409 conflict dönüyor)
- **G1:** Initial master ACTIVE olmadan node eklenemez
- **G2:** Son master silinemiyor, quorum korunuyor
- **G3:** Master ve worker eklemeleri sıralı yapılıyor
- **G4:** Duplicate hostname/IP kontrolü

## Hızlı Başlangıç

```bash
# .env dosyasını hazırla
cp .env.example .env
# AWS credentials ve encryption key'i .env'e ekle

# Servisleri başlat
docker-compose up -d
```

Frontend: http://localhost:3000
Backend: http://localhost:8000

## Stack

- Frontend: React + Vite
- Backend: FastAPI + SQLAlchemy
- Database: SQLite (./data/rke2.db)
- Automation: Ansible + ansible-runner
- LLM: AWS Bedrock (Claude)

## Önemli Notlar

**Credential Encryption:**
```bash
python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

**Cluster Data:**
- Database: `data/rke2.db` (gitignore'da)
- Ansible artifacts: `ansible/clusters/<cluster-name>/` (gitignore'da)
- SSH credentials encrypted olarak database'de

**Node Status Sync:**
Database'deki node statusları bazen Kubernetes'teki gerçek durumla sync olmayabiliyor. Cluster detail sayfasında "Sync Nodes" butonu ile manuel sync yapabilirsin. Status refresh ederken otomatik sync de çalışıyor.

## Kullanım

**Cluster Oluşturma:**
1. New Cluster formunu doldur (name, RKE2 version, CNI)
2. Initial master node bilgilerini gir
3. SSH credential ekle
4. Create Cluster (Ansible artifact'leri oluşturur)
5. Install butonuna bas

**Node Ekleme/Çıkarma:**
- Cluster detail → Scale tab
- Add: hostname, IP, role gir
- Remove: node seç, remove bas, confirm et

**Monitoring:**
- Overview: cluster status, component health, node listesi
- Jobs: installation/scaling job logları

## Troubleshooting

**409 Conflict:**
Başka bir operasyon çalışıyor - beklemen gerekiyor. Jobs sayfasında running job'ları kontrol et.

**Node PENDING ama cluster çalışıyor:**
Sync Nodes butonuna bas veya status refresh yap.

**SSH bağlantı hatası:**
Credentials sayfasından SSH bilgilerini kontrol et. Firewall'lara bak (port 22).

## Güvenlik

**Secrets Scanning:**
Push etmeden önce credential taraması yap:
```bash
./scripts/scan-secrets.sh
```

GitHub'a her push'ta otomatik olarak Gitleaks Action çalışıyor.

## Daha Fazla

- [Cluster Lock & Guardrails](./CLUSTER_LOCK_AND_GUARDRAILS.md)
- [RKE2 Config Fix](./RKE2_CONFIG_FIX_SUMMARY.md)
